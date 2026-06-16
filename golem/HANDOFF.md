# HANDOFF.md — golem 현재 위치와 다음 액션

## 지금 어디 (2026-06-17)

- **v0.1 Contract Microkernel Replay 완료** + **Step 2 Planning A/B/C 측정 하니스 빌드+replay 검증 완료**. 둘 다 키 0.
- v0.1: replay 5/5(통과1+음성4 각각 지정 check 실패). `static_gate.py`는 src/ 지원 확장, 기존 평면 게임 무회귀.
- Step 2: `planning.py` — A(self-review)/B(1+3)/C(1+10) arm, 리뷰어 키 병렬, dedup 메트릭. fake 픽스처 replay로 A2<B6<C12 unique·dup 0.077·BLOCKING 1 측정 확인(plumbing 증명, 데이터는 가짜).
- **Planning A/B/C 첫 실측 완료**(아이디어=방치형게임, 키 씀). A(self) 6 → B(1+3) 11 → C(1+10) 27 unique. B>A·C>B 둘 다 PENDING-004 임계 통과 → 독립리뷰가 self-review 이기고 10이 3을 이김. 부동소수점 반올림 등 오라클 깨는 실질 모호성 포착(G27).
- caveat: N=1(§19는 ≥10), dedup이 문자열기반이라 의미중복 과대계상 → 방향은 신뢰, 크기는 부풀려짐.
- 반박/결정 로그: context-notes G25(v0.1)·G26(하니스)·G27(첫 실측 결과+caveat).

## 다음 액션 (사용자 선택 대기)

1. **(c) 권고 — synthesis로 진행.** lead가 리뷰 이슈를 받아 BLOCKING→0 정리 + contract_packet(§4) 생성. 구조 실효는 정성적으로 충분히 확인됨. `planning.py`에 synthesis arm 추가 필요(현재 미구현).
2. (b) dedup 의미기반 개선 — unique 과대계상 교정(측정 신뢰 먼저).
3. (a) 아이디어 더 돌려 N≥10 쌓기 — §19 통계 근거. 단 dedup 고치기 전엔 부풀린 수가 쌓임.

키 사용은 사용자 명시 go 뒤에만(메모리 no-autostart-runs).
