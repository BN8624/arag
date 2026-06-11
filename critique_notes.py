"""비평노트: 검증된 비평(수정이 게이트·채점표를 통과해 살아남은 것)을 기록하고,
새 회차의 구현 단계(26B)에 주입한다.

오답노트(lessons.py)와의 분담:
- 오답노트  = "뭐가 깨지는가"  -> 설계 단계(31B)에 주입
- 비평노트  = "뭐가 코드를 더 좋게 만드는가" -> 구현 단계(26B)에 주입

수확 조건이 핵심: rollback된 비평(수정이 게이트를 깨거나 점수를 낮춘 것)은
트집이었거나 잘못된 지적이므로 기록하지 않는다. 기록은 콜 0 — 비평 텍스트를
그대로 쓴다(이미 31B가 쓴 구조화된 지적).

저장소: critique_notes.json (프로젝트 루트). 형식:
[
  {"t": "...", "idea": "...", "path": "main.py",
   "issue": "usage message unclear"}
]
"""

import json
import re
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT

NOTES_PATH = PROJECT_ROOT / "critique_notes.json"
MAX_INJECT = 3      # 구현 프롬프트에 넣을 노트 최대 개수
MAX_NOTES = 300     # 파일 비대 방지 (넘치면 오래된 것부터 버림)
FREQ_FLOOR = 3      # 주제가 안 겹쳐도 이만큼 반복된 지적이면 주입 (보편 규칙 취급)


def load_notes(path: Path | None = None) -> list[dict]:
    path = Path(path or NOTES_PATH)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[0-9a-zA-Z가-힣]{2,}", text.lower()))


def _norm(issue: str) -> str:
    """빈도 집계용 정규화 — 공백·대소문자 차이만 흡수."""
    return " ".join(issue.lower().split())


def record_notes(idea: str, flagged: list[dict],
                 path: Path | None = None) -> int:
    """살아남은 비평의 파일별 지적을 저장. 기록된 건수를 반환.

    flagged: [{"path": "main.py", "issues": ["...", ...]}, ...]
    실패해도 회차를 막지 않도록 예외를 내지 않는다.
    """
    try:
        now = datetime.now().isoformat(timespec="seconds")
        entries = load_notes(path)
        added = 0
        for f in flagged:
            file_path = str(f.get("path", "")).strip()
            for issue in f.get("issues", []):
                issue_text = str(issue).strip()
                if not issue_text:
                    continue
                entries.append({"t": now, "idea": idea,
                                "path": file_path, "issue": issue_text})
                added += 1
        if added:
            Path(path or NOTES_PATH).write_text(
                json.dumps(entries[-MAX_NOTES:], ensure_ascii=False, indent=2),
                encoding="utf-8")
        return added
    except Exception:  # noqa: BLE001
        return 0


def find_relevant(idea: str, notes: list[dict] | None = None,
                  max_n: int = MAX_INJECT,
                  path: Path | None = None) -> list[str]:
    """주입할 노트를 점수순으로 최대 max_n개 반환.

    점수 = 아이디어와의 키워드 겹침 + 반복 빈도.
    겹침이 없어도 FREQ_FLOOR회 이상 반복된 지적은 보편 규칙으로 보고 주입.
    """
    if notes is None:
        notes = load_notes(path)
    idea_tokens = _tokens(idea)

    freq: dict[str, int] = {}
    first_text: dict[str, str] = {}
    overlap: dict[str, int] = {}
    for entry in notes:
        issue = str(entry.get("issue", "")).strip()
        if not issue:
            continue
        key = _norm(issue)
        freq[key] = freq.get(key, 0) + 1
        first_text.setdefault(key, issue)
        ov = len(idea_tokens & _tokens(issue + " " + str(entry.get("idea", ""))))
        overlap[key] = max(overlap.get(key, 0), ov)

    scored: list[tuple[int, str]] = []
    for key, count in freq.items():
        ov = overlap.get(key, 0)
        if ov == 0 and count < FREQ_FLOOR:
            continue
        scored.append((ov * 2 + min(count, 5), first_text[key]))
    scored.sort(key=lambda x: -x[0])
    return [text for _, text in scored[:max_n]]


def frequent_candidates(min_count: int = 5,
                        path: Path | None = None) -> list[tuple[int, str]]:
    """HARD_RULES 승격 후보: min_count회 이상 반복된 지적 (빈도 내림차순)."""
    freq: dict[str, int] = {}
    first_text: dict[str, str] = {}
    for entry in load_notes(path):
        issue = str(entry.get("issue", "")).strip()
        if not issue:
            continue
        key = _norm(issue)
        freq[key] = freq.get(key, 0) + 1
        first_text.setdefault(key, issue)
    out = [(count, first_text[key]) for key, count in freq.items()
           if count >= min_count]
    out.sort(key=lambda x: -x[0])
    return out
