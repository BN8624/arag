# 모듈식 RPG 카드(PAMPHLET.md 기반): 첫 모듈 = 상태이상 엔진(임의 상호작용 매트릭스)
"""PAMPHLET.md의 모듈을 카드로 시드. 카드 goal은 계약+규칙+시그니처를 자체포함(모델은 goal만 봄).
신규 임의규칙 = frontier 측정, 동시에 나중 조립용 재사용 모듈. 결정19 B.

사용: python bank_cards_rpg.py
"""

from bank_db import BankDB, DuplicateTask

SOURCE = "human_seeded"

CARDS = [
    {
        "source_model": SOURCE,
        "title": "RPG module: status-effect engine with custom interaction matrix",
        "goal": (
            "임의규칙 자동전투 RPG의 '상태이상 엔진' 모듈을 만든다(결정적, stdlib만, "
            "대화형 입력 금지). 공유 데이터 계약을 *정확히* 따른다.\n"
            "Entity(dataclass): id:str, name:str, team:str, max_hp:int, hp:int, atk:int, "
            "defense:int, spd:int, gauge:float=0, statuses:list, last_skill:str|None=None.\n"
            "Status(dataclass): type:str('burn'|'freeze'|'poison'|'shock'), turns:int, stacks:int=1.\n"
            "Event:dict {'kind':str,'actor':str|None,'target':str|None,'value':int,'detail':str}.\n"
            "구현할 함수(시그니처 고정): "
            "apply_status(target:Entity, stype:str, turns:int, stacks:int=1)->list[Event] ; "
            "tick_start(e:Entity)->list[Event] ; tick_end(e:Entity)->list[Event] ; "
            "incoming_multiplier(e:Entity)->float.\n"
            "규칙: 화상=턴시작 시 현재 HP의 5%(내림) 피해·3턴·매턴 turns-1(tick_start). "
            "중독=턴끝 고정 8*stacks 피해·최대5스택·매턴 stacks-1(0이면 제거)(tick_end). "
            "감전=incoming_multiplier가 1.25 반환(없으면 1.0, 중첩 안 함). 빙결=다음 행동 스킵용 표식.\n"
            "상호작용 매트릭스(apply_status 부여 시점 판정): "
            "(1)대상이 화상 보유 중 빙결 부여 → 빙결 무효(적용 안 함). "
            "(2)대상이 빙결 보유 중 화상 부여 → 빙결 제거 후 화상 적용. "
            "(3)부여 후 화상과 빙결을 동시 보유하면 → 둘 다 제거 + '증발' 즉발 30 피해(kind 'evaporate'). "
            "(4)대상이 감전 보유 중 중독 부여 → 부여 후 중독 stacks 즉시 ×2(상한 5).\n"
            "모든 변화는 Event로 기록. HP는 0 미만으로 안 내려가게(0에서 멈춤)."
        ),
        "difficulty_level": 5,
        "difficulty_tags": ["multi_file_contract", "numeric_precision",
                            "context_heavy", "regression_sensitive", "error_handling"],
        "expected_failure_modes": ["signature_drift", "import_mismatch",
                                   "missing_edge_case", "numeric_tolerance_error",
                                   "regression_introduced"],
        "acceptance_criteria": [
            "Entity/Status 계약과 4개 함수 시그니처를 정확히 구현한다",
            "tick_start가 화상 보유 시 현재 HP의 5%(내림) 피해를 주고 turns를 1 줄인다",
            "tick_end가 중독 보유 시 8*stacks 피해를 주고 stacks를 1 줄인다(0이면 제거)",
            "중독 stacks는 5를 넘지 않는다",
            "incoming_multiplier가 감전 시 1.25, 아니면 1.0을 반환한다",
            "화상 보유 중 빙결 부여는 무효(빙결이 안 붙는다)",
            "빙결 보유 중 화상 부여는 빙결을 제거하고 화상을 붙인다",
            "감전 보유 중 중독 부여는 중독 stacks를 즉시 2배로 만든다(상한 5)",
            "동시 보유 시 증발 규칙으로 둘 다 제거되고 30 즉발 피해가 들어간다",
            "모든 상태 변화가 Event로 기록되고 HP는 0 미만으로 내려가지 않는다",
        ],
        "required_files": ["entities.py", "status.py"],
        "test_oracle": "pytest로 화상/중독 tick·스택상한·감전배수·매트릭스 4규칙·증발·HP하한을 "
                       "각각 독립 단언(다수)",
        "anti_goals": ["대화형 input() 금지", "외부 패키지 금지", "전투루프/스킬은 이 모듈 밖(범위 외)"],
        "notes_for_evaluator": "PAMPHLET 시스템1. 임의 상호작용 매트릭스가 신규성(외울 수 없음). "
                               "독립 검사 10개 + 부여순서 의존 → select-best 저항 기대.",
        "required_behaviors": 10,
        "declared_dependency": 4,
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
