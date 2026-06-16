# HANDOFF.md — golem 현재 위치와 다음 액션

## 지금 어디 (2026-06-17)

- **v0.1 Contract Microkernel Replay 완료** + **Step 2 Planning A/B/C 측정 하니스 빌드+replay 검증 완료**. 둘 다 키 0.
- v0.1: replay 5/5(통과1+음성4 각각 지정 check 실패). `static_gate.py`는 src/ 지원 확장, 기존 평면 게임 무회귀.
- Step 2: `planning.py` — A(self-review)/B(1+3)/C(1+10) arm, 리뷰어 키 병렬, dedup 메트릭. fake 픽스처 replay로 A2<B6<C12 unique·dup 0.077·BLOCKING 1 측정 확인(plumbing 증명, 데이터는 가짜).
- **Planning 단계 완성 — 방치형게임 계약 FROZEN**(키 씀). 초안→리뷰어10→synthesis로 BLOCKING 11→0(decisions 9/assumed 3/deferred 2). 부동소수점 모호성을 RULE-03 floor()로 못박는 등 결정성 깨던 모호점 전부 닫음. 패킷=`golem/studio/planning_packet/`.
- A/B/C 측정(G27): A6<B11<C27 unique, 독립리뷰>self·10>3 둘 다 임계 통과. caveat: N=1, dedup 문자열기반 과대계상(방향 신뢰/크기 부풀림).
- interface_contract(2파일)는 v0.1 contract_validator의 module_manifest와 동형 → Build에서 그대로 검증 가능.
- 반박/결정 로그: context-notes G25(v0.1)·G26(하니스)·G27(A/B/C 실측)·G28(synthesis FROZEN).

- **측정 신뢰 보강(G29, 키X).** dedup 토큰 Jaccard 클러스터링. 임계 0.5~0.25 어디서 재도 A6<B11<C20~25 — 결론(독립리뷰>self, 10>3) 강건. 진짜 의미 dedup(임베딩/LLM)은 보류.
- **Build v0 완성(G30, 키 씀).** `build.py` — FROZEN 계약 → gemma 구현 → static_gate + v0.1 contract_validator(매니페스트 정합) + 스모크. 방치형 계약 **cracked@4, 10/11 통과**. attempt04 진짜(규칙 구현, sc3 turn1000 WON). 아이디어→리뷰→계약→구현→검증이 실모델로 한 줄에 꿰임.
- **순서 복원(G31).** §13은 1→2→3 Design→4 Spec QA→5 Build→6 Adv QA. 1,2 후 5(Build)로 점프했던 것 바로잡음. Build v0는 스파이크로 남김.
- **Step 3 Design 완료(G31, 키 씀).** `design.py` — 방치형 계약을 **4모듈 분해**(utils 순수계산←state_manager 상태전이←engine 조율←main I/O), RULE-01~06 전부 traceability 연결, §7·§8.2 validator PASS. 산출=`design_packet/`(system_design.md, module_manifest.json, traceability.json, traceability_report.md). Build v0 통짜 2파일을 교정.

- **Step 4 Spec QA 완료(G32, 키 씀, 초안).** `specqa.py` — 11 시나리오 구체화(기계입력+정확 expected), RULE-01~06 커버, validator PASS. 산출=`specqa_packet/`. **결함 있음(초안)**: SCN-006 "ACTIVE"(계약엔 PLAYING) 오라클오류, RULE-03 float경로 미검, BLOCKING 5 해소 추적안됨. 사용자=초안으로 두고 진행(Step5 합의·Step6가 잡음).

## 다음 액션 — §13 순서대로

1. **Step 5 Build 재실행(다음).** design_packet의 **4모듈 manifest** + specqa 시나리오로 gemma 빌드 → static_gate + contract_validator(design manifest) + 시나리오 실행 → **합의 채점**(빌드들이 같은 답에 모이나, 특권 golden 아님 — 사용자 산출물축소 우려 반영). build.py를 design manifest+합의로 확장. ★키.
2. **Step 6 Adversarial QA.** edge_cases.json + acceptance draft 다듬기(ACTIVE 등 오라클오류 교정).
3. (backlog) specqa validator 강화(계약 외 상태값 거부+BLOCKING 해소 추적).

키 사용은 사용자 명시 go 뒤에만(메모리 no-autostart-runs).
