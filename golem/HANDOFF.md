# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터
1. **읽기**: 이 파일 `지금 어디` + `다음 액션`만. 규칙은 CLAUDE.md, 왜는 context-notes.md.
2. **지금 할 일 (한 줄)**: ★**사용자 go 받으면** `python golem/driver.py --card merge-2048` 생성 런 —
   gemma가 결정적 2048을 독립 구현하나(cracked@N?). 준비(레퍼런스·규칙·골든·카드) 다 됨.
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
- Phase 3 2단계(준비 완료, 키 안 씀): **입출력 게임-중립화** — 골든=평면 `key:value` 정확일치,
  입력=임의 JSON. 카드#1 무회귀 4/4 유지. **카드#2 'merge-2048'**(결정적 2048) 적재 —
  Claude 레퍼런스(board/moves/main.js)+규칙+4시나리오, oracle 골든, self-채점 PASS.
  → 남은 건 gemma 생성 런(★go 필요).
- 방향(사용자): A 방식으로 여러 게임 만들어 은행에 쌓고 베이스로 확장. = ARAG Design Bank의 golem판.

## 다음 액션 (★다음 세션 여기부터)
1. **★생성 런 (사용자 go 필요, 키 씀)** — `python golem/driver.py --card merge-2048`.
   gemma가 결정적 2048을 독립 구현 → 카드 골든 정확일치 채점 → cracked@N 보고.
   - cracked면: 통과본을 카드 solution에 갱신(`game_bank.save_card` 또는 별 스크립트), "A 방식이
     처음 보는 게임에도 된다" 확정 → 3단계(확장)로.
   - NOT CRACKED면: first_divergence 패턴 분석. **모델 탓 전에 RULES↔레퍼런스 계약 불일치부터 의심**
     (프로젝트 핵심 교훈). 규칙 모호하면 보강 후 재시도.
2. (3단계) 은행 카드를 베이스로 "메카닉 하나 더" 확장이 되는지. 여기까지면 도구 완성형.
- **런은 사용자 go 전 금지.** 재적재: 카드#1=`bank_init.py`, 카드#2=`bank_add_2048.py`.

## 기계 정본
- 장부: `golem/golem_ledger.jsonl`(시도별 ok·first_divergence·cost). 후보: `runs/golem/<ts>/attemptNN/`.
- 정답지: `golem/golden/scenarios.json`(시나리오 파티+정답, make_golden으로 재생성). 오라클: `grade.py`(콜0).
- 재사용: arag `llm.py`(gemma 호출), `game/`(레퍼런스·골든 소스), `frozen/T-000012`(파이썬 대조군).
