# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터
1. **읽기**: 이 파일 `지금 어디` + `다음 액션`만. 규칙은 CLAUDE.md, 왜는 context-notes.md.
2. **지금 할 일 (한 줄)**: Phase 3 **2단계 — 새 게임 1개를 A 방식으로 생성**. Claude가 새 게임
   레퍼런스(JS)+규칙 작성 → `oracle.py`로 골든 → `game_bank`에 카드 적재 → `driver --card <slug>`로
   gemma 생성(★키 씀 = 사용자 go 필요). 어떤 게임(장르)으로 갈지 사용자와 먼저 정한다.
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
- Phase 3 1단계: **검증엔진 라이브러리(은행)** 골격 완성.
  · `game_bank.py`(sqlite 카드 은행) — 카드#1 'tempo-combat' 적재(규칙·시나리오·골든·솔루션).
  · `oracle.py`(JS 레퍼런스→골든, **game/ 의존 제거** = A경로) — 솔루션에서 골든 4/4 재현.
  · driver/worker_prompt/grade 카드 파라미터화(`--card`), 기본·카드 경로 둘 다 PASS.
- 방향(사용자): A 방식으로 여러 게임 만들어 은행에 쌓고 베이스로 확장. = ARAG Design Bank의 golem판.

## 다음 액션 (★다음 세션 여기부터)
**Phase 3 2단계 = 새 게임 1개를 A 방식으로 생성(★키 씀 — 사용자 go 필요).**
1. **장르/게임 정하기** — 타깃 장르(turn-rpg·autobattler·card·sim·roguelike) 중 하나로 작은 새 게임.
   사용자와 먼저 합의(어떤 게임을 만들지).
2. **A 오라클 만들기(키 안 씀)** — Claude가 그 게임의 JS 레퍼런스 impl + 규칙 스펙 + 시나리오(파티)
   작성 → `oracle.golden_from_reference`로 골든 생성 → `game_bank.save_card`로 카드 적재.
3. **생성 런(★키 씀, go 필요)** — `python golem/driver.py --card <slug>`로 gemma가 독립 구현,
   카드 골든으로 채점. cracked되면 통과본을 카드 solution에 갱신(확장 베이스). 안 되면 first_divergence 분석.
4. (3단계) 은행 카드를 베이스로 "메카닉 하나 더" 확장이 되는지. 여기까지면 도구 완성형.
- **런은 사용자 go 전 금지.** 참고: 카드#1은 `python golem/bank_init.py`로 언제든 재적재.

## 기계 정본
- 장부: `golem/golem_ledger.jsonl`(시도별 ok·first_divergence·cost). 후보: `runs/golem/<ts>/attemptNN/`.
- 정답지: `golem/golden/scenarios.json`(시나리오 파티+정답, make_golden으로 재생성). 오라클: `grade.py`(콜0).
- 재사용: arag `llm.py`(gemma 호출), `game/`(레퍼런스·골든 소스), `frozen/T-000012`(파이썬 대조군).
