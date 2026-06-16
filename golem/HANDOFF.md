# HANDOFF.md — golem 진행상황 스냅샷

## ▶ 새 세션 여기부터

1. **먼저 읽기**: 이 파일의 `지금 어디`와 `다음 액션`만 읽는다. 규칙은 `CLAUDE.md`, 새 방향의 상세 설계는 `GolemStudioMode.md`, 결정 이유는 `context-notes.md`다.
2. **지금 할 일 한 줄**: 예전 G20 생산 분할 Step 1은 폐기하고, **Golem Studio v0.1 Contract Microkernel Replay**부터 구현한다.
3. ⚠️ **실제 Gemini/Gemma API 런은 사용자 명시 지시 전엔 금지**다. v0.1은 fake artifact와 replay만으로 검증한다.

## 문서 용도

| 문서 | 용도 | 언제 |
|---|---|---|
| HANDOFF.md | 현재 상태 + 다음 할 일 | 항상 먼저 |
| CLAUDE.md | golem 폴더 전체 규칙 | 처음 1회 |
| GolemStudioMode.md | 새 Golem Studio Mode 설계 정본 | v0.1 구현 전 필수 |
| context-notes.md | 결정 로그 | 왜가 필요할 때 |
| checklist.md | 세부 체크리스트 | 진행 추적 |
| README.md | 기존 golem 정체 | 방향 의심될 때 |

## 지금 어디 (2026-06-17)

**선회 결정**:
- 기존 다음 작업이던 **생산 분할 Step 1 오케스트레이터**는 보류가 아니라 폐기된 예정분으로 본다.
- 새 방향은 `GolemStudioMode.md`에 정리한 **Golem Studio Mode**다.
- 핵심은 11개 Auth Key를 독립 인격이 아니라 **11 worker slots / 병렬 샘플링 슬롯**으로 쓰는 것이다.
- 단, 바로 11개 슬롯을 투입하지 않는다. 먼저 키를 쓰지 않는 v0.1 계약 검증 마이크로커널을 만든다.

**현재 정본**:
- 새 설계 정본: `golem/GolemStudioMode.md`.
- 구현 시작점: `Contract Microkernel Replay`.
- v0.1 목표: 게임 생성이 아니라 **manifest에 적힌 파일/export/import와 실제 CommonJS 코드가 기계적으로 일치하는지 검증**하는 것.
- v0.1 module format: **CommonJS only**.
- v0.1 manifest 최소 필드: `schema_version`, `module_format`, `entry`, `files[].path`, `files[].exports`, `files[].imports`.
- v0.1 static_gate bridge 입력: `workspace_path`, `manifest_path`.
- v0.1 static_gate bridge 출력: `ok`, `checks`, `errors`, `warnings`.

**기존 성과는 버리지 않는다**:
- `static_gate.py`, `grade.py`의 Node 권한모델 실행 격리, CommonJS 멀티파일 규칙은 계속 재사용한다.
- 기존 로그라이크 부품과 캠페인 결과는 배경 자료다. v0.1 구현의 직접 목표는 아니다.
- `HANDOFF.md`에 있던 생산 분할 계획은 `context-notes.md`의 G20 기록으로만 남기고, 다음 작업으로 실행하지 않는다.

## 다음 액션 (★다음 세션 여기부터)

### Step 0: 파일 확인

1. `golem/GolemStudioMode.md`의 13장 구현 우선순위와 19장 Pending Decisions를 읽는다.
2. `golem/static_gate.py`의 현재 CLI/함수 구조를 확인한다.
3. 기존 `driver.py`, `grade.py`는 참고만 하고 v0.1에서는 실제 키 호출을 붙이지 않는다.

### Step 1: v0.1 폴더와 fake artifact 생성

`golem/studio/` 하위에 별도 실험 모드로 만든다.

필수 산출물:
- `golem/studio/schemas/module_manifest.schema.json`
- `golem/studio/runs/demo/module_manifest.json`
- `golem/studio/runs/demo/workspace/main.js`
- `golem/studio/runs/demo/workspace/src/engine.js`
- `golem/studio/runs/demo/workspace/src/state.js`
- `golem/studio/runs/demo/workspace/src/movement.js`

새 소스파일은 첫 줄에 한국어 역할 주석을 넣는다.

### Step 2: import/export validator 구현

v0.1 검증 범위:
- manifest JSON schema 검증.
- manifest에 있는 파일이 실제 존재하는지 확인.
- CommonJS only 확인.
- `require(...)`가 manifest의 `imports`와 일치하는지 확인.
- manifest의 named export가 실제 코드에 존재하는지 확인.
- `exports.name = ...` 또는 `module.exports = { name }`만 named export로 인정.
- `module.exports = function ...` 같은 bare default export는 `exports: []`인 entry 파일 외에는 금지.
- 순환 의존성 확인.

### Step 3: static_gate bridge 연결

bridge 입력:

```json
{
  "workspace_path": "golem/studio/runs/demo/workspace",
  "manifest_path": "golem/studio/runs/demo/module_manifest.json"
}
```

bridge 출력:

```json
{
  "ok": true,
  "checks": [],
  "errors": [],
  "warnings": []
}
```

`checks`에는 최소 `manifest_schema`, `file_exists`, `import_export`, `static_gate`를 넣는다.

### Step 4: replay result report 생성

필수 산출물:
- `golem/studio/runs/demo/replay_result.json`
- `golem/studio/runs/demo/contract_validation_report.md`

성공 기준:
- replay 결과 `ok: true`.
- `static_gate`와 import/export validator가 모두 통과.
- Gemini/Gemma API 호출 0회.

### Step 5: 다음 단계로 넘어가기 전 확인

v0.1이 통과한 뒤에만 Planning 팀 실제 호출 Step 2를 논의한다.
그 전에는 11 worker slots, A/B/C 비교 실험, 실제 키 사용을 구현하지 않는다.

## CLAUDE.md 충돌 점검 결과

현재 `CLAUDE.md`와 새 문서의 큰 충돌은 없다.
다만 아래는 우선순위를 명확히 해야 한다.

- `CLAUDE.md`의 “gemma=손, Claude=머리” 표현은 기존 부품공장 방식 설명이다. Golem Studio Mode에서는 Gemma도 설계/리뷰 샘플링 슬롯으로 쓸 수 있다.
- `CLAUDE.md`의 “병렬 우선”은 실제 키 런에만 적용한다. v0.1 Contract Microkernel Replay에서는 키를 쓰지 않는다.
- `CLAUDE.md`의 CommonJS, Node 빌트인만, npm 금지, Math.random 금지 규칙은 v0.1과 일치한다.

## 운영 규칙

- 사용자 `go` 없이 키 쓰는 런 금지.
- ARAG 캠페인과 키 경쟁 금지.
- 기존 `HANDOFF.md` 변경분은 이 문서로 대체되었으므로 예전 생산 분할 다음 액션으로 돌아가지 않는다.
- 세션 종료 시 이 파일의 `지금 어디`와 `다음 액션`을 갱신한다.
