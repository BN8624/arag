# 진짜 frontier 카드(결정19 B): select-best도 cap 안에 못 깨는 깊이-heavy 카드 — 엄격 검사 다수
"""select-best(retry+선택)가 L4-5를 1~2번에 깨버려, 측정도구(카드)가 약함이 드러남(결정19).
→ per-attempt 통과확률을 확 낮춘 카드: 단일도메인 깊이 + 엣지케이스 빽빽 + 한 번에 다 맞아야
하는 엄격 독립 검사 다수. T-7식 넓이(시스템 얽힘)가 아니라 깊이로 어렵게.

difficulty_level은 스키마가 1~5만 허용 → 5로 두되 난이도 근거 아님(결정17). 실제 난이도는
통과율로 사후 확정. required_behaviors/declared_dependency로 의도복잡도 기록.

사용: python bank_cards_l6.py
"""

from bank_db import BankDB, DuplicateTask

SOURCE = "human_seeded"

CARDS = [
    {
        "source_model": SOURCE,
        "title": "Mini formula spreadsheet engine (deterministic)",
        "goal": "미니 수식 스프레드시트. --input 경로의 텍스트(각 줄 'A1=값또는수식')를 읽어 "
                "각 셀을 계산한다. 수식은 +,-,*,/ 와 괄호, 셀 참조(A1,B2)를 지원하고 사칙연산 "
                "우선순위를 지킨다. 셀 간 의존 순서대로 평가하며, 순환참조는 무한루프 없이 "
                "탐지해 보고하고, 0으로 나누면 해당 셀을 ERROR로, 빈/없는 셀 참조는 0으로 "
                "취급한다. --cell A1 이면 그 셀 값만, 없으면 전체 셀과 값을 정렬해 출력한다. "
                "대화형 입력 없이 인자/파일만 사용한다.",
        "difficulty_level": 5,
        "difficulty_tags": ["parser_logic", "numeric_precision", "multi_file_contract",
                            "error_handling", "context_heavy"],
        "expected_failure_modes": ["parser_boundary_error", "missing_edge_case",
                                   "numeric_tolerance_error", "signature_drift",
                                   "import_mismatch"],
        "acceptance_criteria": [
            "숫자 셀과 수식 셀을 모두 파싱한다",
            "곱셈/나눗셈이 덧셈/뺄셈보다 먼저 계산된다(우선순위)",
            "괄호로 우선순위를 바꿀 수 있다",
            "셀 참조(A1 등)가 다른 셀 값으로 해소된다",
            "다단계 의존 사슬(A=B+1, B=C*2, C=3)이 올바른 순서로 평가된다",
            "순환참조(A=B, B=A)를 무한루프 없이 탐지해 보고한다",
            "0으로 나누는 셀은 ERROR로 표시된다",
            "빈 셀/없는 셀 참조는 0으로 취급된다",
            "잘못된 수식은 친화적 에러를 낸다(크래시 금지)",
            "--cell A1 은 그 셀의 계산값만 출력한다",
            "같은 입력에 대해 출력이 결정적이다",
        ],
        "required_files": ["main.py", "tokenizer.py", "evaluator.py", "grid.py"],
        "test_oracle": "pytest로 우선순위·괄호·참조해소·의존순서·순환탐지·0나눗셈·빈셀·"
                       "잘못된수식 처리를 각각 검증(다수의 독립 단언)",
        "anti_goals": ["대화형 input() 금지", "외부 패키지 금지", "eval() 사용 금지(직접 파싱)"],
        "notes_for_evaluator": "깊이-frontier. 독립 검사 11개를 한 번에 다 맞춰야 통과 → "
                               "per-attempt 확률이 낮아 select-best도 cap 안에 못 깰 것으로 기대.",
        "required_behaviors": 11,
        "declared_dependency": 4,
        "state_required": False,
        "spec_complete": True,
        "oracle_verified": False,
    },
    {
        "source_model": SOURCE,
        "title": "Mini regex matcher (subset, deterministic)",
        "goal": "미니 정규식 매처. --pattern 과 --text 를 받아 패턴이 텍스트와 매칭되는지 "
                "판정한다. 지원: 리터럴 문자, '.'(임의 한 글자), '*'(직전 요소 0회 이상), "
                "'?'(직전 요소 0~1회), 문자클래스 '[a-z]'와 '[abc]', 앵커 '^'(시작) '$'(끝). "
                "재귀/백트래킹으로 정확히 매칭하고, 매칭 여부와 (있으면) 매칭 구간을 출력한다. "
                "정규식 표준 라이브러리(re)는 쓰지 말고 직접 구현한다. 대화형 입력 금지.",
        "difficulty_level": 5,
        "difficulty_tags": ["parser_logic", "multi_file_contract", "error_handling",
                            "context_heavy", "regression_sensitive"],
        "expected_failure_modes": ["parser_boundary_error", "missing_edge_case",
                                   "signature_drift", "import_mismatch",
                                   "regression_introduced"],
        "acceptance_criteria": [
            "리터럴 문자열이 정확히 매칭/불매칭된다",
            "'.'이 임의의 한 글자와 매칭된다",
            "'*'이 직전 요소의 0회 이상 반복과 매칭된다",
            "'?'이 직전 요소의 0~1회와 매칭된다",
            "문자클래스 [a-z] 범위가 매칭된다",
            "문자클래스 [abc] 집합이 매칭된다",
            "'^' 앵커가 문자열 시작을 강제한다",
            "'$' 앵커가 문자열 끝을 강제한다",
            "'a*' 가 빈 문자열에도 매칭된다(0회)",
            "'.*' 같은 탐욕적 패턴이 올바르게 처리된다",
            "잘못된 패턴(닫히지 않은 [ 등)은 친화적 에러를 낸다",
            "re 모듈 없이 직접 구현되어 결정적으로 동작한다",
        ],
        "required_files": ["main.py", "compiler.py", "matcher.py"],
        "test_oracle": "pytest로 각 메타문자(.*?[]^$)·빈매칭·탐욕·잘못된패턴을 독립 단언으로 검증",
        "anti_goals": ["대화형 input() 금지", "re 모듈 사용 금지", "외부 패키지 금지"],
        "notes_for_evaluator": "깊이-frontier. 메타문자 상호작용(*,?,앵커,클래스)이 빽빽해 "
                               "한 번에 다 맞추기 어렵다 → select-best 저항 기대.",
        "required_behaviors": 12,
        "declared_dependency": 3,
        "state_required": False,
        "spec_complete": True,
        "oracle_verified": False,
    },
]


def main() -> int:
    inserted, skipped = [], []
    with BankDB() as db:
        for card in CARDS:
            try:
                tid = db.insert_task(card)
                inserted.append((tid, card["title"]))
            except DuplicateTask as e:
                skipped.append((card["title"], str(e)))
        total = db.count()
    for tid, title in inserted:
        print(f"[OK] {tid}  {title}")
    for title, why in skipped:
        print(f"[SKIP] {title} - {why}")
    print(f"[DONE] inserted={len(inserted)} skipped={len(skipped)} total={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
