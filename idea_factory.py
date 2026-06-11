"""3층: 자동 아이디어 출제기.

깃허브 스타순 메타데이터 수집(콜 0) → topic 버킷 추첨 → 자카드 중복제거
→ 뽑힌 후보만 README 발췌 + 난이도 5축 프로필을 줘서 31B가 아이디어 작성(콜 1).

- 난이도는 주제가 아니라 요구사항의 속성: 주제(버킷 추첨)와 난이도(5축 레벨 1~5)를
  분리 출제한다.
- 레벨은 runs/index.json 최근 성적으로 적응 조절 — 타깃: 자가수정 1~2회 구간.
  (전부 첫 트 통과 = lessons 0개, 전부 폭사 = lessons 노이즈)
- 상태(현재 레벨·사용한 저장소)는 auto_state.json에 저장.

사용법:
    python idea_factory.py --dry   # 콜 0: 후보 저장소·난이도만 뽑아본다
    python idea_factory.py         # 콜 1: 아이디어 1건 생성·출력
"""

import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

from config import PROJECT_ROOT, force_utf8_stdout, load_env
from lessons import _tokens
from run_index import load_index
from schema import extract_json

RUNS_DIR = PROJECT_ROOT / "runs"
STATE_PATH = PROJECT_ROOT / "auto_state.json"

# 주제 버킷: Python CLI 프로토타입으로 재해석하기 좋은 도메인들.
# 버킷 추첨이 다양성을 보장하므로 임베딩이 필요 없다.
TOPIC_BUCKETS = [
    "cli", "automation", "productivity", "finance", "budget",
    "data-analysis", "text-processing", "file-manager", "scheduler",
    "monitoring", "backup", "note-taking", "password-manager",
    "static-site-generator", "log-analysis", "inventory", "parser",
    "encryption", "todo", "bookmark", "habit-tracking", "invoice",
    "recipe", "flashcards", "time-tracker",
]

MIN_STARS = 100          # 검색 하한 (의미 있는 프로젝트만)
REPOS_PER_TOPIC = 30     # 토픽당 수집 개수
BUCKET_ATTEMPTS = 8      # 신선한 후보를 못 찾을 때 버킷 재추첨 횟수
SIMILARITY_THRESHOLD = 0.35  # 과거 아이디어와 자카드 유사도 상한
README_MAX_CHARS = 2500
MAX_USED_REPOS = 500     # auto_state.json 비대 방지

DEFAULT_LEVEL = 2
RECENT_N = 5             # 적응 조절에 보는 최근 런 수
TARGET_FIX_LO = 1.0      # 평균 자가수정이 이보다 적고 전부 성공이면 레벨 ↑
TARGET_FIX_HI = 2.5      # 평균 자가수정이 이보다 많거나 성공률 <50%면 레벨 ↓

# 5축 난이도 앵커: 레벨 1~5 각각의 요구 강도. 31B 프롬프트에 그대로 들어간다.
AXIS_GUIDE: dict[str, dict[int, str]] = {
    "state": {
        1: "no persistent state - pure input to output transformation",
        2: "one small state file, read-mostly (e.g. a config or counter)",
        3: "one state file (JSON) that the tool reads AND updates",
        4: "two related state files kept consistent with each other",
        5: "multiple state files with history/undo or state transitions",
    },
    "integration": {
        1: "no external system at all",
        2: "reads one external-format file produced by another program",
        3: "one external API, replaceable by a mock JSON response file",
        4: "one external API with live/mock mode switch via env var",
        5: "two or more external systems (all mockable) with mode switching",
    },
    "input": {
        1: "CLI arguments only",
        2: "one structured input file (CSV or JSON)",
        3: "one or two structured input files with format validation",
        4: "multiple input files with required-field and range validation",
        5: "multiple input formats with cross-file consistency checks",
    },
    "modules": {
        1: "2-3 source files",
        2: "3 source files",
        3: "4-5 source files",
        4: "5-6 source files",
        5: "6 or more source files",
    },
    "breadth": {
        1: "a single core feature",
        2: "one core feature plus a report/summary output",
        3: "2-3 features (e.g. validate + transform + report)",
        4: "3-4 features behind distinct subcommands",
        5: "4 or more subcommands covering distinct workflows",
    },
}


# ------------------------------------------------------------ github (콜 0)

def github_token() -> str:
    load_env()
    return os.environ.get("GITHUB_TOKEN", "").strip()


def _gh_get(path: str, token: str, accept: str = "application/vnd.github+json",
            timeout: int = 15) -> str:
    headers = {"Accept": accept, "User-Agent": "arag-idea-factory"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request("https://api.github.com" + path,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_repo_candidates(topic: str, token: str) -> list[dict]:
    """토픽의 스타 상위 저장소 메타데이터. 실패하면 빈 리스트 (버킷 재추첨)."""
    path = (f"/search/repositories?q=topic:{topic}+stars:>{MIN_STARS}"
            f"&sort=stars&order=desc&per_page={REPOS_PER_TOPIC}")
    try:
        data = json.loads(_gh_get(path, token))
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        return []
    out = []
    for item in data.get("items", []):
        out.append({
            "full_name": item.get("full_name", ""),
            "description": item.get("description") or "",
            "topics": item.get("topics") or [],
            "stars": item.get("stargazers_count", 0),
        })
    return [r for r in out if r["full_name"]]


def fetch_readme(full_name: str, token: str,
                 max_chars: int = README_MAX_CHARS) -> str:
    """README 원문 발췌. 없거나 실패하면 빈 문자열 (description만으로 진행)."""
    try:
        text = _gh_get(f"/repos/{full_name}/readme", token,
                       accept="application/vnd.github.raw+json")
    except (urllib.error.URLError, OSError, TimeoutError):
        return ""
    return text[:max_chars]


# ------------------------------------------------------------ 중복제거 (콜 0)

def jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def too_similar(candidate_text: str, past_ideas: list[str],
                threshold: float = SIMILARITY_THRESHOLD) -> bool:
    cand = _tokens(candidate_text)
    return any(jaccard(cand, _tokens(idea)) >= threshold
               for idea in past_ideas if idea)


# ------------------------------------------------------------ 상태·난이도

def load_state(path: Path | None = None) -> dict:
    path = Path(path) if path else STATE_PATH  # 호출 시점 결정 (테스트 격리)
    if not Path(path).exists():
        return {"level": DEFAULT_LEVEL, "used_repos": []}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (json.JSONDecodeError, OSError, ValueError):
        return {"level": DEFAULT_LEVEL, "used_repos": []}
    data.setdefault("level", DEFAULT_LEVEL)
    data.setdefault("used_repos", [])
    return data


def save_state(state: dict, path: Path | None = None) -> None:
    path = Path(path) if path else STATE_PATH
    state["used_repos"] = state.get("used_repos", [])[-MAX_USED_REPOS:]
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def adjust_level(level: int, entries: list[dict]) -> int:
    """최근 성적으로 레벨 조절. 타깃: 자가수정 1~2회 구간.

    런 3개 미만이면 판단 보류 (현 레벨 유지).
    """
    recent = entries[-RECENT_N:]
    if len(recent) < 3:
        return max(1, min(5, level))
    fixes = [sum((e.get("fixes") or {}).values()) for e in recent]
    avg_fixes = sum(fixes) / len(fixes)
    ok_rate = sum(1 for e in recent if e.get("ok")) / len(recent)
    if ok_rate < 0.5 or avg_fixes > TARGET_FIX_HI:
        return max(1, level - 1)
    if ok_rate == 1.0 and avg_fixes < TARGET_FIX_LO:
        return min(5, level + 1)
    return max(1, min(5, level))


def axis_levels(base_level: int, rng: random.Random) -> dict[str, int]:
    """기본 레벨 주변에서 축별로 ±1 흔들어 조합 다양성을 만든다."""
    return {axis: max(1, min(5, base_level + rng.choice((-1, 0, 0, 1))))
            for axis in AXIS_GUIDE}


# ------------------------------------------------------------ 후보 추첨

def pick_candidate(token: str, past_ideas: list[str], used_repos: list[str],
                   rng: random.Random,
                   fetch=None) -> tuple[str, dict] | None:
    """버킷 추첨 → 미사용·비유사 저장소 1개. 못 찾으면 None."""
    fetch = fetch or fetch_repo_candidates  # 호출 시점 결정 (테스트 격리)
    used = set(used_repos)
    topics = list(TOPIC_BUCKETS)
    rng.shuffle(topics)
    for topic in topics[:BUCKET_ATTEMPTS]:
        repos = fetch(topic, token)
        rng.shuffle(repos)
        for repo in repos:
            if repo["full_name"] in used:
                continue
            cand_text = " ".join([repo["full_name"], repo["description"],
                                  " ".join(repo["topics"])])
            if too_similar(cand_text, past_ideas):
                continue
            return topic, repo
    return None


# ------------------------------------------------------------ 출제 (콜 1)

def idea_prompt(repo: dict, readme: str, axes: dict[str, int]) -> str:
    axis_lines = "\n".join(
        f"- {axis} (level {lv}/5): {AXIS_GUIDE[axis][lv]}"
        for axis, lv in axes.items())
    readme_block = f"\nREADME EXCERPT:\n{readme}\n" if readme.strip() else ""
    return f"""You set exam problems for an automated pipeline that builds multi-file
Python CLI prototypes. Below is a real open-source project for INSPIRATION
only. Reinterpret its core concept as a SMALL, SELF-CONTAINED Python CLI tool
idea. Borrow the domain and concept - do NOT describe a clone of the project.

REPO: {repo['full_name']} ({repo['stars']} stars)
DESCRIPTION: {repo['description']}
TOPICS: {', '.join(repo['topics'])}
{readme_block}
The idea MUST match this difficulty profile exactly. These are requirement
attributes, independent of the topic:
{axis_lines}

Hard constraints for the idea:
- implementable as a Python CLI tool (stdlib preferred, at most 1-2 common
  packages like click or openpyxl)
- NO interactive stdin - all input via CLI arguments and files
- if an external API appears, state explicitly that it must be replaceable
  by a mock JSON response file
- concrete and testable: name the input formats, the checks, and the outputs
- write the idea in KOREAN, 2-4 sentences, as one paragraph

Respond with a single JSON object (no prose, no fences):
{{"idea": "한국어 아이디어 한 단락", "keywords": ["3-8 lowercase topic words"]}}"""


def _parse_idea(text: str) -> dict | None:
    raw = extract_json(text)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    idea = str(parsed.get("idea", "")).strip()
    if not idea:
        return None
    keywords = [str(k).strip().lower() for k in parsed.get("keywords", [])
                if str(k).strip()]
    return {"idea": idea, "keywords": keywords}


def generate_idea(llm, rng: random.Random | None = None,
                  runs_dir: Path | None = None) -> dict:
    """파이프라인 전체: 추첨(콜 0) → 31B 출제(콜 1). 실패 시 RuntimeError."""
    rng = rng or random.Random()
    runs_dir = Path(runs_dir) if runs_dir else RUNS_DIR
    token = github_token()
    state = load_state()
    entries = load_index(runs_dir)
    level = adjust_level(int(state.get("level", DEFAULT_LEVEL)), entries)
    axes = axis_levels(level, rng)

    past_ideas = [str(e.get("idea", "")) for e in entries]
    picked = pick_candidate(token, past_ideas, state.get("used_repos", []), rng)
    if picked is None:
        raise RuntimeError("no fresh repo candidate found "
                           "(network down or buckets exhausted)")
    topic, repo = picked
    readme = fetch_readme(repo["full_name"], token)

    prompt = idea_prompt(repo, readme, axes)
    parsed = _parse_idea(llm.generate("critic", prompt))
    if parsed is None:  # 프롬프트 JSON 실패 시 1회 재요청 (프로젝트 공통 규칙)
        parsed = _parse_idea(llm.generate("critic", prompt))
    if parsed is None:
        raise RuntimeError("31B returned unparseable idea JSON twice")

    state["level"] = level
    state["used_repos"] = state.get("used_repos", []) + [repo["full_name"]]
    save_state(state)
    return {"idea": parsed["idea"], "keywords": parsed["keywords"],
            "repo": repo["full_name"], "topic": topic,
            "level": level, "axes": axes}


# ------------------------------------------------------------ CLI

def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="auto idea generator (3rd layer)")
    parser.add_argument("--dry", action="store_true",
                        help="pick a candidate repo only - no API call")
    args = parser.parse_args()

    if args.dry:
        rng = random.Random()
        state = load_state()
        level = adjust_level(int(state.get("level", DEFAULT_LEVEL)),
                             load_index(RUNS_DIR))
        axes = axis_levels(level, rng)
        past = [str(e.get("idea", "")) for e in load_index(RUNS_DIR)]
        picked = pick_candidate(github_token(), past,
                                state.get("used_repos", []), rng)
        if picked is None:
            print("[ERROR] no candidate found")
            return 1
        topic, repo = picked
        print(f"[DRY] topic={topic} level={level} axes={axes}")
        print(f"[DRY] repo={repo['full_name']} stars={repo['stars']}")
        print(f"[DRY] desc={repo['description']}")
        return 0

    from llm import LLMClient
    out = generate_idea(LLMClient(max_calls=4))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
