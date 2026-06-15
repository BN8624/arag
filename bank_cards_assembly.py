# 조립 카드(PAMPHLET 통합): status×skills×combat을 한 판으로 엮는 통합 frontier 카드
"""결정20: 단일 모듈은 select-best가 다 깬다. 진짜 frontier = 여러 시스템이 여러 턴 함께
돌며 동시에 맞아야 하는 '창발적 통합'. 이 카드는 PAMPHLET 전체 규칙 + 4개 고정 시나리오 파티
+ 골든 결과(winner/turns/final_hp)를 goal에 자체포함한다(모델은 goal만 봄).

후자 노선: 파티는 데이터로 박는다(RNG 재현 요구 안 함 — 그건 통합과 무관한 트리비아).
검수 반영(2026-06-15):
- 발견1: HP 0 클램프를 goal에 명시(오버킬 12회 관측 → 클램프 없으면 음수 final_hp = 가짜 FAIL).
- 발견2: 확장(B). freeze/poison/shock 부여 스킬을 레퍼런스에 추가하고, 매트릭스·DoT·감전·빙결스킵이
  *실제로 골든에서 발동*하는 시드(53/3/0/45)를 스캐너로 골라 시나리오로 박음. 10개 현상 전부 커버.
- 발견3: 안 걸리는 문구(이월 2회행동·spd동률 타이브레이크) 정리. 대신 실제 작동하는
  '행동마다 재평가 + 사망한 준비자는 행동 안 함'을 명시.
모호점(턴=행동단위·스킵포함)은 goal에 명시로 못 박아 가짜 MODEL_FAIL 차단.

골든 출처: game/(레퍼런스, test_reference 14/14). scenario 1/2/3/4 = seed 53/3/0/45.

사용: python bank_cards_assembly.py
"""

from bank_db import BankDB, DuplicateTask

SOURCE = "human_seeded"

GOAL = r"""임의규칙 자동전투 RPG 한 판을 끝까지 돌리는 '통합' CLI를 만든다(결정적, stdlib만,
대화형 input() 금지, eval 금지). 여러 시스템(상태이상·스킬콤보·템포턴제 전투)이 한 전투에서
함께 맞물려야 한다. 아래 규칙을 *정확히* 따르고, 4개 고정 시나리오를 정확한 골든 결과로 재현하라.

== 공유 데이터 계약 ==
Entity(dataclass): id:str, name:str, team:str('hero'|'enemy'), max_hp:int, hp:int(0이하=사망),
  atk:int, defense:int, spd:int, gauge:float=0, statuses:list, last_skill:str|None=None.
Status(dataclass): type:str('burn'|'freeze'|'poison'|'shock'), turns:int, stacks:int=1.

== 피해 공통식 (모든 피해 스킬 공유) ==
dmg = max(1, atk + skill_base - target.defense). 대상이 감전(shock) 보유면 dmg에 ×1.25(내림).
**모든 피해는 hp를 0 미만으로 내리지 않는다(0에서 멈춤). 사망한 엔티티의 final hp는 정확히 0이다.**

== 상태이상 ==
- 화상 burn: 턴 *시작* 시 현재 HP의 5%(내림) 피해, 3턴, 매 턴 turns-1(0이면 제거).
- 빙결 freeze: 다음 행동 1회 스킵, 1턴.
- 중독 poison: 턴 *끝* 고정 8*stacks 피해, 최대 5스택, 매 턴 stacks-1(0이면 제거).
- 감전 shock: 받는 피해 ×1.25(내림), 2턴.
상호작용 매트릭스(부여 시점 판정):
- 화상 보유 + 빙결 부여 시도 → 빙결 무효(안 붙음).
- 빙결 보유 + 화상 부여 시도 → 빙결 제거 후 화상 적용.
- 부여 후 화상과 빙결 동시 보유 → 둘 다 제거 + '증발' 즉발 30 피해(위 두 규칙 때문에 보통 안 생기나,
  외부 강제부여 정리용).
- 감전 보유 + 중독 부여 시도 → 부여 후 중독 stacks 즉시 ×2(상한 5).

== 스킬 표 ==
각 피해 스킬은 위 피해 공통식을 쓴다. 상태부여는 피해 적용 *후* 매트릭스를 거쳐 붙는다.
- "ignite": base 5 + target에 화상 부여.
- "detonate": base 20. 단, actor.last_skill=="ignite"이면 base 50 + 화상 부여.
- "charge": 피해 0, 자기 강화 표식(다음 연계타용).
- "combo_strike": base 12. 단, actor.last_skill=="charge"이면 2회 타격.
- "frost": base 4 + target에 빙결 부여(1턴).
- "venom": base 3 + target에 중독 부여(turns 3, stacks 2).
- "shock_bolt": base 6 + target에 감전 부여(2턴). 부여한 그 타격엔 감전배수 미적용(다음 타격부터).
콤보 사슬: 각 엔티티 last_skill 기억. *스킬 외 사건*(피격으로 실제 피해를 받음, 빙결 스킵)으로
끊기면 None. 행동을 마치면 actor.last_skill = 방금 쓴 스킬.

== 템포 턴제 + AI(전부 결정적) ==
- 매 틱: 모든 생존 엔티티 gauge += spd.
- 그 틱 안에서 gauge>=100인 생존자가 있으면 우선순위 1명이 행동한다. 행동하면 그 즉시 gauge -= 100
  (초과분 이월, 0 리셋 아님). **행동할 때마다 생존·gauge를 다시 평가해** 다음 1명을 고른다(먼저
  행동한 쪽이 다른 준비자를 죽이면, 그 죽은 엔티티는 행동하지 않는다). 더 이상 gauge>=100인
  생존자가 없으면 다음 틱으로 넘어간다.
- 우선순위: spd 큰 쪽; 동률이면 hp 낮은 쪽; 그래도 동률이면 등록 순서(heroes 먼저, 시나리오에
  나열된 순서).
- 한 엔티티의 한 행동 처리 순서: (a) tick_start(화상 피해) → (b) 화상으로 죽었으면 그 행동 끝
  (단 gauge는 -=100), 아니면 빙결이면 [행동 스킵 + gauge=0 + freeze turns-1 + last_skill=None],
  빙결 아니면 [gauge-=100 → 대상 선택 → 스킬 1개 해소] → (c) tick_end(중독 피해+감쇠, 감전 턴 감쇠).
  화상 tick(a)은 빙결이어도 발생한다. tick_end는 그 행동이 적팀을 전멸시켰더라도 그 엔티티에 대해 실행.
- AI 대상: 상대 팀 생존자 중 HP 최저(동률이면 등록 인덱스 낮은 쪽).
- AI 스킬: 각 엔티티의 skills 리스트를 로테이션 순환(행동마다 다음 스킬, 인덱스는 행동할 때만 +1).
- 한쪽 팀 전멸 시 종료. max_turns(=100) 초과 시 무승부('draw').

== 턴(turns)의 정의 — 정확히 ==
turns는 **엔티티가 행동할 차례를 받은 횟수**다. 빙결로 스킵한 차례도 +1로 센다. tick 수가 아니다
(spd<100이라 초기 여러 틱은 아무도 행동 못 해 turns가 0인 채로 지나간다). max_turns는 이 turns 상한.

== CLI / 출력 포맷 — 정확히 ==
실행: `python main.py --scenario N`  (N ∈ {1,2,3,4}). 각 시나리오는 아래 고정 파티를 만들어
한 판을 돌린 뒤, 정확히 이 포맷으로(소문자, 콜론+공백) stdout에 출력한다:
  winner: <hero|enemy|draw>
  turns: <정수>
  그 다음 등록 순서대로 각 엔티티 한 줄씩: `<id>: <남은 hp>`  (heroes 먼저, 그 뒤 enemies)

== 고정 시나리오 파티 (id, name, team, max_hp, atk, defense, spd, skills) ==
파티는 이 데이터를 그대로 코드에 박는다(무작위/seed로 생성하지 말 것). hp 시작값=max_hp.

[scenario 1]  (2 heroes vs 3 enemies)
  hero1  Tank  hero  140 12 9  7  [charge, combo_strike, venom]
  hero2  Volt  hero  85  16 3  15 [shock_bolt, venom, combo_strike]
  enemy1 Imp   enemy 60  15 2  14 [ignite, frost, detonate]
  enemy2 Golem enemy 160 14 11 5  [combo_strike, charge, frost]
  enemy3 Orc   enemy 120 17 6  8  [shock_bolt, detonate, combo_strike]
[scenario 2]  (2 vs 2)
  hero1  Volt  hero  85  16 3  15 [shock_bolt, venom, combo_strike]
  hero2  Tank  hero  140 12 9  7  [charge, combo_strike, venom]
  enemy1 Golem enemy 160 14 11 5  [combo_strike, charge, frost]
  enemy2 Imp   enemy 60  15 2  14 [ignite, frost, detonate]
[scenario 3]  (3 vs 3)
  hero1  Pyro  hero  90  18 4  12 [ignite, detonate, combo_strike]
  hero2  Frost hero  100 14 6  10 [frost, ignite, combo_strike]
  hero3  Volt  hero  85  16 3  15 [shock_bolt, venom, combo_strike]
  enemy1 Golem enemy 160 14 11 5  [combo_strike, charge, frost]
  enemy2 Orc   enemy 120 17 6  8  [shock_bolt, detonate, combo_strike]
  enemy3 Imp   enemy 60  15 2  14 [ignite, frost, detonate]
[scenario 4]  (3 vs 3)
  hero1  Tank  hero  140 12 9  7  [charge, combo_strike, venom]
  hero2  Frost hero  100 14 6  10 [frost, ignite, combo_strike]
  hero3  Pyro  hero  90  18 4  12 [ignite, detonate, combo_strike]
  enemy1 Imp   enemy 60  15 2  14 [ignite, frost, detonate]
  enemy2 Orc   enemy 120 17 6  8  [shock_bolt, detonate, combo_strike]
  enemy3 Goblin enemy 70 13 3  11 [venom, combo_strike]

== 골든 결과 (반드시 정확히 일치) ==
[scenario 1] winner: enemy turns: 23  hero1: 0  hero2: 0  enemy1: 0   enemy2: 160 enemy3: 11
[scenario 2] winner: hero  turns: 17  hero1: 23 hero2: 140 enemy1: 0  enemy2: 0
[scenario 3] winner: hero  turns: 19  hero1: 90 hero2: 100 hero3: 20  enemy1: 0 enemy2: 0 enemy3: 0
[scenario 4] winner: hero  turns: 29  hero1: 18 hero2: 0  hero3: 0    enemy1: 0 enemy2: 0 enemy3: 0

오라클은 위 골든의 정확 일치다(winner + turns + 엔티티별 final hp). 너의 acceptance_criteria와
criteria_checks는 각 시나리오마다 이 정확한 출력 값을 단언해야 한다(라벨만이 아니라 골든 숫자까지).
멀티파일로 분해하라(상태이상 / 스킬 / 전투 / 진입점)."""

CARDS = [
    {
        "source_model": SOURCE,
        "title": "RPG assembly: full battle integration (status x skills x tempo combat)",
        "goal": GOAL,
        "difficulty_level": 5,
        "difficulty_tags": ["multi_file_contract", "numeric_precision",
                            "context_heavy", "regression_sensitive",
                            "cli_arg_surface"],
        "expected_failure_modes": ["signature_drift", "import_mismatch",
                                   "missing_edge_case", "numeric_tolerance_error",
                                   "regression_introduced"],
        "acceptance_criteria": [
            "멀티파일로 분해되고(상태이상/스킬/전투/진입점) 서로 import해 실제로 호출한다",
            "python main.py --scenario 1 이 골든(winner enemy, turns 23, enemy2 160/enemy3 11 외 0)을 정확히 출력한다",
            "python main.py --scenario 2 이 골든(winner hero, turns 17, hero1 23/hero2 140 외 0)을 정확히 출력한다",
            "python main.py --scenario 3 이 골든(winner hero, turns 19, hero1 90/hero2 100/hero3 20 외 0)을 정확히 출력한다",
            "python main.py --scenario 4 이 골든(winner hero, turns 29, hero1 18 외 0)을 정확히 출력한다",
            "빙결스킵·중독틱·감전배수·매트릭스(화상이 빙결막기 등)·콤보가 골든과 어긋나지 않게 통합된다",
        ],
        "required_files": ["entities.py", "status.py", "skills.py", "combat.py", "main.py"],
        "test_oracle": "각 시나리오(1~4) python main.py --scenario N 출력의 winner/turns/엔티티별 "
                       "final hp가 박힌 골든과 정확히 일치하는지 단언. 골든=game/ 레퍼런스(seed 53/3/0/45) 산출.",
        "anti_goals": ["대화형 input() 금지", "외부 패키지 금지", "무작위/seed로 파티 생성 금지(파티는 고정 데이터)",
                       "단일파일 금지"],
        "notes_for_evaluator": "PAMPHLET 전체 조립. 결정20 통합 frontier 카드 — 단일 모듈은 select-best가 "
                               "이미 깸. 검수(2026-06-15) 반영: HP클램프 명시(가짜FAIL 차단), 확장B로 "
                               "freeze/poison/shock/매트릭스/감전배수/빙결스킵이 실제 골든에서 발동(시드 스캔, "
                               "10현상 커버). scenario 1/2/3/4=seed 53/3/0/45. 골든은 game/(test 14/14)에서 생성, 사람 검증됨. "
                               "4 시나리오(승자/크기 다양) 정확 일치라 우연 PASS 사실상 0.",
        "required_behaviors": 6,
        "declared_dependency": 8,
        "state_required": True,
        "spec_complete": True,
        "oracle_verified": True,
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
