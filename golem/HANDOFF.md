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
- caveat: Build v0는 '계약대로 굴러가나'까지. 10개가 각각 다른 숫자(golden 미고정) → 정확일치 아님(=오라클 붙이는 v1 몫).

## 다음 액션 (사용자 선택 대기)

1. **Build v1 — 오라클 골든 + 정확일치 채점.** 31B(or A방식)가 FROZEN 계약대로 레퍼런스 구현 → 시나리오 골든 생성(oracle.py/oracle_design.py 재사용) → build.py 게이트에 grade(정확일치) 추가. 그래야 "10개가 *같은 정답*"을 잼. ★키.
2. **측정: N≥10을 서로 다른 장르로.** §19 일반화(모호↔명확 게임에서 리뷰어 효과 차이). 메트릭 이제 신뢰. ★키.
3. 통과본(attempt04)을 web 표현층(golem/web)에 바인딩해 실제 플레이.

키 사용은 사용자 명시 go 뒤에만(메모리 no-autostart-runs).
