# HANDOFF.md — golem 현재 위치와 다음 액션

## 지금 어디 (2026-06-17)

- **Golem Studio v0.1 Contract Microkernel Replay 완료.** `golem/studio/`에 구현됨.
- replay 5/5 통과(API 0회). 통과 픽스처 ok:true, 음성 4종(export불일치·파일누락·순환·bare default) 각각 지정 check에서 실패.
- `static_gate.py`를 src/ 하위폴더 지원(rglob+경로해소)으로 확장했고, 기존 평면 게임 무회귀 확인(merge-2048 ok:true 유지).
- 산출물: `golem/studio/contract_validator.py`, `replay.py`, `schemas/module_manifest.schema.json`, `fixtures/demo_*`(픽스처 5종), `replay_result.json`, `contract_validation_report.md`. (`runs/`는 .gitignore — Step 2+ 생성물용으로 비워둠.)
- 다음은 **Step 2 — Planning 팀만 실제 worker slot 투입**이다. 단 키를 쓰므로 사용자 go 전에는 안 돈다.
- 구현 전 반박/결정은 context-notes G25 참조(역할순환 포장 비판, A/B/C 선측정, bare-default 주의).

## 다음 액션

1. (키 필요 — 사용자 go 대기) Step 2 들어가기 전에 A/B/C 비교(single / 1+3 / 1+10 reviewer)를 Planning 한 단계에서 먼저 설계한다. 전체 6단계 파이프라인을 다 짓기 전에 reviewer 추가가 unique issue를 늘리는지부터 측정한다.
2. Planning 팀 실행 골격(planning_lead 1 + reviewer N → ambiguity_review.json → synthesis → contract_packet)을 짠다.
3. 성공 기준: BLOCKING questions 0, concept.md/gdd.md/ambiguity_review.json 생성, contract_packet 검증 통과.

실제 키 사용, worker slots 투입은 사용자 명시 go 뒤에만 한다(메모리 no-autostart-runs).
