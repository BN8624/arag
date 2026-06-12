"""만점 런의 사용자 시점 총평 (31B 1콜, 블랙박스).

채점표가 만점이면 잴 게 없어진다 — 그때 31B에게 "사용자가 보는 것"만 주고
(아이디어·README·수용기준. 코드는 절대 주지 않음) 실사용자가 가장 아쉬워할
개선점 1~3개를 받아 improve 모드의 피드백으로 쓴다.

코드를 안 주는 이유: 31B는 이 설계의 저자라 코드를 보면 자기 작품에 후해진다
(자가채점 편향). 블랙박스로 결과물만 보게 하면 시선이 사용자 쪽으로 강제된다.

결과는 run_dir/auto_review.json에 기록 — NOCHANGE여도 기록해서
배치가 같은 런을 다시 총평하느라 콜을 태우지 않게 한다 (런당 총평 1회).
"""

import json
from datetime import datetime
from pathlib import Path

from schema import extract_json

REVIEW_FILE = "auto_review.json"
README_MAX_CHARS = 4000


def review_prompt(idea: str, readme: str, criteria: list[str]) -> str:
    criteria_lines = "\n".join(f"- {c}" for c in criteria) or "(none listed)"
    return f"""You are an END USER evaluating a small Python CLI tool. You can see
only what a user sees: the idea it promises, its README, and the acceptance
criteria it already passes. You have NOT seen the source code and you do not
care how it is written - only how useful it is.

THE IDEA IT PROMISES:
{idea}

ITS README:
{readme}

ACCEPTANCE CRITERIA IT ALREADY PASSES (all of them):
{criteria_lines}

First decide the verdict, in this order:
- SUGGEST only if a real user following the README would hit a WALL:
  a capability the idea promises is missing or wrong, the README leaves the
  tool unusable (a user cannot figure out how to run it), or the output is
  misleading about what the tool did.
- NOCHANGE if the tool delivers what the idea promises and the README is
  enough to use it. Nice-to-haves are NOT walls: more README detail, extra
  convenience commands, prettier output, optional validation, broader inputs
  than promised. If nice-to-haves are all you can think of, the verdict is
  NOCHANGE.

Expect NOCHANGE to be the common case - these tools already pass every
acceptance criterion. A clean NOCHANGE is more useful than invented busywork;
do not suggest something just to appear thorough.

If (and only if) the verdict is SUGGEST, name the 1-3 walls. Stay inside the
existing idea - no rewrites, no new external services, no scope creep. Each
suggestion must be concrete enough to act on.

Respond with a single JSON object (no prose, no fences):
{{"verdict": "SUGGEST" or "NOCHANGE",
  "feedback": "2-4 sentences in Korean, concrete - empty if NOCHANGE"}}"""


def _parse_review(text: str) -> dict | None:
    raw = extract_json(text)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    verdict = str(parsed.get("verdict", "")).strip().upper()
    feedback = str(parsed.get("feedback", "")).strip()
    if verdict == "NOCHANGE":
        return {"verdict": "NOCHANGE", "feedback": ""}
    if verdict == "SUGGEST" and feedback:
        return {"verdict": "SUGGEST", "feedback": feedback}
    return None


def review_marker(run_dir: Path) -> Path:
    return Path(run_dir) / REVIEW_FILE


def user_review(llm, run_dir: Path, idea: str) -> str | None:
    """만점 런 총평 1콜. 개선 피드백 문자열 또는 None(NOCHANGE) 반환.

    어떤 결과든 auto_review.json 마커를 남긴다 (런당 총평 1회 보장).
    파싱 실패가 반복되면 NOCHANGE로 취급 — 총평 때문에 콜을 더 태우지 않는다.
    """
    run_dir = Path(run_dir)
    workspace = run_dir / "workspace"
    readme_path = workspace / "README.md"
    readme = (readme_path.read_text(encoding="utf-8")[:README_MAX_CHARS]
              if readme_path.exists() else "(no README)")
    criteria: list[str] = []
    design_path = run_dir / "design.json"
    if design_path.exists():
        try:
            design = json.loads(design_path.read_text(encoding="utf-8"))
            criteria = [str(c) for c in design.get("acceptance_criteria") or []]
        except (json.JSONDecodeError, OSError):
            pass

    prompt = review_prompt(idea, readme, criteria)
    parsed = _parse_review(llm.generate("critic", prompt))
    if parsed is None:  # 프롬프트 JSON 실패 시 1회 재요청 (프로젝트 공통 규칙)
        parsed = _parse_review(llm.generate("critic", prompt))
    if parsed is None:
        parsed = {"verdict": "NOCHANGE", "feedback": "",
                  "note": "unparseable twice - treated as NOCHANGE"}

    record = {"t": datetime.now().isoformat(timespec="seconds"), **parsed}
    review_marker(run_dir).write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return parsed["feedback"] or None
