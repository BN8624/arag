# HANDOFF.md — golem 현재 위치와 다음 액션

## 지금 어디 (2026-06-17)

- **v0.1 Contract Microkernel Replay 완료** + **Step 2 Planning A/B/C 측정 하니스 빌드+replay 검증 완료**. 둘 다 키 0.
- v0.1: replay 5/5(통과1+음성4 각각 지정 check 실패). `static_gate.py`는 src/ 지원 확장, 기존 평면 게임 무회귀.
- Step 2: `planning.py` — A(self-review)/B(1+3)/C(1+10) arm, 리뷰어 키 병렬, dedup 메트릭. fake 픽스처 replay로 A2<B6<C12 unique·dup 0.077·BLOCKING 1 측정 확인(plumbing 증명, 데이터는 가짜).
- **Planning 단계 완성 — 방치형게임 계약 FROZEN**(키 씀). 초안→리뷰어10→synthesis로 BLOCKING 11→0(decisions 9/assumed 3/deferred 2). 부동소수점 모호성을 RULE-03 floor()로 못박는 등 결정성 깨던 모호점 전부 닫음. 패킷=`golem/studio/planning_packet/`.
- A/B/C 측정(G27): A6<B11<C27 unique, 독립리뷰>self·10>3 둘 다 임계 통과. caveat: N=1, dedup 문자열기반 과대계상(방향 신뢰/크기 부풀림).
- interface_contract(2파일)는 v0.1 contract_validator의 module_manifest와 동형 → Build에서 그대로 검증 가능.
- 반박/결정 로그: context-notes G25(v0.1)·G26(하니스)·G27(A/B/C 실측)·G28(synthesis FROZEN).

- **측정 신뢰 보강(G29, 키X).** dedup을 토큰 Jaccard 클러스터링으로 교체. 어휘기반 한계로 C 27→25만 줄지만, 임계 0.5~0.25 어디서 재도 A6<B11<C20~25 — **결론(독립리뷰>self, 10>3) 강건**(자 흔들림보다 효과 큼). 진짜 의미 dedup(임베딩/LLM)은 보류.

## 다음 액션 (사용자 선택 대기)

1. **측정: N≥10을 서로 다른 장르 아이디어로(권고).** §19의 진짜 목적=일반화(모호한 게임 vs 명확한 게임에서 리뷰어 효과 다른가). 메트릭은 이제 충분히 신뢰. ★키(싸다, AI Studio 무료). 신규 run은 새 dedup 자동.
2. **Build 단계.** FROZEN 계약 → `driver.py` 11키 select-best → `static_gate`+`contract_validator`+`grade`. grade 정확일치엔 **golden 필요** → 오라클(oracle.py/oracle_design.py 재사용) 선행. ★키.
3. acceptance expect 정확값화(Spec QA).

키 사용은 사용자 명시 go 뒤에만(메모리 no-autostart-runs).
