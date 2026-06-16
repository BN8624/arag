# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터
1. **읽기**: 이 파일 `지금 어디` + `다음 액션`만. 규칙은 CLAUDE.md, 왜는 context-notes.md.
2. **지금 할 일 (한 줄)**: `golem/web/battle.html` 관전기를 사용자가 폰에서 보고 피드백 →
   다음 표현층 작업(연출 강화/인터랙티브화) 또는 새 시나리오. (Phase 2 1차 산출물 완료.)
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
**Phase 1 완료(엔진 검증) → Phase 2 진행 중(표현층 = 이모지 스킨).**
- Phase 1: 런 `20260616-130305` cracked@10, 5/11 통과. attempt01·10 독립 재채점 4/4(우연 아님).
- Phase 2 표현층: 엔진을 `golem/web/engine.browser.js` 공유 모듈로 분리(단일 진실원). 그 위에
  스킨만 갈아끼우는 구조. 룩 비교 목업(samples.html)에서 사용자가 **이모지** 선택.
  `battle.html` = 공유엔진 + 이모지 스킨(데미지숫자·들썩·흔들림·스킬아이콘). 무회귀 4/4 유지.
- 폰 확인: 테일스케일 `http://100.89.73.83:8731/golem/web/battle.html` 접속 OK.
- 핵심 통찰(사용자): 엔진/trace 공통 + 껍데기(SKIN)만 교체 = 같은 전투를 여러 룩으로. 구조로 반영됨.

## 다음 액션 (★다음 세션 여기부터)
**Phase 2 방향 = 표현층 바인딩(사용자 선택). 1차 산출물 완료 — `golem/web/battle.html`.**
1. **사용자 피드백 받기**: 폰에서 `golem/web/battle.html` 열어(로컬: `python -m http.server`로
   서빙 후 `/golem/web/battle.html`) 관전기 보고 "되나/손맛" 판단. 무회귀는 `node golem/web/_verify.js`(4/4).
2. 피드백에 따라 다음 중 하나.
   - 연출 강화(데미지 숫자 플로팅·HP 깎임 애니·타겟 표시) — 엔진 무수정, 표현층만.
   - **인터랙티브화**(스킬 선택 플레이) — 엔진의 자동 rotation을 입력 기반으로. 이건 메카닉 변경이라
     골든 재생성·재검증 필요(별 작업으로 취급).
   - 새 시나리오/카드 추가 — make_golden으로 골든 늘리고 관전기 드롭다운 확장.
3. **런은 사용자 go 전 금지.**

## 기계 정본
- 장부: `golem/golem_ledger.jsonl`(시도별 ok·first_divergence·cost). 후보: `runs/golem/<ts>/attemptNN/`.
- 정답지: `golem/golden/scenarios.json`(시나리오 파티+정답, make_golden으로 재생성). 오라클: `grade.py`(콜0).
- 재사용: arag `llm.py`(gemma 호출), `game/`(레퍼런스·골든 소스), `frozen/T-000012`(파이썬 대조군).
