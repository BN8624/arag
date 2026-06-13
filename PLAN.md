# PLAN.md — ARAG PLAN 2 (게임/앱 프로토타입 기반 측정)

> 지침은 [CLAUDE.md](CLAUDE.md), 진행상황은 [HANDOFF.md](HANDOFF.md),
> 진행 체크리스트는 [checklist.md](checklist.md), 결정 로그는 [context-notes.md](context-notes.md).
> 이 문서는 **앞으로 할 일과 그 명세**만 담는다. 끝난 일은 HANDOFF로 간다.

## 0. 최종 목표 (2026-06-13 재확정)

ARAG의 목표는 **엄밀한 벤치마크가 아니다.** 목표는 다음이다.

> 사용자가 대략적 밑그림을 주면, 1~2개 저가 모델이 **프로덕션급으로 업그레이드
> 가능한 작은 프로토타입**을 만들 수 있는지 확인한다.

이 과정에서 함께 본다.
- 무료/저가 모델이 어디까지 쓸 만한가.
- 오답노트·비평노트가 실제로 품질 개선에 도움이 되는가 (**핵심 비교**).
- 모델별 차이가 실제 결과물에서 드러나는가.
- 실패했을 때 다음 시도에 도움이 되는 부산물이 남는가.
- 어떤 난이도부터 상위/유료 모델이 필요한가.

→ PLAN 2는 **논문식 벤치마크가 아니라 실제 프로토타입 생산 실험**이다.

### 과했던 방향 (폐기/보류)
초기에 파일수·계약수·도메인·oracle강도 축, m×k 격자, synthetic grid, reference
구현 대량작성, 세밀 taxonomy, 신뢰구간, 셀 중단규칙까지 논의했으나 **현재 목표에
과하다** (도구가 목적을 잡아먹음, 흥미 없는 카드, 합성격자 성능≠실전 생성능력).
→ **보류.** 측정이 무거워지면 다시 꺼내되, 지금은 최소 측정으로 간다.

### 살아있는 것
- 관측 체계 0단계(`observability.py`) — 실패 분류·artifact 채점. 라벨은 §4로 단순화.
- Design Bank 모듈(`bank_*.py`) — **카드 저장소로 재사용**(생성 벤치마크용 아님).
- `--task-id` 접점, 격리 worktree(`../arag-bank`), cold/warm 격리 원칙.

---

## 1. 핵심 실험 — cold vs warm

같은 조건에서 노트 유무만 바꿔 **오답노트/비평노트의 효과**를 본다.

| 고정 | 변수 |
|---|---|
| 같은 카드 / 모델 / 예산(K=3) / 프롬프트 | cold: 노트 없음 ↔ warm: 노트 있음 |

- **cold mode**: lessons / critique_notes / evaluator_mistakes 주입 OFF.
  목적 = 순수 모델+프롬프트만의 결과.
- **warm mode**: 위 노트 주입 ON. 목적 = 누적 노트가 품질·수리횟수·실패유용성·비용에
  도움이 되는지.
- **절대 섞지 않는다.** 런마다 `mode`를 기록.

초기에는 정밀 통계보다 **방향성 확인**이 목적.

### warm이 데울 노트의 출처 (확정)
노트는 `_exploration`으로 비웠으므로 warm은 데울 내용이 없다(=cold와 같아짐).
**실행 순서**: ① cold 6런(노트 OFF) + 실패/비평/오답 후보 *수확* → ② 수확 노트
정리(기계 요약 + 최소 확인, §1.5 품질필터) → warm 저장소 적재 → ③ warm 6런
(노트 ON, **같은 카드 재시도**) → ④ cold 대비 비교(prototype_score·
failure_usefulness 개선? repair_rounds 감소? PASS/PARTIAL 증가? 비용 변화?).

> **⚠️ 이 셰이크다운은 오답노트 효과의 정식 측정이 아니다.** 같은 카드 재시도에
> cold에서 나온 노트를 쓰면 "한 번 틀리고 해설 본 뒤 다시 푸는 것"에 가까워 효과가
> **과대평가**된다. 12런의 목적은 **노트 파이프라인이 작동하는지 확인**이다 —
> cold 주입 OFF / 실패 수확 / warm 적재 / warm 주입 / 결과 기록 / 폰 감사 화면.
> 정식 일반화 효과 측정은 캠페인2(cross-card warm)에서 한다.

### 캠페인 로드맵
- **캠페인1 (= 이번 셰이크다운, same-card warm)**: cold 카드의 노트를 같은 카드
  warm에 사용. 목적 = 파이프라인 검증.
- **캠페인2 (cross-card warm)**: A 카드들에서 수확한 노트를 *비슷하지만 다른* B
  카드들에 적용(예: 숫자야구→숫자추리, 퀴즈→객관식변형, 가위바위보리그→주사위리그).
  목적 = 노트가 같은 문제 재시도뿐 아니라 **비슷한 문제에도 일반화되나** 확인.

### 1.5 warm 노트 품질 필터 (USE/HOLD/DROP)
cold 실패를 아무거나 warm에 넣으면 잘못된 비평·카드전용 과적합 패치·틀린 원인분석이
섞여 warm을 오염시킨다. 적재 전 후보를 3종으로 분류한다.
- `USE` — 다음 warm에 주입 / `HOLD` — 기록만, 주입 안 함 / `DROP` — 틀렸거나 너무
  구체적이라 버림. **기계가 자동 분류 → 폰 감사에서 사람이 변경 가능.**

---

## 2. 첫 카드풀 (게임/앱 6개)

선정 기준: 사용자가 결과를 눈으로 판단 / 흥미로운 주제 / 작은 CLI로 시작 /
확장 가능 / 멀티파일 자연 발생 / 성공·실패가 보임 / 실패 시 약점이 드러남 /
오답노트로 남길 실패가 나옴. → **업무자동화(CSV·영수증·로그) 카드는 주 카드 아님.**

| # | 카드 | 역할(난이도) | 보는 능력 |
|---|---|---|---|
| 1 | 숫자 야구 게임 CLI | L1 하네스 점검 | 입출력·게임루프·입력검증·규칙·상태 |
| 2 | 퀴즈 게임 CLI + 문제 JSON 로딩 | L1~2 데이터로딩 | JSON 로딩·구조처리·점수·오답기록·파일검증 |
| 3 | 가위바위보 리그 + 전적 저장 | L1~2 상태저장 | 반복경기·판정·전적누적·JSON 저장/로드·메뉴 |
| 4 | 미니 상점 경영 시뮬 | L2 상태/재고/돈 | 돈·재고·구매/판매·일정산·리포트 |
| 5 | 아이템 강화 시뮬 | L2 확률/상태변화 | 확률·단계·실패패널티·비용·로그·요약(멀티파일 자연) |
| 6 | 자동 전투 RPG | L2~3 멀티파일 | 캐릭터·몬스터·스킬·전투루프·HP·승패·리포트 |

- 5·6은 멀티파일 구조가 자연스럽다(item/enhancer/probability/wallet/history/cli,
  character/monster/skill/battle/balance/cli). **랜덤성 → 테스트 모드 seed/deterministic 필요.**
- 6은 범위 작게: 영웅 1·몬스터 3종·스킬 2개·전투 1회·저장 없음.
- **보류 카드**: 덱빌딩 카드전투, 방치형 자원생산 (복잡도 급상승 → L3 확장 카드로).

---

## 3. 결과 라벨 (5개, 단순)

| 라벨 | 뜻 |
|---|---|
| `PASS` | 기계 검증 통과 + 프로토타입으로 볼 결과가 나옴 |
| `PARTIAL_USEFUL` | 미완성이나 실행 가능한 부분 + 다음 개선에 쓸 실패 정보 남음 |
| `MODEL_FAIL` | 모델이 요구사항을 제대로 구현 못 함 |
| `INFRA_FAIL` | API/서버/Docker/네트워크 등 모델 능력과 무관한 실패 |
| `HARNESS_FAIL` | 카드/테스트/oracle/실행하네스/판정 로직 문제 |

> 기존 observability의 limit_type(5종)은 이 5라벨로 매핑해 단순화한다.
> `INVALID_CARD`는 당장 안 쓰고 HARNESS_FAIL에 포함(필요 시 분리).

## 4. 점수·기록 필드

초기 점수 3개만 본다. **점수는 _auto(기계 잠정) / _user(사람 확정) 2단계.**
처음엔 _user가 없어도 되고, 폰 감사에서 덮어쓴다.
- **prototype_score 0~5**: 0 없음 / 1 실행불안정 / 2 일부기능 / 3 작동하나부족 /
  4 꽤쓸만 / 5 바로확장하고싶음.
- **failure_usefulness 0~5**: 0 쓸모없음 / 1 막연 / 2 위치보임 / 3 수정방향보임 /
  4 오답노트후보 / 5 다음루프에 강하게 반영가치.
- **cost_usd**: 모델 비교·warm/cold 비교에 필요.

런마다 기록할 최소 필드.
```json
{
  "protocol_version": "p2.0",
  "protocol_fingerprint": {
    "prompt_version": "p2-prompt-v1", "card_pool_version": "p2-cards-v1",
    "label_set_version": "p2-labels-v1", "repair_budget": 3, "notes_mode": "cold"
  },
  "card_id": "L2-003", "card_name": "item_enhancement_simulator", "card_level": 2,
  "model_design": "gemma-31b", "model_impl": "gemma-26b",
  "mode": "cold", "notes_enabled": false,
  "final_label": "PASS", "failure_stage": "none", "repair_rounds": 1,
  "prototype_score_auto": 3, "prototype_score_user": null,
  "failure_usefulness_auto": 4, "failure_usefulness_user": null,
  "human_audit_status": "pending",
  "cost_usd": 0.02, "elapsed_sec": 420
}
```
`protocol_version`은 앵커, `protocol_fingerprint`는 비교 조건을 펼쳐 기록한다.
**처음부터 해시 시스템을 만들지 않는다** — 중요한 건 해시가 아니라 조건이 남는 것.
나중에 fingerprint를 문자열 해시로 접으면 됨.

## 5. 사람 감사 화면 (폰)

사용자는 코드를 안 읽으므로 런 결과는 **아이폰에서 바로 판단 가능한 산문 1화면**이어야 한다.
형식: `[카드ID] 이름 / mode → 결과 라벨 / 점수 / 비용 / 시간 / 수리 n/3 /
만든 것(파일) / 통과 / 실패 / 기계판단` + 사람 체크 3개:
`[ ] 판정 맞음  [ ] 프로토타입으로 건질 수 있음  [ ] 오답노트로 쓸 만함`.

---

## 6. 첫 단계 = 셰이크다운 (결론 아님, 장치 검증)

- 카드 6개 × {cold, warm} × 1회 = **12런.**
- 볼 것: 실행 안정성 / 라벨이 제대로 남나 / 비용·수리라운드 기록 / cold·warm 차이가
  보이나 / 폰에서 판단 가능한가 / 오답노트·비평노트 후보가 남나.
- 잘 돌면 → 카드 수·반복 수·모델 비교를 늘린다(캠페인2~).

### 구현 순서 (checklist.md가 정본)
1. 카드 6개 정의(bank 스키마로) → 2. cold/warm mode 분리(**최우선 코딩**) →
3. run metadata 필드 추가 → 4. 라벨 5개 적용 → 5. 점수 2종 기록 →
6. 폰 감사 요약 생성 → 7. 12런 실행 → 8. 결과 보고 카드/라벨/요약 포맷 수정.

> **가장 먼저 할 코딩**: cold mode에서 lessons/critique_notes 주입을 확실히 끄기
> (주입 지점 = `phase_design._load_lessons`, `phase_implement._load_notes`).
> 이게 안 되면 cold/warm 비교 자체가 무효.

## 7. 이번 단계에서 안 할 것 (스코프 보호)
full factorial grid / synthetic 벤치마크 / reference 구현 대량작성 / 세밀 taxonomy /
처음부터 m×k 반복 / 통계 엄밀성 과몰입 / 업무자동화 중심 카드풀.

## 8. 측정 실험 후보 (셰이크다운 이후, 한 번에 하나·측정 동반)

> 느낌으로 적용 금지. 베이스라인 동결 후 하나씩 전후 비교. HANDOFF "실험 기록"에 측정 남김.

1. **thinking LOW vs ON (저우선)** — 천장 조사 결과 OFF는 폐기(출력 천장이 제약 아님으로
   판명, context-notes 참조). 남은 가치는 LOW(추론 유지+폭주 억제) vs ON 품질·속도 비교뿐.
   기본 ON 유지. 실험하려면 선결: orchestrator/llm.generate에 thinking 모드 주입 배선
   (현재 미배선). 방식 (A) 전단계 동일모드 + 설계고정(--resume) + 같은 oracle.
2. **콜당 토큰·finish_reason 계측** — `llm.py`가 토큰을 런합계로만 누적, 콜당·잘림 미기록.
   추가하면 분산성 잘림이 모든 런에서 자동 관측됨. (#1보다 먼저 해도 무방, 콜 0)
3. **설계 주입 파일화 / XML 구획화** — 단, 에이전트형 코더(Claude/Codex) 투입과 묶임 →
   모델 에스컬레이션 로드맵 항목. gemma는 비에이전트라 현재 효과 제한적.
4. **improve 계획 프롬프트 다이어트** — 30,000자 도달 중단 누적. 컨텍스트 슬림화.

### 모델 사실 (Gemma 4, 검증됨 — 상세는 context-notes.md)
26B·31B = 텍스트+이미지+비디오 입력(**음성 ❌**), 컨텍스트 256K, thinking 제어 가능,
function calling·structured JSON 네이티브. PDF는 비전 처리(파일시스템 읽기 아님).
