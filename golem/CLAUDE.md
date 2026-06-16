# CLAUDE.md — golem 작업 규칙

## 문서 우선순위

- 현재 위치와 다음 액션은 `HANDOFF.md`만 본다.
- Golem Studio 설계 정본은 `GolemStudioMode.md`다.
- 결정 이유는 `context-notes.md`에만 기록한다.
- 진행 체크는 `checklist.md`에만 기록한다.
- 이 문서와 `GolemStudioMode.md`가 충돌하면, Golem Studio 구현 범위에서는 `GolemStudioMode.md`와 `HANDOFF.md`를 우선한다.

## 사용자 방식

- 사용자는 바이브코더다. 코드보다 “되나/안되나”와 사람 말 요약으로 판단한다.
- 결정할 게 없으면 단계마다 멈추지 말고 진행한다.
- 멈추는 시점은 진짜 갈림길이거나 실제 Gemini/Gemma 키를 쓰기 직전이다.
- 구현 중 장황한 코드 설명은 피하고, 결과와 검증을 짧게 보고한다.

## 키 사용

- 사용자 명시 지시 전에는 Gemini/Gemma API 런을 돌리지 않는다.
- ARAG 캠페인과 키 경쟁을 만들지 않는다.
- 키와 자격증명은 저장소, 로그, 아티팩트에 출력하지 않는다.
- v0.1 Contract Microkernel Replay는 키 없이 fake artifact와 replay validator만 사용한다.

## JS 산출물 규칙

- 언어는 JavaScript, 실행은 Node.js다.
- v0.1은 CommonJS only다.
- `require(...)`, `exports.name = ...`, `module.exports = { name }` 패턴을 우선한다.
- npm, 네트워크, FS, stdin 사용은 금지한다.
- `Math.random`은 금지한다.
- 결정적 실행과 정확일치 검증을 우선한다.
- 새 소스파일 첫 줄에는 역할을 설명하는 한 줄 한국어 주석을 넣는다.

## 보고와 핸드오프

- 한국어 문장은 마침표로 끝낸다. 콜론은 라벨, 키밸류, 코드 안에서만 쓴다.
- 보고는 “무엇을 바꿨나 / 무엇을 검증했나 / 남은 위험” 중심으로 짧게 한다.
- 세션 끝에는 `HANDOFF.md`의 지금 위치와 다음 액션을 갱신한다.
