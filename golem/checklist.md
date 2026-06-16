# golem 체크리스트

## Phase 0 — 셋업 (지금)
- [x] 이름·폴더 확정 (golem, `arag/golem/`)
- [x] node 가용성 확인 (v24.15.0)
- [x] 플랜/체크리스트/컨텍스트노트 생성
- [ ] 스케줄러 스펙 한 장 (인터페이스 + 결정적 입력/출력 계약)

## Phase 1 — 전투엔진 JS 스파이크 (T-000012 JS판, 4 고정 시나리오) — 완료
- [x] make_golden.py — game/로 시나리오 파티+정답 생성·검증 (4/4 골든 일치)
- [x] grade.py — node main.js --scenario N 출력 vs 골든 정확일치 + 첫불일치 (스모크 검증)
- [x] worker_prompt.py — PAMPHLET 규칙+고정파티+출력계약 (정답 비노출)
- [x] driver.py — 키 11개 병렬 select-best(워커=키) + --replay 점검모드 (plumbing 검증)
- [x] 스파이크 실행 — 런 20260616-130305, **cracked@10, 11시도 중 5통과**, 총 $0.031
- [x] 통과본 독립 재채점 — attempt01·10 둘 다 4/4 정확일치 (우연 아님 확인)
- [x] 통과본 검수 — 4파일 304줄, 껍데기·미사용 import 없음, 스케줄러 레퍼런스 일치 → 재작성 불필요

## 판단 기준 — 결과
- gemma JS 엔진이 4 시나리오 골든 정확일치하나 → **됨**. cracked@10 (Python T-000012 cracked@2 대비 더 어렵게 걸림, 통과율 5/11).
- Claude가 packet/diff만으로 얕게 끝내나 → **아니오**. 4파일 전부 읽고 로직 추적, 품질 양호 확인.
- 실패 6개 패턴: 시나리오1 턴 카운트 ±오차 4개(턴 스케줄러 frontier 동일) + require 경로 깨짐 2개.

## Phase 2 — 표현층 바인딩 (사용자 선택: 실용)
- [x] `golem/web/engine.browser.js` — 검증엔진(attempt10) 무수정 로직 + trace. 공유 모듈(browser+node).
      **표현층(스킨)이 갈아끼우는 단일 진실원.** 룩이 바뀌어도 이 파일은 안 바뀜.
- [x] `golem/web/battle.html` — 공유엔진 + **이모지 스킨**. 캐릭터 이모지·공격 들썩·피격 흔들림·
      데미지 숫자 플로팅·스킬 아이콘·HP/gauge바·상태배지·승자배너. 폰 세로. 스킨=SKIN 객체 한 곳.
- [x] `golem/web/samples.html` — 룩 비교 목업(A 이모지 / B 레트로도트 / C 네온). 사용자가 **A 이모지** 선택.
- [x] `golem/web/_verify.js` — 공유엔진 vs 골든 무회귀 가드. **4/4 PASS** (이모지 개편 후 재확인).
- [x] 아이폰 확인 — 테일스케일 `http://100.89.73.83:8731/golem/web/battle.html`로 폰 접속 OK.
- [ ] (선택) 다른 스킨(레트로/네온) 추가 시 SKIN을 스킨객체 배열로 승격 + 셀렉터. 지금은 이모지 1종.
- [ ] (선택) 인터랙티브화 — 스킬 선택 플레이는 엔진 변경(메카닉 확장)이라 골든 재검증 필요.

## Phase 3 — Game Bank + A 오라클 (검증엔진 라이브러리)
방향(사용자 2026-06-16): A 방식(Claude 레퍼런스 오라클)으로 여러 게임을 만들어 DB(은행)에 쌓고,
베이스로 확장. 단계 = 1)은행+A골격(키X) 2)새 게임 1개 생성(런·go필요) 3)확장 루프(런).
### 1단계 — 은행 + A 파이프라인 골격 (키 안 씀) — 완료
- [x] `game_bank.py` — sqlite 카드 은행(스키마 + save/get/list). 카드 = 규칙·시나리오·골든·솔루션·레퍼런스.
- [x] `oracle.py` — JS 레퍼런스 impl → 골든 생성(grade 러너 재사용). **game/ 의존 제거 = A경로 핵심.**
- [x] `bank_init.py` — 카드 #1 "tempo-combat" 적재(규칙=RULES, 시나리오=golden/, 솔루션=attempt10).
- [x] 무회귀: oracle로 솔루션에서 골든 재생성 → 저장 골든 4/4 일치(game/ 없이 골든 나옴 증명).
- [x] driver/worker_prompt/grade 카드 파라미터화(`--card slug`, 기본값 유지). replay 양쪽 PASS, 프롬프트 동일.
- [x] `game_bank.sqlite` gitignore(바이너리·재생성 가능).
### 2단계 — 새 게임(2048류 합치기 퍼즐) A 생성 (준비=키X 완료, 런=go필요)
- [x] 입출력 일반화 — 골든=평면 `key:value` dict 정확일치(전투의 winner/turns/hp도 자연 포함),
      입력=임의 JSON. grade/oracle/worker_prompt/driver 게임-중립화. **새 게임이 강제한 일반화.**
- [x] 카드#1 무회귀 — 일반화 후 bank_init 재적재, 솔루션 여전히 4/4 PASS.
- [x] 카드#2 "merge-2048" — Claude 결정적 2048 레퍼런스(board/moves/main.js)+규칙+4시나리오 →
      oracle 골든 → 적재. 레퍼런스 self-채점 PASS. 골든 손검산 OK(sc1 L→4·sc2 L→12 등).
- [x] **생성 런** `driver.py --card merge-2048` (런 20260616-143058) — **cracked@4, 11/11 전부 통과**,
      $0.027. attempt04 독립 재채점 4/4 정확일치(멀티파일 board/moves/main 157줄). 통과본=카드 solution 갱신.
      → **A 방식이 처음 보는 게임(2048)에도 됨 확정.** 전투(5/11)보다 깔끔 — 규칙이 명확할수록 잘 됨.

### 3단계 — 확장 루프 (준비=키X 완료, 런=go필요)
선택 메카닉 = 2048 + 벽(장애물). 베이스 solution을 워커에 줘 "맨바닥 대비 확장이 싸게 되나" 측정.
- [x] 베이스 주입 경로 — worker_prompt.build_prompt(base_files=), driver `--base <slug>`.
- [x] 카드#3 "merge-2048-walls" — 확장 레퍼런스(moves.js만 벽 세그먼트화)+전체 규칙+4 벽시나리오 →
      oracle 골든. self-채점 PASS, 골든 손검산 OK(sc1 [2,-1,2,2]L→2,-1,4,2 등).
- [x] 확장 프롬프트 점검 — BASE IMPLEMENTATION(베이스 코드)+벽 규칙 포함(8966자).
- [ ] **(★go 필요) 확장 런** `python golem/driver.py --card merge-2048-walls --base merge-2048` —
      gemma가 베이스 위에 벽 확장. cracked@N + 11/11 대비 난이도. 통과본=카드#3 solution.
