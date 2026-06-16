# HANDOFF.md — golem 현재 위치와 다음 액션

## ▶ 새 세션 여기부터
- 읽는 순서: 이 파일 → 필요할 때만 `context-notes.md`(결정 이유 G25~G34) / `GolemStudioMode.md`(설계 정본) / `checklist.md`(진행).
- **지금 할 일 한 줄**: 시나리오 입력 스키마를 한 형식으로 고정하고 `build_graded.py` 합의 재측정(0.66→?).
- 키 사용은 사용자 명시 go 뒤에만(메모리 no-autostart-runs).

## 지금 어디 (2026-06-17)

Golem Studio = `GolemStudioMode.md` §13의 6단계 파이프라인을 실모델로 구축 중. 아이디어 한 줄("방치형게임")로 Step 1~5를 실제 통과했다. 산출물은 `golem/studio/`.

| §13 단계 | 코드 | 산출/상태 |
|---|---|---|
| Step1 v0.1 Contract Microkernel | `contract_validator.py`·`replay.py` | replay 5/5(키0). `static_gate.py` src/ 확장(strict 모드 보유). |
| Step2 Planning | `planning.py` | A/B/C 측정 + synthesis. 방치형 FROZEN 계약 → `planning_packet/`. A6<B11<C27(독립리뷰>self·10>3). |
| Step3 Design | `design.py` | 4모듈 분해(utils←state_manager←engine←main)+traceability, §7·§8.2 PASS → `design_packet/`. |
| Step4 Spec QA | `specqa.py` | 11 시나리오 구체화 → `specqa_packet/`. **초안**(결함: SCN-006 "ACTIVE" 오라클오류, BLOCKING 추적안됨). |
| Step5 Build v1 | `build_graded.py` | design 4모듈+시나리오+**합의 채점**(특권 golden 아님). `build.py`는 v0 스파이크로 잔존. |

**핵심 측정(G33·G34)** — Build 합의(특권 golden 아닌 다수합의)로 "계약이 얼마나 빡빡한가"를 잰다.
- 출력계약 미고정 → 합의 **0.36**.
- 출력계약 고정(한 변수만 바꿈) → 합의 **0.66**, 게이트 3/11→8/11. **"계약 빡빡 → 싼 모델 수렴" 방향 확인.**
- 단 **0.66은 반쪽**: 통과 빌드들이 시나리오 actions를 실제 실행 안 함(turn:0/undefined). **입력 스키마 미고정**이 남은 원인.

주의: Step4는 초안(결함 있음, Step6가 다듬을 예정). `build_runs/`는 .gitignore(생성물). 결정·반박 로그는 context-notes G25~G34.

## 다음 액션

1. **입력(시나리오) 스키마 고정 → 합의 재측정**(위 "지금 할 일 한 줄"). scenarios.json을 한 형식으로 못박고(현재 constants/initialState/actions 이질적·일부 산문) 빌드가 actions를 실제 실행하게 → 0.66이 진짜 수렴으로 오르나 본다. 한 번에 한 변수. ★키.
2. **Step 6 Adversarial QA** — edge_cases.json + acceptance draft 다듬기(ACTIVE 오라클오류 교정).
3. (backlog) specqa validator 강화(계약 외 상태값 거부 + BLOCKING 해소 추적) / 측정 N≥10 장르확장.
