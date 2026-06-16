# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터
1. **읽기**: 이 파일 `지금 어디` + `다음 액션`만. 규칙은 CLAUDE.md, 왜는 context-notes.md.
2. **지금 할 일 (한 줄)**: **Phase 4 설계 — 자율 오라클**(주제+최소규격만 주면 31B가 오라클까지).
   핵심=오라클 신뢰를 select-best 합의로 보증. 사용자와 범위 합의 후 파이프라인 설계(준비는 키X).
3. ⚠️ **런은 사용자 명시 지시 전엔 안 돌린다**(키 소비, ARAG 캠페인과 경쟁 금지).

**문서 용도 (필요할 때만):**
| 문서 | 용도 | 언제 |
|---|---|---|
| **HANDOFF.md** (여기) | 현재 상태 + 다음 할 일 | **항상 먼저** |
| CLAUDE.md | golem 규칙·제약 | 처음 1회 |
| README.md | golem 정체·역할·Phase | 방향 의심될 때 |
| context-notes.md | 결정 로그 G1~G6 (왜) | 특정 결정 궁금할 때 |
| checklist.md | 세부 체크리스트 | 진행 추적 |

## 지금 어디 (2026-06-16)
**Phase 1(엔진검증)·Phase 2(이모지 스킨) 완료 → Phase 3 1단계(은행+A오라클) 완료.**
- Phase 1: 런 `20260616-130305` cracked@10, 5/11. attempt01·10 독립 재채점 4/4.
- Phase 2: 엔진 `web/engine.browser.js` 공유모듈 + 스킨 교체 구조. `battle.html`=이모지 스킨.
  폰(테일스케일 `http://100.89.73.83:8731/golem/web/battle.html`) 확인. 무회귀 4/4.
- Phase 3 1단계: **검증엔진 라이브러리(은행)** 골격. `game_bank.py`(sqlite) + `oracle.py`(JS
  레퍼런스→골든, game/ 의존 제거) + driver/worker/grade 카드화(`--card`).
- Phase 3 2단계 **완료**: 입출력 게임-중립화(골든=평면 dict). 카드#2 'merge-2048' A 방식 적재 후
  **생성 런 cracked@4, 11/11 전부 통과**($0.027, 런 20260616-143058). 독립 재채점 4/4.
  → **A 방식이 처음 보는 게임에도 일반화됨 확정.** 통과본=카드#2 solution(확장 베이스).
- 방향(사용자): A 방식으로 여러 게임 만들어 은행에 쌓고 베이스로 확장. = ARAG Design Bank의 golem판.
- Phase 3 3단계 **완료**: 확장 루프 = 2048+벽. 베이스 주입(driver `--base`) + 카드#3
  'merge-2048-walls'. 확장 런 **cracked@7, 11/11 통과**($0.030). **재사용 증거**: 통과본이
  board.js를 베이스 그대로 두고 moves.js만 벽 세그먼트화 → 맨바닥 재작성 아닌 진짜 확장.
  은행 3장 모두 solution 있음(확장 베이스 준비).
- **Phase 4 제안(사용자)**: 오라클(골든)도 31B가 만들게. Claude=주제+최소규격+감수. 리스크=오라클
  신뢰 → 독립 gemma 합의(select-best)로 보증. checklist Phase 4 참고. = golem 자율화·Claude 절감 극대.

## 다음 액션 (★다음 세션 여기부터)
**Phase 4 = 자율 오라클(31B가 골든까지).** 1~3단계로 "사람 오라클 → gemma 구현·확장"은 다 됨
(맨바닥·확장 둘 다 11/11). 다음은 오라클 생성 자체를 gemma로 넘겨 Claude 절감 극대화.
1. **범위 합의** — 어느 장르/주제로 자율 오라클을 첫 실험할지, Claude가 줄 "골든 최소규격"(공통 메타
   계약 = 평면 key:value 정확일치·결정적·멀티파일·stdin금지·난이도)을 어디까지 고정할지.
2. **오라클 생성 프롬프트 설계(키X)** — 31B에 [주제+메타규격] → [규칙+레퍼런스+시나리오] 출력 스키마.
   정적 점검(결정적·멀티파일·출력형식)·oracle 골든화.
3. **오라클 검증 게이트(★키 씀)** — 독립 gemma K개가 규칙만으로 재구현 → 골든 합의율 측정.
   높으면 오라클 채택(+통과본), 낮으면 31B 규칙 재설계. = select-best를 오라클에도.
- **런은 사용자 go 전 금지.** 재적재: #1 `bank_init.py`, #2 `bank_add_2048.py`, #3 `bank_add_2048_walls.py`.

## 기계 정본
- 장부: `golem/golem_ledger.jsonl`(시도별 ok·first_divergence·cost). 후보: `runs/golem/<ts>/attemptNN/`.
- 정답지: `golem/golden/scenarios.json`(시나리오 파티+정답, make_golden으로 재생성). 오라클: `grade.py`(콜0).
- 재사용: arag `llm.py`(gemma 호출), `game/`(레퍼런스·골든 소스), `frozen/T-000012`(파이썬 대조군).
