# L4-5 frontier 카드 시드 (전투/RPG 줄기 연장: L3 자동전투 → L4 파티전투 → L5 세이브 로그라이크)
"""PLAN.md §10 난이도 사다리의 L4·L5 카드 2장을 bank 스키마(task_card.v1)로 정의·삽입한다.

도메인은 L3(자동전투 RPG)과 동일하게 고정하고 복잡도만 올린다.
L4 = 파티전투(상태이상·턴순서), L5 = 세이브 로그라이크(절차생성+저장/로드+회귀).
모든 카드는 비대화형(stdin 금지), stdlib만, 멀티파일, --seed로 결정성 강제.

사용: python bank_cards_l45.py   (이미 있으면 중복 스킵)
"""

from bank_db import BankDB, DuplicateTask

SOURCE = "human_seeded"

CARDS = [
    {
        "source_model": SOURCE,
        "title": "Party auto-battle RPG with status effects (seeded)",
        "goal": "파티 자동 전투 RPG. 영웅 파티(2~3명)와 적 파티가 --seed로 결정적인 "
                "자동 전투를 벌인다. 속도 기반 턴 순서, 상태이상(독·기절·방어)이 "
                "턴마다 적용·감쇠되고, 스킬은 대상 선택 규칙을 따른다. 한쪽이 전멸하면 "
                "종료하고 전투 리포트(승리 파티·총 턴 수·생존자별 남은 HP·가한 피해)를 출력한다.",
        "difficulty_level": 4,  # 남기되 난이도 근거 아님(결정17)
        "spec_complete": True,   # goal이 수용기준을 다 담음
        "oracle_verified": False,  # 사람 행동-검증 후속(샘플)
        "difficulty_tags": ["multi_file_contract", "stateful_io", "numeric_precision",
                            "regression_sensitive", "error_handling"],
        "expected_failure_modes": ["import_mismatch", "signature_drift",
                                   "regression_introduced", "missing_edge_case",
                                   "numeric_tolerance_error"],
        "acceptance_criteria": [
            "--seed 5 --party warrior,mage --enemies goblin,goblin,orc 로 결정적 전투를 수행한다",
            "속도 기준으로 턴 순서가 매 라운드 일관되게 결정된다",
            "상태이상(독=턴당 피해, 기절=턴 스킵, 방어=피해 감소)이 정확히 적용·감쇠된다",
            "HP 0 이하 캐릭터는 행동·피격 대상에서 제외되고 한쪽 전멸 시 전투가 종료된다",
            "전투 리포트에 승리 파티·총 턴 수·생존자별 남은 HP가 포함된다",
        ],
        "required_files": ["main.py", "character.py", "party.py", "skill.py",
                           "status.py", "battle.py", "report.py"],
        "test_oracle": "pytest로 seed 고정 시 턴 순서·상태이상 적용/감쇠·전멸 종료·대상 선택·리포트 검증",
        "anti_goals": ["대화형 input() 금지", "저장/로드 금지(이번엔 범위 밖)",
                       "seed 없는 랜덤 금지", "외부 패키지 금지"],
        "notes_for_evaluator": "L4 frontier. 상태이상×턴순서×다대다 대상선택이 파일 간 계약을 "
                               "강하게 묶는다. 26B가 상태 로직에서 strain하는지가 관측 포인트.",
    },
    {
        "source_model": SOURCE,
        "title": "Save-enabled roguelike with procedural floors and meta-progression",
        "goal": "세이브 로그라이크. --seed로 절차생성된 던전 층(맵·적 배치·아이템)을 영웅이 "
                "자동 공략한다. --save 경로에 진행 상태(현재 층·HP·인벤토리·메타 자원)를 "
                "저장하고, --load로 이어서 재개한다. 사망 시 메타 자원이 누적되어 다음 "
                "회차의 시작 능력치를 강화한다(회귀). --run으로 한 회차를 자동 진행하고 "
                "리포트(도달 층·획득 메타 자원·사망 여부)를 출력한다.",
        "difficulty_level": 5,  # 남기되 난이도 근거 아님(결정17)
        "spec_complete": False,  # 오라클은 손상세이브 복구 검사, goal엔 손상 언급 없음(출제불량)
        "oracle_verified": False,
        "difficulty_tags": ["multi_file_contract", "stateful_io", "numeric_precision",
                            "regression_sensitive", "context_heavy", "schema_validation"],
        "expected_failure_modes": ["import_mismatch", "signature_drift",
                                   "state_persistence_error", "schema_violation",
                                   "regression_introduced", "missing_edge_case"],
        "acceptance_criteria": [
            "--seed 9 로 절차생성된 층(맵·적·아이템)이 같은 seed에서 항상 동일하게 재현된다",
            "--run 으로 한 회차를 자동 진행하고 도달 층·결과를 결정적으로 출력한다",
            "--save 로 현재 진행(층·HP·인벤토리·메타 자원)을 파일에 저장하고 --load 로 정확히 재개한다",
            "사망 시 메타 자원이 누적되고 다음 회차 시작 능력치에 반영된다(회귀)",
            "저장 파일이 없거나 손상됐을 때 친화적으로 실패하거나 새 회차로 시작한다",
        ],
        "required_files": ["main.py", "rng.py", "dungeon.py", "hero.py", "combat.py",
                           "inventory.py", "save.py", "meta.py", "report.py"],
        "test_oracle": "pytest로 seed 결정성·저장/로드 왕복 일치·메타 누적 반영·손상 세이브 처리 검증",
        "anti_goals": ["대화형 input() 금지", "seed 없는 랜덤 금지", "외부 패키지 금지",
                       "DB 금지(파일 저장만)"],
        "notes_for_evaluator": "L5 frontier 천장. 절차생성 결정성+저장/로드 왕복+회귀가 한 회차 "
                               "안에 맞물려야 한다. 9파일 계약·persistence가 어디서 무너지는지가 핵심.",
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
