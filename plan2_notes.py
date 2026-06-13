# PLAN 2 warm 노트 품질 필터 (콜0): cold 수확 노트를 USE/HOLD/DROP로 자동 분류, 폰 감사에서 변경
"""PLAN.md §1.5 구현 — cold 실패에서 나온 노트를 warm 저장소에 넣기 전 거른다.

잘못된 비평·카드전용 과적합 패치·트리비얼을 걸러 warm 오염을 막는다.
기계 자동 분류(보수적, 기본 HOLD) → 폰 감사에서 사람이 변경. USE만 warm에 주입.
콜0 휴리스틱(모델 호출 없음). 영어 교훈 기준(record_lesson이 영어 규칙을 뽑음).
"""

import re

# 일반적·실행가능 규칙을 시사하는 동사 (USE 후보)
_ACTIONABLE = re.compile(
    r"\b(use|ensure|handle|validate|avoid|always|never|prefer|implement|"
    r"check|treat|provide|return|raise|verify|guard|escape|normalize)\b",
    re.IGNORECASE)

# 카드 전용(과적합)을 시사하는 패턴 (DROP 후보)
_FILE_REF = re.compile(r"\b[\w/]+\.py\b")          # 특정 파일명
_CALL_REF = re.compile(r"\b[a-zA-Z_]\w*\([^)]*\)")  # 특정 함수 호출
_SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")          # snake_case 식별자

MIN_LEN = 15  # 이보다 짧으면 트리비얼 → DROP


def classify_note(text: str) -> str:
    """노트 1건을 USE/HOLD/DROP로 분류. 보수적 — 애매하면 HOLD."""
    t = (text or "").strip()
    if len(t) < MIN_LEN:
        return "DROP"  # 트리비얼

    # 카드 전용 신호: 특정 파일/함수호출, 또는 snake_case 식별자 2개 이상
    if _FILE_REF.search(t) or _CALL_REF.search(t) or len(_SNAKE.findall(t)) >= 2:
        return "DROP"

    # 일반적·실행가능 규칙
    if _ACTIONABLE.search(t):
        return "USE"

    return "HOLD"  # 애매 — 기록만, 주입 안 함


def partition(notes: list[str]) -> dict[str, list[str]]:
    """노트 리스트를 USE/HOLD/DROP로 분할. (중복 제거, 순서 보존)."""
    out: dict[str, list[str]] = {"USE": [], "HOLD": [], "DROP": []}
    seen: set[str] = set()
    for n in notes:
        key = (n or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out[classify_note(key)].append(key)
    return out


def render_note_audit(notes: list[str]) -> str:
    """노트 후보 폰 감사 화면 — 후보 + 기계 판정 + 변경 체크 (PLAN §1.5)."""
    parts = partition(notes)
    lines = ["[노트 후보 감사]  USE만 warm 저장소에 주입됨"]
    for verdict in ("USE", "HOLD", "DROP"):
        for n in parts[verdict]:
            lines.append(f"- 교훈: {n}")
            lines.append(f"  판정: {verdict}   [ ] USE  [ ] HOLD  [ ] DROP")
    counts = " / ".join(f"{k} {len(parts[k])}" for k in ("USE", "HOLD", "DROP"))
    lines.append(f"합계: {counts}")
    return "\n".join(lines)
