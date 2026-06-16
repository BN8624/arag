# CLAUDE.md — golem (gemma 워커 × JS 게임 룰엔진)

## 이게 뭔가
golem = ARAG의 서브프로젝트. gemma 워커가 **JS 게임 룰엔진**을 짓고 Claude는 조율만 한다.
목적은 연구가 아니라 실용 — **사용자가 Claude를 쓸 때 Claude 사용량을 줄이는 것.**
gemma = 손(구현), Claude = 머리(계약·조율·바인딩), 사용자 = 방향·밸런스.
정체·Phase는 README.md, 결정 이유는 context-notes.md, 현재상태·다음할일은 HANDOFF.md.

## 현재 우선순위 (Golem Studio 선회, 2026-06-17)
- 현재 다음 작업은 `GolemStudioMode.md`의 **Golem Studio v0.1 Contract Microkernel Replay**다.
- 예전 HANDOFF의 생산 분할 Step 1 오케스트레이터 계획은 폐기된 예정분으로 보고, 새 작업순서로 되살리지 않는다.
- v0.1은 실제 Gemini/Gemma API 호출 없이 fake artifact와 replay validator만 만든다.
- v0.1에서 11개 키는 독립 인격이 아니라 향후 사용할 **worker slot / 병렬 샘플링 슬롯** 개념이다.
- 이 문서의 “gemma=손, Claude=머리”는 기존 부품공장 방식 설명이다. Golem Studio Mode에서는 Gemma를 설계·리뷰 샘플링 슬롯으로도 쓸 수 있다.
- 이 문서와 `GolemStudioMode.md`가 충돌하면, Golem Studio 구현 범위에서는 `GolemStudioMode.md`와 `HANDOFF.md`를 우선한다.

## 사용자 (arag와 동일)
- 바이브코더. 코드 안 읽는다. "되나/안되나" + 사람 말 요약으로 판단. 거의 폰에서 작업.
- 작업방식: Claude가 사람 말로 먼저 제안 → 사용자가 듣고 막히면 되묻고 → 이해된 건 진행.
- **결정할 게 없으면 단계마다 멈추지 말고 쭉 진행.** 멈추는 건 진짜 갈림길 + 키 쓰는 실제 런 직전뿐.
- 구현 중 코드 설명·중계 금지. 게임 개념도 처음이니 풀어서 설명한다.

## 모델 / 키 (arag 공유 — llm.py 재사용)
- 무료 gemma 4 31B(generator role, 31solo). 구글 AI Studio. llm.py가 페이서·키풀·RPD·재시도 담당.
- 쿼터: 키당 RPM 15(페이서가 보호), RPD 1,500, 단일출력 32k. 키 11개.
- ⚠️ **런은 사용자 명시 지시 전엔 안 돌린다**(키 소비). ARAG 캠페인과 키 경쟁 금지 — 동시 가동 말 것.

## 산출물 규격 (golem 고유 — arag는 Python, golem은 JS)
- 언어 = **JavaScript (Node.js)**. 그릇 = JS/웹(턴제 RPG·로그라이크·카드·시뮬·오토배틀러).
- **CommonJS 멀티파일**(require/module.exports), 진입점 main.js. 단일파일·껍데기모듈 금지.
- **Node 빌트인만**(npm·네트워크·FS·stdin 금지). 결정적(Math.random 금지).
- 출력 계약은 **정확일치**로 채점(winner/turns/엔티티HP). 정답 수치는 워커에 비노출(모델이 계산).

## 부품 추가 시 시연 필수 (사용자 규칙, 2026-06-16)
- **부품이 게이트를 통과하면(합의율 측정으로 끝내지 말고) 반드시 "시연"을 만든다.** 사용자는
  바이브코더라 숫자(11/11)가 아니라 *눈으로 되는 걸 봐야* 판단한다.
- 시연 = 통과본을 시나리오에 실제로 돌려, **사람말 요약 + 격자/상태 시각화**(예: 던전 격자에
  `@`=플레이어 `E`=적를 찍어 이동·추격을 보여줌)로 "이 부품이 이렇게 동작한다"를 보인다.
- 시연도 도구로 굳혀 반복 비용을 낮춘다(목표② — 부품마다 손으로 다시 짜지 말 것).

## 파이프라인 (Phase 1)
make_golden.py(정답지) → worker_prompt.py(지시문) → driver.py(키 11개 병렬 select-best, 생성·채점) → grade.py(채점).
골든·오라클 철학은 ARAG game/ + 트레이스diff 재사용. T-000012(파이썬 cracked@2)와 사과-대-사과 비교.

## 가드레일 (arag 계승)
- **병렬 우선**: 테스트·캠페인은 키 11개로 최대 병렬(워커=키, arag select_run 패턴). 단일키 순차 금지.
- select-best 상한 cap(기본 11=키수). 첫 통과 시 미시작 시도 취소.
- 각 시도는 runs/golem/<ts>/attemptNN/에 격리(원본 workspace 안 건드림).
- 키/자격증명은 .env로(arag 공유), 저장소·로그·아티팩트에 키 출력 금지.

## 출력 규칙 (arag 계승)
- 한국어 문장은 마침표로 끝낸다(콜론으로 끝내지 말 것). 콜론은 라벨·키밸류에만.
- 새 소스파일 첫 줄 = 역할 한 줄 한국어 주석.
- 보고는 짧게: 뭘 했나 / 됐나 안 됐나 / 다음. 코드 나열 금지.

## 핸드오프 (arag 계승)
- 새 세션은 HANDOFF.md만 먼저 읽고 시작. 최상단 "▶ 새 세션 여기부터" 블록을 항상 유지.
- 세션 끝낼 때 "지금 어디"·"다음 액션"을 갱신한다.
- 문서 역할: HANDOFF=현재/다음, CLAUDE.md=규칙, README=정체, context-notes=결정로그(왜), checklist=세부.
