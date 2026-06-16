# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터
1. **읽기**: 이 파일 `지금 어디` + `다음 액션`만. 규칙은 CLAUDE.md, 왜는 context-notes.md.
2. **지금 할 일 (한 줄)**: **Phase 5 — 랜덤 주제 대량 측정 캠페인** 설계·실행. 주제 출처((a)Claude
   장르풀 / (b)31B 자율) 정하고, oracle_design→driver 게이트를 주제 루프로 묶어 합의율 분포 측정.
   ⚠️대량 키 소비 — 사용자 명시 go + 사전 점검 필수.
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
- **Phase 4 완료(자율 오라클 작동 입증)**: `oracle_design.py`로 31B가 [주제+메타규격]→게임 규칙
  +레퍼런스+시나리오 설계(theme=Snake, 첫 시도 성공). 합의 게이트(`driver --card snake-auto`)에서
  독립 11개 중 **10/11이 31B 골든과 정확일치** → 오라클 신뢰 입증. 은행 4번째 카드 snake-auto(sol o).
- **다음 = Phase 5**: 랜덤 주제 대량 캠페인으로 합의율 분포 측정(무료모델×자율오라클 한계 지도).
  ⚠️대량 키 — go+점검 필수. 정할 것: 주제 출처 (a)Claude 풀 (b)31B 자율.

## 다음 액션 (★다음 세션 여기부터)
**Phase 5 = 랜덤 주제 대량 측정 캠페인.** Phase 4로 자율 오라클(31B 설계 + 독립 합의 검증) 작동
입증(snake 10/11). 이제 주제를 계속 바꿔 대량으로 돌려 한계 지도를 그린다.
1. **주제 출처 결정(사용자)** — (a) Claude가 장르 풀 제공 / (b) 31B가 주제까지 자율 생성.
2. **캠페인 러너 설계(키X)** — 주제 리스트 루프: oracle_design(설계) → 정적/골든 게이트 → driver(독립
   합의) → 합의율·실패모드 장부화. 오라클 설계 실패·합의 미달도 데이터로 기록.
3. **캠페인 실행(★대량 키 — 명시 go + 점검 필수)** — 측정축: 주제별 설계 성공률 / 합의율 분포 /
   자율 신뢰 통과율. ARAG 캠페인과 키 경쟁 금지 확인.
- **런은 사용자 go 전 금지.** 재적재: #1 `bank_init.py`, #2 `bank_add_2048.py`,
  #3 `bank_add_2048_walls.py`, #4 `oracle_design.py --theme ... --slug ...`(키 씀).

## 기계 정본
- 장부: `golem/golem_ledger.jsonl`(시도별 ok·first_divergence·cost). 후보: `runs/golem/<ts>/attemptNN/`.
- 정답지: `golem/golden/scenarios.json`(시나리오 파티+정답, make_golden으로 재생성). 오라클: `grade.py`(콜0).
- 재사용: arag `llm.py`(gemma 호출), `game/`(레퍼런스·골든 소스), `frozen/T-000012`(파이썬 대조군).
