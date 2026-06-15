# PAMPHLET.md — 모듈식 RPG "임의규칙 자동전투" 규칙서 + 데이터 계약

> 목적 두 가지. (1) **frontier 측정**: 외울 수 없는 임의 규칙 → 모델이 진짜 추론해야 하는
> 어려운 카드. (2) **재사용 산출물**: 모듈을 쌓으면 진짜 RPG 한 판이 돈다(껍데기=에셋은 나중).
> 각 모듈 = 카드 1장. 카드 goal엔 이 문서의 *해당 부분을 자체포함*한다(모델은 goal만 봄).
> 결정 17~19 노선: 결정적·stdlib·비대화형. 난이도는 통과율로 사후 확정.

## 0. 불변 원칙
- **결정적**: 모든 무작위는 `--seed` 고정 RNG로만. 같은 입력 → 같은 출력·같은 이벤트 로그.
- stdlib만, `input()` 금지, CLI 인자/파일만. `eval` 금지.
- 모든 모듈은 **이벤트 리스트**를 내보내 검증 가능하게 한다(아래 Event 계약).

## 1. 데이터 계약 (모든 모듈이 공유 — 이게 조립을 가능케 함)
```
Entity(dataclass):
  id: str            # 고유 식별자 (예: "hero1")
  name: str
  team: str          # "hero" | "enemy"
  max_hp: int
  hp: int            # 0 이하 = 사망
  atk: int
  defense: int       # 'def'는 예약어 → defense
  spd: int
  gauge: float = 0   # 행동게이지. 100 도달 시 행동
  statuses: list[Status]   # 기본 []
  last_skill: str | None = None

Status(dataclass):
  type: str          # "burn" | "freeze" | "poison" | "shock"
  turns: int         # 남은 지속 턴
  stacks: int = 1    # 중독 전용(그 외 1)

Event: dict
  {"kind": str, "actor": str|None, "target": str|None, "value": int, "detail": str}
  # kind 예: "status_apply","status_tick","evaporate","skill","combo","death","turn"
```

## 2. 세계 규칙 (신규·임의 — 외울 레퍼런스 없음)

### 2.1 상태이상 (모듈: status.py)
- **화상 burn**: 턴 *시작* 시 현재 HP의 5%(내림) 피해, 3턴, 매 턴 turns−1.
- **빙결 freeze**: 다음 행동 1회 스킵, 1턴.
- **중독 poison**: 턴 *끝* 고정 8×stacks 피해, 최대 5스택, 매 턴 stacks−1(0 되면 제거).
- **감전 shock**: 받는 피해 ×1.25, 2턴.

**상호작용 매트릭스(부여 시점에 판정):**
- 대상이 화상 보유 + 빙결 부여 시도 → **빙결 무효**(불이 얼음 막음).
- 대상이 빙결 보유 + 화상 부여 시도 → **빙결 제거 후 화상 적용.**
- 부여 후 대상이 화상 **그리고** 빙결을 동시 보유하게 되면 → **둘 다 제거 + "증발" 즉발 30 피해**
  (Event kind "evaporate"). (위 두 무효/제거 규칙이 먼저라 보통은 안 생기지만, 외부에서 강제
  부여된 경우의 정리 규칙.)
- 대상이 감전 보유 + 중독 부여 시도 → **부여 후 중독 stacks 즉시 ×2**(상한 5).

### 2.2 템포 턴제 (모듈: combat.py)
- 매 틱 모든 생존 엔티티 gauge += spd. **gauge ≥ 100 인 엔티티가 행동.**
- 행동 후 **gauge -= 100**(초과분 이월, 0 리셋 아님).
- 동시(≥100) 다수면 타이브레이크 **3단계**: ① spd 큰 쪽 → ② 같으면 hp 낮은 쪽 →
  ③ 같으면 등록 순서(heroes 먼저, 각 리스트 인덱스 순).
- 빙결 상태로 행동 차례가 오면 **행동 스킵 + gauge=0 + freeze turns−1**.
- 한쪽 팀 전멸 시 종료. max_turns 초과 시 무승부.

### 2.3 스킬/콤보 (모듈: skills.py)
- 기본 피해 계산: `dmg = max(1, atk + skill.base - target.defense)` → 감전 시 ×1.25(내림).
- 각 엔티티 `last_skill` 기억. 피격·스킵 등 *스킬 외 사건*으로 끊기면 None.
- 스킬 표(임의):
  - **"점화" ignite**: target에 화상 부여. base 5.
  - **"폭발" detonate**: 단독 base 20. **actor.last_skill=="ignite"면 base 50 + 화상 부여.**
  - **"준비" charge**: 자신 강화 표식(다음 연계타 2회). base 0.
  - **"연계타" combo_strike**: base 12. **actor.last_skill=="charge"면 2회 타격.**

## 3. 모듈 지도 + 진입 시그니처 (조립 계약)
- `entities.py`: `Entity`, `Status` 정의 + `make_entity(...)->Entity`.
- `status.py`: `apply_status(target:Entity, stype:str, turns:int, stacks:int=1)->list[Event]`
  (매트릭스 적용) / `tick_start(e:Entity)->list[Event]`(화상) / `tick_end(e:Entity)->list[Event]`
  (중독) / `incoming_multiplier(e:Entity)->float`(감전).
- `skills.py`: `resolve_skill(actor:Entity, target:Entity, skill:str)->list[Event]`(콤보·피해 적용).
- `combat.py`: `next_actor(entities:list[Entity])->Entity|None`(템포) /
  `run_battle(heroes, enemies, seed:int, max_turns:int=100)->dict`(승자·턴수·생존HP·이벤트로그).

## 4. 조립 (나중)
모든 모듈이 위 계약을 지키면 `combat.run_battle`가 status·skills를 호출해 한 판을 돌린다.
조립 = 통합 카드(진입점 main.py가 파티 구성→run_battle→리포트). **여기서 모듈 간 계약 정합성이
진짜 frontier**(단일 모듈은 select-best가 깸 — 결정19).

## 5. 카드(모듈)와 측정
- 각 모듈 카드 goal = §1 계약 + 해당 §2 규칙 + 해당 §3 시그니처를 *자체포함*.
- 오라클 = seed 고정 → 함수 호출 → *정확한 HP·상태·이벤트* 단언(다수 독립 검사).
- 신규성(임의 규칙)이 어려움의 원천. select-best 저항하면 진짜 frontier 확보.
