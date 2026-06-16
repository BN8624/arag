# HANDOFF.md — golem 현재 위치와 다음 액션

## 지금 어디 (2026-06-17)

- 예전 G20 생산 분할 Step 1 오케스트레이터 예정분은 폐기했다.
- 현재 활성 방향은 `GolemStudioMode.md`의 **Golem Studio Mode**다.
- 다음 구현 시작점은 **Golem Studio v0.1 Contract Microkernel Replay**다.
- v0.1은 실제 Gemini/Gemma API 호출 없이 fake artifact와 replay validator만 만든다.
- v0.1 목표는 게임 생성이 아니라, manifest에 적힌 파일/export/import와 실제 CommonJS 코드가 기계적으로 일치하는지 검증하는 것이다.
- v0.1 CommonJS 규칙과 manifest/static_gate bridge 기본값은 `GolemStudioMode.md` 19장 Pending Decisions를 따른다.
- `static_gate.py`, `grade.py`의 기존 Node 권한모델 실행 격리와 CommonJS 멀티파일 규칙은 재사용한다.

## 다음 액션

1. `GolemStudioMode.md`의 13장 구현 우선순위와 19장 Pending Decisions를 읽는다.
2. `static_gate.py`의 현재 CLI/함수 구조를 확인한다.
3. `golem/studio/` 하위에 v0.1 fake artifact를 만든다.
4. `module_manifest.schema.json`과 demo `module_manifest.json`을 만든다.
5. demo workspace에 `main.js`, `src/engine.js`, `src/state.js`, `src/movement.js`를 만든다.
6. import/export validator를 구현한다.
7. static_gate bridge를 연결한다.
8. `replay_result.json`과 `contract_validation_report.md`를 생성한다.
9. replay 결과 `ok: true`, static_gate 통과, Gemini/Gemma API 호출 0회를 확인한다.

실제 키 사용, 11 worker slots 투입, A/B/C 비교 실험은 v0.1 통과 뒤에만 논의한다.
