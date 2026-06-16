# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터
1. **읽기**: 이 파일 `지금 어디` + `다음 액션`만. 규칙은 CLAUDE.md, 왜는 context-notes.md.
2. **지금 할 일 (한 줄)**: Phase 3 **3단계 — 확장 루프**. 은행 카드를 베이스로 "메카닉 하나 더"
   확장이 gemma로 되는지(★키 씀, go 필요). 어떤 카드에 뭘 더할지 사용자와 정한다.
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
  은행: tempo-combat(solution o), merge-2048(solution o). 둘 다 확장 베이스 준비됨.

## 다음 액션 (★다음 세션 여기부터)
**Phase 3 3단계 = 확장 루프(★키 씀, go 필요).** 1·2단계로 "맨바닥 생성"은 됨 확정. 이제 도구의
실용 가치 = 기존 카드를 베이스로 확장이 싸게 되는지.
1. **확장거리 정하기** — 어느 카드에 무슨 메카닉을 더할지 사용자와 합의.
   예: 2048에 "이동 횟수 제한"·"장애물 칸"·"5단계 더 큰 보드", 또는 전투에 "새 스킬·새 상태이상".
2. **확장 오라클(키 안 씀)** — Claude가 베이스 solution을 출발점으로 추가 규칙+레퍼런스 변경분 작성
   → oracle 골든 → 새 카드(또는 카드 버전) 적재. 프롬프트에 베이스 solution을 컨텍스트로 줄지 검토.
3. **확장 생성 런(★go)** — gemma가 확장 구현 → 채점. 맨바닥보다 적은 시도/비용으로 되면 도구 가치 입증.
- **런은 사용자 go 전 금지.** 재적재: 카드#1=`bank_init.py`, 카드#2=`bank_add_2048.py`.

## 기계 정본
- 장부: `golem/golem_ledger.jsonl`(시도별 ok·first_divergence·cost). 후보: `runs/golem/<ts>/attemptNN/`.
- 정답지: `golem/golden/scenarios.json`(시나리오 파티+정답, make_golden으로 재생성). 오라클: `grade.py`(콜0).
- 재사용: arag `llm.py`(gemma 호출), `game/`(레퍼런스·골든 소스), `frozen/T-000012`(파이썬 대조군).
