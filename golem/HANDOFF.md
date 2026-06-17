# HANDOFF.md — golem 현재 위치와 다음 액션

## ▶ 새 세션 여기부터
- 읽는 순서: 이 파일 → 필요할 때만 `context-notes.md`(결정 이유 G25~G44) / `GolemStudioMode.md`(설계 정본) / `checklist.md`(진행).
- **지금 할 일 한 줄**: reconcile 자동연결 마무리 — diff는 build_graded에 자동 wired(G45). 남은 건 resolve→AUTO 자동적용(`--apply`)·ESCALATE만 사람에게·BUILD_BUG 재빌드 트리거를 build_graded 흐름에 잇기. ★키(resolve 시).
- 회귀 하드닝(외부 지적 수용분 #2~7)은 G45에서 전부 반영 완료(키0). 남은 키 작업=resolve 자동연결 + 장르 N≥3.
- 키 사용은 사용자 명시 go 뒤에만(메모리 no-autostart-runs).
- 운영 가드레일은 context-notes **G46** 참조: v0.1 동결 아님(확장 유지) / 우선순위 T0→T1→T2(T2가 T0/T1 안 막음) / live build=build_graded.py / reconcile=Build↔oracle 슬라이스 / unique_issue_count는 lexical(방향성만) / --apply는 AUTO만.

## 지금 어디 (2026-06-17)

Golem Studio = `GolemStudioMode.md` §13 파이프라인을 실모델로 구축. 아이디어 한 줄로 **Step 1~7 전부 실제 완주**(방치형·발열 두 카드). 하네스는 계약구동으로 일반화돼 새 카드는 코드변경 0. 합의-vs-oracle 자동 해소(`reconcile.py`)까지 갖춤. 산출물은 `golem/studio/`(패킷: 방치형=`*_packet`, 발열=`*_packet_heat`).

| §13 단계 | 코드 | 산출/상태 |
|---|---|---|
| Step1 v0.1 Contract Microkernel | `contract_validator.py`·`replay.py` | replay 5/5(키0). `static_gate.py` src/ 확장(strict 모드 보유). |
| Step2 Planning | `planning.py` | A/B/C 측정 + synthesis. 방치형 FROZEN 계약 → `planning_packet/`. A6<B11<C27(독립리뷰>self·10>3). |
| Step3 Design | `design.py` | 4모듈 분해(utils←state_manager←engine←main)+traceability, §7·§8.2 PASS → `design_packet/`. |
| Step4 Spec QA | `specqa.py` | 11 시나리오 구체화 → `specqa_packet/`. SCN-006 오라클오류는 G36에서 교정(ACTIVE→PLAYING). 남은 결함: BLOCKING 해소 추적 안 됨(backlog). |
| Step5 Build v1 | `build_graded.py` | design 4모듈+시나리오+**합의 채점**(특권 golden 아님). `build.py`는 v0 스파이크로 잔존. |
| Step6 Adversarial QA | `adversarial.py` | 팀(lead+리뷰어8+synth)이 edge_cases 13+acceptance 5 → `adversarial_packet/`. 실측으로 EDGE-011(빈입력)·EDGE-012(미지id) 크래시 발견 → 계약 명문화(RULE-07+actions []디폴트, rung5)로 **둘 다 소거**, 유효빌드 edge 7/7 수렴. |
| Step7 Integration | `integration.py` | 수렴 빌드 재사용(키0) → 최종 workspace 선정+static_gate+golden 채점+final_report. **계약구동 일반화**(출력키=state_shape, adversarial 옵셔널). 방치형 24/24·발열 13/13. |
| 자동해소 | `reconcile.py` | Build 합의 vs golden **자동 diff(키0)** + 31B 진단(CONTRACT_AMBIGUOUS/ORACLE_BUG/BUILD_BUG)·AUTO/ESCALATE 분류 + `--apply`(AUTO만). 내 수작업 자동화. diff/resolve/apply 키0 검증 + 실측 1건(SCN-011→BUILD_BUG 정확). |

**장르확장(다리실험, G41~44)**: 방치형 v1 → **발열/과열(결합 시스템)** 카드(`*_packet_heat`). 결과: ① 맞물림이 빌드 합의를 안 떨어뜨림(첫 런 1.0) — "결합=어렵다" 기각. ② 난이도가 *틱 순서 모호성*(관성·즉시)+*oracle 버그*로 이동 — 합의 1.0은 필요조건이지 충분조건 아님(독립 oracle 대조 필수). ③ 계약 한 줄 명문화로 완전수렴 합의를 의도값으로 이동시킴(B1→B2). 최종 발열 골든 13/13. ④ 하네스(build_graded·integration) 계약구동 일반화 → 새 카드 코드변경 0. ⑤ 수작업 diff/진단을 `reconcile.py`로 자동화.

**핵심 측정(G33·G34·G35)** — Build 합의(특권 golden 아닌 다수합의)로 "계약이 얼마나 빡빡한가"를 잰다. 한 번에 한 변수.
- 출력계약 미고정 → 합의 **0.36**.
- 출력계약 고정 → 합의 **0.66**, 게이트 3/11→8/11. 단 반쪽(빌드가 actions 미실행, turn:0 no-op 합의).
- 입력 스키마 고정(액션 키 `action`/`id`·`costMultiplier`·캐노니컬 디폴트) → 합의 **0.98**, 게이트 9/11. 진짜 수렴.
- 평가시점 명문화(RULE-05/06 시작+액션후 체크, WON시 중단) + SCN-006 ACTIVE→PLAYING → 합의 **1.0**, 게이트 11/11, 11빌드 expected 완전 수렴(G36). **사다리 0.36→0.66→0.98→1.0 = 계약 한 칸 박을 때마다 한 칸 수렴.**
- Step6 실측(G37): 수렴 빌드가 edge 대부분 일치하나 EDGE-011(빈 {})·EDGE-012(미지 id)에서 깨짐 → 두 구멍 지목.
- rung5(G38): 두 구멍 계약 명문화(RULE-07 + actions []디폴트) → acceptance 합의 **1.0 유지**, EDGE-011/012 **크래시 둘 다 0**, 유효빌드 edge 7/7 수렴. **adversarial이 찾은 구멍을 계약에 박을 때마다 싼 모델이 그 엣지에서도 수렴 — 사다리 검증 완결.**
- logs 채점(G39): 출력계약에 `logs:` 줄 추가 → acceptance 1.0 유지, EDGE-012 미지id 로그 2/11→**6/6 골든 수렴**. RULE-07 상태+로그 모두 채점·수렴. 교훈: 채점 표면(output contract)이 곧 측정 가능 범위.
- Step7 Integration(G40): 수렴 빌드 재사용(키0) E2E 완주 — 최종 attempt01(4모듈), static_gate PASS, **golden 24/24 PASS**(levels는 출력표면밖 표기). **아이디어 한 줄→Step1~7 전 파이프라인 실제 완주 도달.**

주의: Step4는 초안(결함 있음). `build_runs/`는 .gitignore(생성물). 결정·반박 로그는 context-notes G25~G44.

## 다음 액션

1. **reconcile를 파이프라인에 연결**(위 "지금 할 일 한 줄"). build_graded 끝나면 reconcile.diff 자동 호출 → 불일치 있으면 resolve → AUTO 자동적용(--apply), ESCALATE만 사람에게 모아 보고. BUILD_BUG는 재빌드 자동 트리거 검토. 이게 "사람은 fork만" 자동 루프를 완성. ★키(resolve 시).
2. (대안) 장르확장 계속 — 조립카드 T-000012(창발적 통합) 등 더 어려운 카드로 N≥3. 발열로 결합 카드 1장 검증됨.
3. (backlog) levels 등 출력표면 확장 / adversarial validator BLOCKING 추적 / 발열 Adversarial QA·Integration 정식 완주.
