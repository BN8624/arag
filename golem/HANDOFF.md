# HANDOFF.md — golem 현재 위치와 다음 액션

## ▶ 새 세션 여기부터
- 읽는 순서: 이 파일 → 필요할 때만 `context-notes.md`(결정 이유 G25~G35) / `GolemStudioMode.md`(설계 정본) / `checklist.md`(진행).
- **지금 할 일 한 줄**: Step 6 Adversarial QA — RULE-05/06 승리판정 **평가시점**을 계약에 명문화(SCN-009/010 갈림 원인) + edge_cases·acceptance 다듬기(ACTIVE 오라클오류 교정).
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

**핵심 측정(G33·G34·G35)** — Build 합의(특권 golden 아닌 다수합의)로 "계약이 얼마나 빡빡한가"를 잰다. 한 번에 한 변수.
- 출력계약 미고정 → 합의 **0.36**.
- 출력계약 고정 → 합의 **0.66**, 게이트 3/11→8/11. 단 반쪽(빌드가 actions 미실행, turn:0 no-op 합의).
- 입력 스키마 고정(액션 키 `action`/`id`·`costMultiplier`·캐노니컬 디폴트) → 합의 **0.98**, 게이트 9/11. **진짜 수렴 확인**(SCN-001 turn2/energy6 등 expected 일치, no-op 아님). **"입력+출력 둘 다 못박으면 31B가 거의 완전 수렴" 정량 확정.**
- 남은 0.02 = no-op 잔재 아니라 **진짜 명세 구멍**: SCN-009/010만 합의 8/9 — RULE-05/06 승리판정 **평가시점** 미고정("액션 처리 전 승리체크 하나"). → Step6가 메울 자리.

주의: Step4는 초안(결함 있음, Step6가 다듬을 예정). `build_runs/`는 .gitignore(생성물). 결정·반박 로그는 context-notes G25~G35.

## 다음 액션

1. **Step 6 Adversarial QA**(위 "지금 할 일 한 줄"). RULE-05/06 승리판정 평가시점을 계약에 명문화(SCN-009/010 갈림 = 0.98의 남은 구멍) + edge_cases.json + acceptance draft 다듬기(SCN-006 "ACTIVE" 오라클오류 교정). ★키.
2. (backlog) specqa validator 강화(계약 외 상태값 거부 + BLOCKING 해소 추적) / 측정 N≥10 장르확장.
