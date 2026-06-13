# Design Bank 카드 생성: 설계자 호출 + 분포 밸런서 + 파싱 재요청 1회
"""31B(또는 mock) 설계자에게 task_card를 한 장씩 받아 DB에 적재한다.

- 분포 밸런서: 현재 DB에서 가장 빈약한 (난이도 레벨 + 태그)를 다음 카드 목표로
  지정해 분포를 고르게 채운다 (PLAN §2.5 "부족 조합 우선").
- 파싱/검증 실패 시 에러를 프롬프트에 넣어 1회만 재요청 (콜 절약).
- 중복은 건너뛰고 집계만 한다 (실패 아님).

설계자는 .design(prompt) -> str 인터페이스만 요구 — 테스트는 mock 주입으로 콜 0.
"""

from collections import Counter

from bank_schema import (DIFFICULTY_TAGS, FAILURE_MODES, SCHEMA_VERSION,
                         validate_card)
from schema import extract_json

import json

from bank_db import DuplicateTask, InvalidCard

_TAGS_SORTED = sorted(DIFFICULTY_TAGS)
_MODES_SORTED = sorted(FAILURE_MODES)


def pick_targets(db) -> tuple[int, list[str]]:
    """DB 현황에서 가장 빈약한 (레벨, 태그 3개)를 다음 목표로 고른다."""
    tasks = db.list_tasks()
    level_counts = Counter(t["difficulty_level"] for t in tasks)
    tag_counts = Counter(tag for t in tasks for tag in t.get("difficulty_tags", []))
    # 레벨 1~5 중 가장 적게 채워진 것 (동률이면 낮은 레벨)
    target_level = min(range(1, 6), key=lambda lv: (level_counts.get(lv, 0), lv))
    # 가장 적게 쓰인 태그 3개
    target_tags = sorted(_TAGS_SORTED,
                         key=lambda tg: (tag_counts.get(tg, 0), tg))[:3]
    return target_level, target_tags


def build_prompt(target_level: int, target_tags: list[str],
                 prior_errors: list[str] | None = None) -> str:
    """설계자에게 task_card 한 장을 요청하는 프롬프트."""
    fix = ""
    if prior_errors:
        fix = ("\n이전 출력이 검증에 실패했다. 아래 문제를 모두 고쳐 다시 출력하라.\n"
               + "\n".join(f"- {e}" for e in prior_errors) + "\n")
    return f"""너는 저가 코딩 모델의 한계를 측정하기 위한 실험 과제를 설계한다.
Python 멀티파일 CLI 도구 과제 한 개를 JSON으로 설계하라. 제약:

- 언어 Python, 표준 라이브러리만. 외부 패키지 금지.
- 무조건 멀티파일 (required_files 2개 이상). 대화형 stdin 입력 금지.
- 난이도 레벨: {target_level} (1 단순~5 장기루프 한계).
- 다음 측면을 우선 겨냥하라: {", ".join(target_tags)}.

difficulty_tags는 아래 고정 어휘에서만 고른다 (동의어·신규어 금지):
{", ".join(_TAGS_SORTED)}

expected_failure_modes도 아래 고정 어휘에서만:
{", ".join(_MODES_SORTED)}
{fix}
정확히 이 키들을 가진 JSON 객체 하나만 출력하라 (코드펜스 안에):
{{
  "source_model": "gemma-31b",
  "title": "짧은 영어 제목",
  "goal": "한국어 한 줄 목표",
  "difficulty_level": {target_level},
  "difficulty_tags": ["고정어휘에서 2~4개"],
  "expected_failure_modes": ["고정어휘에서 1~3개"],
  "acceptance_criteria": ["검증 가능한 수용기준 3개 이상"],
  "required_files": ["main.py", "...", "최소 2개"],
  "test_oracle": "어떻게 통과를 판정하나 (예: pytest 전체 통과)",
  "anti_goals": ["하지 말아야 할 것"],
  "notes_for_evaluator": "채점자가 볼 핵심 한 줄",
  "design_quality_score": null
}}"""


def _parse_card(text: str) -> tuple[dict | None, list[str]]:
    raw = extract_json(text)
    if raw is None:
        return None, ["no JSON object found in response"]
    try:
        card = json.loads(raw)
    except json.JSONDecodeError as err:
        return None, [f"JSON parse error: {err}"]
    errors = validate_card(card)
    if errors:
        return None, errors
    return card, []


def generate_cards(db, designer, count: int, parse_retries: int = 1) -> dict:
    """count장 생성 시도. 통계 dict 반환.

    stats: requested / inserted / duplicate / invalid + ids + last_errors.
    """
    stats = {"requested": count, "inserted": 0, "duplicate": 0,
             "invalid": 0, "ids": [], "last_errors": []}
    for _ in range(count):
        target_level, target_tags = pick_targets(db)
        prior_errors: list[str] | None = None
        card = None
        for attempt in range(parse_retries + 1):
            text = designer.design(build_prompt(target_level, target_tags,
                                                prior_errors))
            card, errors = _parse_card(text)
            if card is not None:
                break
            prior_errors = errors
        if card is None:
            stats["invalid"] += 1
            stats["last_errors"] = prior_errors or []
            continue
        try:
            tid = db.insert_task(card)
            stats["inserted"] += 1
            stats["ids"].append(tid)
        except DuplicateTask:
            stats["duplicate"] += 1
        except InvalidCard as err:
            stats["invalid"] += 1
            stats["last_errors"] = err.errors
    return stats


def main(argv=None) -> int:
    """CLI: python bank_generate.py [N]  — 31B로 N장 생성 (기본 50)."""
    import sys
    args = argv if argv is not None else sys.argv[1:]
    count = int(args[0]) if args else 50
    from bank_db import BankDB
    from bank_llm import GemmaDesigner

    designer = GemmaDesigner()
    with BankDB() as db:
        before = db.count()
        stats = generate_cards(db, designer, count)
        after = db.count()
    print(f"[OK] requested={stats['requested']} inserted={stats['inserted']} "
          f"duplicate={stats['duplicate']} invalid={stats['invalid']} "
          f"(DB {before} -> {after})")
    if stats["last_errors"]:
        print("[WARN] last validation errors:", "; ".join(stats["last_errors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
