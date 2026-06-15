"""오답노트: 실패한 회차의 교훈을 기록하고, 새 회차의 설계에 주입한다.

저장소: lessons.json (프로젝트 루트). 형식:
[
  {"t": "2026-06-10T21:50:00", "idea": "...", "keywords": ["csv", "table"],
   "lesson": "한두 문장의 구체적 교훈"}
]

- 검색(find_relevant)은 키워드 겹침 — 콜 0, 임베딩 없음 (2차에서 업그레이드 검토).
- 기록(record_lesson)은 31B(critic)에게 실패 분석을 1콜 요청.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT
from schema import extract_json

LESSONS_PATH = PROJECT_ROOT / "lessons.json"
MAX_INJECT = 3      # 설계 프롬프트에 넣을 교훈 최대 개수
MAX_LESSONS = 200   # 파일 비대 방지 (넘치면 오래된 것부터 버림)


def load_lessons(path: Path | None = None) -> list[dict]:
    path = LESSONS_PATH if path is None else path  # 기본값은 호출시점에(격리 반영)
    if not Path(path).exists():
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[0-9a-zA-Z가-힣]{2,}", text.lower()))


def find_relevant_entries(idea: str, lessons: list[dict] | None = None,
                          max_n: int = MAX_INJECT) -> list[dict]:
    """아이디어와 키워드가 겹치는 교훈 엔트리를 점수순으로 최대 max_n개 반환.

    엔트리 전체를 반환하므로 호출자가 keywords를 알 수 있다 (재발률 집계용).
    """
    if lessons is None:
        lessons = load_lessons()
    idea_tokens = _tokens(idea)
    scored: list[tuple[int, dict]] = []
    for entry in lessons:
        lesson_text = str(entry.get("lesson", "")).strip()
        if not lesson_text:
            continue
        keywords = " ".join(str(k) for k in entry.get("keywords", []))
        overlap = idea_tokens & _tokens(keywords + " " + str(entry.get("idea", "")))
        if overlap:
            scored.append((len(overlap), entry))
    scored.sort(key=lambda x: -x[0])
    # 같은 교훈 중복 제거
    seen: set[str] = set()
    out: list[dict] = []
    for _, entry in scored:
        lesson_text = str(entry.get("lesson", "")).strip()
        if lesson_text not in seen:
            seen.add(lesson_text)
            out.append(entry)
        if len(out) >= max_n:
            break
    return out


def find_relevant(idea: str, lessons: list[dict] | None = None,
                  max_n: int = MAX_INJECT) -> list[str]:
    """아이디어와 키워드가 겹치는 교훈을 점수순으로 최대 max_n개 반환."""
    return [str(e.get("lesson", "")).strip()
            for e in find_relevant_entries(idea, lessons, max_n)]


def record_lesson(llm, idea: str, failure_summary: str,
                  path: Path | None = None) -> dict | None:
    """실패 증거를 31B에게 주고 교훈 1건을 뽑아 lessons.json에 저장.

    실패해도 회차 종료를 막지 않도록 None을 반환할 뿐 예외를 내지 않는다.
    """
    path = LESSONS_PATH if path is None else path  # 기본값은 호출시점에(격리 반영)
    prompt = f"""A fully automated code-generation pipeline failed while building a
prototype for this idea:

IDEA: {idea}

FAILURE EVIDENCE:
{failure_summary}

Diagnose the ROOT CAUSE and write ONE short lesson that would let a future
design for a similar idea avoid this exact failure. The lesson must be a
concrete design rule (what to do or avoid), not a description of the failure.

Respond with a single JSON object (no prose, no fences):
{{"keywords": ["3-8 lowercase topic words for matching similar ideas"],
  "lesson": "one or two sentences, concrete and actionable"}}"""
    try:
        text = llm.generate("critic", prompt)
        raw = extract_json(text)
        if not raw:
            return None
        parsed = json.loads(raw)
        lesson_text = str(parsed.get("lesson", "")).strip()
        keywords = [str(k).strip().lower() for k in parsed.get("keywords", [])
                    if str(k).strip()]
        # 더미·퇴행 응답 거름: 실제 교훈은 한 문장이라 6자 미만은 쓰레기
        if len(lesson_text) < 6 or lesson_text.lower() in {"n/a", "none", "todo"}:
            return None
        entry = {
            "t": datetime.now().isoformat(timespec="seconds"),
            "idea": idea,
            "keywords": keywords,
            "lesson": lesson_text,
        }
        lessons = load_lessons(path)
        lessons.append(entry)
        Path(path).write_text(
            json.dumps(lessons[-MAX_LESSONS:], ensure_ascii=False, indent=2),
            encoding="utf-8")
        return entry
    except Exception:  # noqa: BLE001 - 오답노트 실패가 회차 보고를 막으면 안 됨
        return None
