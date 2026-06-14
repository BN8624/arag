# PLAN 2 게임/앱 카드풀 6장 시드 (card_pool_version p2-cards-v1) — 깨끗한 design_bank.sqlite에 적재
"""PLAN.md §2의 게임/앱 카드 6장을 bank 스키마(task_card.v1)로 정의·삽입한다.

모든 카드는 비대화형(stdin 금지) — 입력은 CLI 인자/파일/seed로만, stdlib만, 멀티파일.
랜덤 게임(강화·전투·리그)은 테스트 가능하게 --seed로 결정성 강제.

사용: python bank_cards_p2.py   (이미 있으면 중복 스킵)
"""

from bank_db import BankDB, DuplicateTask

SOURCE = "human_seeded"

CARDS = [
    {
        "source_model": SOURCE,
        "title": "Number Baseball CLI (non-interactive)",
        "goal": "숫자 야구 게임. --secret 세자리 정답과 --guesses 쉼표목록을 받아 "
                "각 추측의 스트라이크/볼을 계산해 출력하고, 정답을 맞히면 몇 번째에 "
                "맞혔는지 보고한다. 대화형 입력 없이 인자만 사용한다.",
        "difficulty_level": 1,
        "difficulty_tags": ["cli_arg_surface", "error_handling"],
        "expected_failure_modes": ["argument_parsing_error", "missing_edge_case"],
        "acceptance_criteria": [
            "--secret 123 --guesses 456,789,123 형태로 인자를 받는다",
            "각 추측마다 스트라이크/볼 개수를 정확히 출력한다",
            "중복 숫자·세자리 아님 같은 잘못된 입력에 친화적 에러를 낸다",
            "정답을 맞히면 종료하고 시도 횟수를 출력한다",
        ],
        "required_files": ["main.py", "game.py"],
        "test_oracle": "pytest로 스트라이크/볼 계산과 잘못된 입력 처리를 검증",
        "anti_goals": ["대화형 input() 금지", "웹/서버 금지", "외부 패키지 금지"],
        "notes_for_evaluator": "L1 하네스 점검용. 기본 입출력·규칙·입력검증이 깨끗이 나오는지.",
    },
    {
        "source_model": SOURCE,
        "title": "Quiz Game CLI with JSON question loading",
        "goal": "퀴즈 게임. --questions 경로의 JSON(문제/보기/정답)을 로드하고 "
                "--answers 쉼표목록(보기 번호)으로 채점해 점수와 오답 목록을 출력한다. "
                "문제 파일이 없거나 형식이 틀리면 친화적으로 실패한다.",
        "difficulty_level": 2,
        "difficulty_tags": ["parser_logic", "schema_validation", "error_handling"],
        "expected_failure_modes": ["schema_violation", "missing_edge_case",
                                   "argument_parsing_error"],
        "acceptance_criteria": [
            "--questions quiz.json --answers 1,3,2 형태로 받는다",
            "정답 수와 점수를 정확히 계산해 출력한다",
            "오답 문항의 번호와 정답을 출력한다",
            "파일 없음·잘못된 JSON 구조에 친화적 에러를 낸다",
        ],
        "required_files": ["main.py", "loader.py", "scorer.py"],
        "test_oracle": "pytest로 채점 정확성과 잘못된 문제파일 처리 검증",
        "anti_goals": ["대화형 input() 금지", "외부 패키지 금지", "DB 금지"],
        "notes_for_evaluator": "외부 데이터 파일 로딩+검증. 단순 게임보다 한 단계.",
    },
    {
        "source_model": SOURCE,
        "title": "Rock-Paper-Scissors League with record persistence",
        "goal": "가위바위보 리그. --players 목록과 --rounds, --seed를 받아 라운드로빈 "
                "경기를 시뮬레이션하고 승/패/무 전적을 JSON 파일에 누적 저장한다. "
                "--standings로 저장된 전적을 읽어 순위를 출력한다.",
        "difficulty_level": 2,
        "difficulty_tags": ["stateful_io", "cli_arg_surface", "error_handling"],
        "expected_failure_modes": ["state_persistence_error", "missing_edge_case",
                                   "argument_parsing_error"],
        "acceptance_criteria": [
            "--players a,b,c --rounds 10 --seed 42 로 결정적으로 경기한다",
            "승/패/무를 정확히 판정해 전적을 누적한다",
            "전적을 JSON 파일에 저장하고 다시 읽어 순위를 출력한다",
            "저장 파일이 없을 때 새로 시작하고 깨지지 않는다",
        ],
        "required_files": ["main.py", "league.py", "store.py"],
        "test_oracle": "pytest로 seed 고정 시 판정·전적 누적·저장/로드 검증",
        "anti_goals": ["대화형 input() 금지", "seed 없는 랜덤 금지", "외부 패키지 금지"],
        "notes_for_evaluator": "상태 저장/로드 능력. seed로 결정성 확보가 핵심.",
    },
    {
        "source_model": SOURCE,
        "title": "Mini shop management simulator",
        "goal": "미니 상점 경영 시뮬레이터. --commands 경로의 명령 목록(buy/sell/endday)을 "
                "읽어 돈과 재고를 갱신하고, 하루 종료 시 정산 리포트를 출력한다. "
                "돈·재고가 음수가 되지 않도록 막는다.",
        "difficulty_level": 2,
        "difficulty_tags": ["stateful_io", "parser_logic", "error_handling"],
        "expected_failure_modes": ["state_persistence_error", "missing_edge_case",
                                   "parser_boundary_error"],
        "acceptance_criteria": [
            "--commands cmds.txt 로 명령 목록을 읽어 순서대로 처리한다",
            "구매/판매 시 돈과 재고를 정확히 갱신한다",
            "돈 부족·재고 부족 구매/판매를 거부하고 음수를 막는다",
            "하루 종료 시 매출·잔액·재고 리포트를 출력한다",
        ],
        "required_files": ["main.py", "shop.py", "report.py"],
        "test_oracle": "pytest로 돈/재고 갱신, 음수 방지, 정산 리포트 검증",
        "anti_goals": ["대화형 input() 금지", "외부 패키지 금지", "웹/DB 금지"],
        "notes_for_evaluator": "상태 변화가 명확한 경영 시뮬. 실전 구조화 능력.",
    },
    {
        "source_model": SOURCE,
        "title": "Item enhancement simulator (seeded)",
        "goal": "아이템 강화 시뮬레이터. --seed, --attempts, --budget를 받아 성공확률에 "
                "따라 강화 단계를 올리거나(실패 시 단계 하락·비용 차감) 시뮬레이션하고, "
                "각 시도 로그와 최종 요약(최고단계·성공률·잔액)을 출력한다.",
        "difficulty_level": 2,
        "difficulty_tags": ["stateful_io", "numeric_precision", "cli_arg_surface"],
        "expected_failure_modes": ["numeric_tolerance_error", "state_persistence_error",
                                   "missing_edge_case"],
        "acceptance_criteria": [
            "--seed 7 --attempts 50 --budget 1000 로 결정적으로 시뮬레이션한다",
            "성공확률에 따라 단계 증가, 실패 시 단계 하락과 비용 차감을 적용한다",
            "강화 상한과 잔액 0을 넘지 않는다",
            "각 시도 로그와 최종 요약(최고단계·성공횟수·잔액)을 출력한다",
        ],
        "required_files": ["main.py", "enhancer.py", "wallet.py", "report.py"],
        "test_oracle": "pytest로 seed 고정 시 확률 적용·단계 하락·비용·상한 검증",
        "anti_goals": ["대화형 input() 금지", "seed 없는 랜덤 금지", "외부 패키지 금지"],
        "notes_for_evaluator": "확률+상태변화+멀티파일이 자연스러운 카드. seed 결정성 필수.",
    },
    {
        "source_model": SOURCE,
        "title": "Auto-battle RPG (single fight, seeded)",
        "goal": "자동 전투 RPG. 영웅 1명과 몬스터 3종 중 하나가 --seed로 결정적인 "
                "자동 전투 1회를 벌인다. 스킬 2개, 턴 기반 HP 변화, 승패 종료 조건을 "
                "구현하고 전투 리포트(승자·턴 수·남은 HP)를 출력한다. 저장은 없다.",
        "difficulty_level": 3,
        "difficulty_tags": ["multi_file_contract", "stateful_io", "numeric_precision"],
        "expected_failure_modes": ["import_mismatch", "signature_drift",
                                   "missing_edge_case", "numeric_tolerance_error"],
        "acceptance_criteria": [
            "--seed 3 --monster goblin 로 결정적 전투 1회를 수행한다",
            "HP가 0 이하가 되면 전투가 종료된다(0 이하인데 계속 공격 금지)",
            "스킬 2개의 효과와 데미지 계산이 일관되게 적용된다",
            "전투 리포트에 승자·턴 수·남은 HP가 포함된다",
        ],
        "required_files": ["main.py", "character.py", "monster.py", "skill.py",
                           "battle.py"],
        "test_oracle": "pytest로 seed 고정 시 전투 종료 조건·턴 순서·데미지·리포트 검증",
        "anti_goals": ["대화형 input() 금지", "저장/로드 금지(이번엔 범위 밖)",
                       "외부 패키지 금지"],
        "notes_for_evaluator": "멀티파일 계약(캐릭터/몬스터/스킬/전투)이 핵심. L2~3 경계.",
    },
]


def main() -> int:
    inserted, skipped = [], []
    with BankDB() as db:
        for card in CARDS:
            # 결정17 최소 스키마: 이 6장은 goal이 수용기준을 다 담음(spec_complete).
            card.setdefault("spec_complete", True)
            card.setdefault("oracle_verified", False)  # 사람 행동-검증 후속
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
