# golem 컨텍스트 노트 (결정 + 왜)

## G1 — 정체성: Claude 사용량 절감용 게임 룰엔진 오프로드
ARAG 본체(무료모델 frontier 연구)와는 별개의 실용 도구다. gemma가 손(구현), Claude가
머리(조율). 목적은 사용자가 Claude를 쓸 때 Claude를 덜 닳게 하는 것.
왜: 사용자 결정(2026-06-16). 연구 정체성 논쟁은 빠지고 실용 도구로 합의.

## G2 — 그릇 = JS/TS 웹 (Godot 아님)
근거: gemma 강점=Python/JS, 약점=GDScript. 사용자=폰 작업·판단 → 웹=즉시 플레이.
장르=로직중심 → 웹 적합. 출처: Gemma4 모델카드(HumanEval/MBPP=Python, 강점언어 Python/JS/SQL),
저자원언어 서베이(arxiv 2410.03981), godot-dodo(GDScript는 파인튜닝 필요), MultiPL-E(GDScript 미포함).
→ GDScript 천장을 재는 대신 강점언어로 비껴간다.

## G3 — Phase 1 = 스케줄러부터 (제일 어려운 것 먼저)
ARAG 실측: 난이도=창발적 통합, frontier 벽=틱/속도게이지 턴 스케줄러(T-000012, 단일≈1/3, cracked@2).
de-risk 원칙: 벽을 먼저 치면 뚫림/한계를 싸게 배운다.

## G4 — 격리: Phase 1은 host node + 타임아웃 (docker-node는 나중)
생성물=순수 계산 스케줄러(네트워크·FS 불필요)라 host node + 타임아웃 + temp dir로 충분.
ARAG 본체는 docker 격리(docker_gate) — golem도 멀티 시스템 통합 단계 가면 docker node로 격상.
node 미설치 시: docker node 이미지로 대체.

## G5 — 오라클: ARAG 트레이스diff 철학 재사용
골든 = 레퍼런스 구현이 뱉는 seed→트레이스(모델 비노출). 게이트 = 정확일치 diff(콜0).
자가수정 = 첫-발산 위치 힌트(ARAG 결정27의 JS판).

## G6 — 스파이크 범위 = 전투엔진 통째(스케줄러 단독 아님), 4 고정 시나리오
game/ 읽어보니 스케줄러 난이도가 상태이상·콤보와 분리 불가(타이밍 상호작용이 곧 난이도).
그래서 T-000012와 동일하게 *전투엔진 전체*를 JS로 재구현, 4 고정 시나리오(winner/turns/엔티티HP
정확일치)로 채점. RNG(파티생성)는 워커 범위서 제외(시나리오=고정 파티 입력) → CPython RNG
재현이라는 불공정 짐 없음. 골든은 game/로 공짜 생성(make_golden, 4/4 일치 검증). T-000012(파이썬
cracked@2)와 사과-대-사과.

## G8 — A 방식(Claude 레퍼런스 오라클)이 처음 보는 게임에 일반화됨 (2026-06-16)
golem을 일회성 데모에서 도구로: 검증엔진을 카드로 쌓는 은행(game_bank.sqlite) + A 오라클
(oracle.py — JS 레퍼런스→골든, game/ 의존 제거). 새 게임은 정답이 없다는 문제를, Claude가
레퍼런스 1벌 짜서 골든 생성으로 푼다. 검증: 카드#2 결정적 2048을 A로 적재 → 생성 런
**cracked@4, 11/11 전부 통과**(전투 카드 5/11보다 깔끔). 새 게임이 입출력 스키마(전투 전용
winner/turns/hp)를 강제로 일반화시킴 → 골든=평면 key:value 정확일치(전투·퍼즐 한 틀).
교훈 재확인: 규칙(RULES)이 레퍼런스를 빈틈없이 명세하면 싼 모델도 처음 보는 게임을 맞춘다
— frontier는 모델이 아니라 계약 정밀도에 있다. 다음 = 확장 루프(베이스 카드 + 메카닉 추가).

## G7 — 드라이버 = 키 11개 병렬 select-best (워커=키), 독립 시도
처음 단일키 순차로 짰다가 사용자 지적(2026-06-16) — 키 11개는 RPM 쿼터가 각각 독립이라 병렬=11배.
arag select_run 패턴(KeyPool.checkout + ThreadPool, 첫 통과 시 미시작 취소) 채택. 시도는 독립
(self-fix 없음) = T-000012 병렬 select-best와 동일 모드. self-fix 웨이브는 옵션으로 미룸.
