# HANDOFF.md — golem 현재 위치와 다음 액션

## ▶ 새 세션 여기부터
- 읽는 순서: 이 파일 → 필요할 때만 `context-notes.md`(결정 이유 G25~G38) / `GolemStudioMode.md`(설계 정본) / `checklist.md`(진행).
- **지금 할 일 한 줄**: §13 Step 7 Integration — 수렴 빌드 중 최종 workspace 선정 + static_gate/grade(acceptance+edge_cases) + final_report.md 생성. (또는 사용자가 장르확장 택하면 그쪽.)
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
| Step6 Adversarial QA | `adversarial.py` | 팀(lead+리뷰어8+synth)이 edge_cases 13+acceptance 5 → `adversarial_packet/`. 실측으로 EDGE-011(빈입력)·EDGE-012(미지id) 크래시 발견 → 계약 명문화(RULE-07+actions []디폴트, rung5)로 **둘 다 소거**, 유효빌드 edge 7/7 수렴. |

**핵심 측정(G33·G34·G35)** — Build 합의(특권 golden 아닌 다수합의)로 "계약이 얼마나 빡빡한가"를 잰다. 한 번에 한 변수.
- 출력계약 미고정 → 합의 **0.36**.
- 출력계약 고정 → 합의 **0.66**, 게이트 3/11→8/11. 단 반쪽(빌드가 actions 미실행, turn:0 no-op 합의).
- 입력 스키마 고정(액션 키 `action`/`id`·`costMultiplier`·캐노니컬 디폴트) → 합의 **0.98**, 게이트 9/11. 진짜 수렴.
- 평가시점 명문화(RULE-05/06 시작+액션후 체크, WON시 중단) + SCN-006 ACTIVE→PLAYING → 합의 **1.0**, 게이트 11/11, 11빌드 expected 완전 수렴(G36). **사다리 0.36→0.66→0.98→1.0 = 계약 한 칸 박을 때마다 한 칸 수렴.**
- Step6 실측(G37): 수렴 빌드가 edge 대부분 일치하나 EDGE-011(빈 {})·EDGE-012(미지 id)에서 깨짐 → 두 구멍 지목.
- rung5(G38): 두 구멍 계약 명문화(RULE-07 + actions []디폴트) → acceptance 합의 **1.0 유지**, EDGE-011/012 **크래시 둘 다 0**, 유효빌드 edge 7/7 수렴. **adversarial이 찾은 구멍을 계약에 박을 때마다 싼 모델이 그 엣지에서도 수렴 — 사다리 검증 완결.**
- logs 채점(G39): 출력계약에 `logs:` 줄 추가 → acceptance 1.0 유지, EDGE-012 미지id 로그 2/11→**6/6 골든 수렴**. RULE-07 상태+로그 모두 채점·수렴. 교훈: 채점 표면(output contract)이 곧 측정 가능 범위.

주의: Step4는 초안(결함 있음). `build_runs/`는 .gitignore(생성물). 결정·반박 로그는 context-notes G25~G38.

## 다음 액션

1. **§13 Step 7 Integration**(위 "지금 할 일 한 줄"). 수렴 빌드 중 최종 workspace 선정 + static_gate/grade(acceptance+edge_cases) + final_report.md. Stage6 산출물=final workspace·static_gate_result·grade_result·final_report. ★키 여부는 채점 방식에 따라(기존 빌드 재사용 시 키0 가능).
2. (대안) 장르/형태 확장 — 같은 파이프라인이 더 어려운/다른 카드에서도 수렴하나(PLAN frontier).
3. (backlog) adversarial validator BLOCKING 해소 추적 / 측정 N≥10 장르확장.
