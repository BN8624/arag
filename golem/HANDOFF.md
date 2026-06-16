# HANDOFF.md — golem 현재 위치와 다음 액션

## 지금 어디 (2026-06-17)

- **v0.1 Contract Microkernel Replay 완료** + **Step 2 Planning A/B/C 측정 하니스 빌드+replay 검증 완료**. 둘 다 키 0.
- v0.1: replay 5/5(통과1+음성4 각각 지정 check 실패). `static_gate.py`는 src/ 지원 확장, 기존 평면 게임 무회귀.
- Step 2: `planning.py` — A(self-review)/B(1+3)/C(1+10) arm, 리뷰어 키 병렬, dedup 메트릭. fake 픽스처 replay로 A2<B6<C12 unique·dup 0.077·BLOCKING 1 측정 확인(plumbing 증명, 데이터는 가짜).
- **바로 다음은 실제 키 발사뿐.** RealCaller(키 경로)는 만들어 뒀고 안 쐈다. 사용자 go 필요.
- 반박/결정 로그: context-notes G25(v0.1)·G26(Step2 하니스, A안=self-review 정의).

## 다음 액션

1. **(★키 — 사용자 go 대기) Planning 실측 1회.** `python golem/studio/planning.py --idea "<게임 아이디어 한 줄>"`. 31B(critic) 콜 ~15회(draft1+self1+reviewer13), 리뷰어는 키 11개 병렬. 사실상 무료(AI Studio)·RPD 영향 미미.
2. 실측 결과로 판정: 독립리뷰가 self-review(A) 이기나, C가 B 이기나(§19 PENDING-004 임계 B>A +30%, C>B +20%). → reviewer 기본 개수(3 vs 10) 결정.
3. 그 다음에야 Design/Spec QA 등 하위 단계로 확장(처음부터 6단계 다 짓지 않는다 — A/B/C 결과가 구조 정당화부터).

실제 키 사용·worker slots 투입은 사용자 명시 go 뒤에만(메모리 no-autostart-runs). 시작점 = 위 1번, 아이디어 한 줄만 주면 발사.
