# HANDOFF.md — 진행상황 스냅샷

> 새 세션은 이 파일 먼저. 지침 = [CLAUDE.md](CLAUDE.md), 계획 = [PLAN.md](PLAN.md).
> 최신 상태만 둔다. 전체 세션 프로즈는 git 히스토리에.

## 지금 어디 (2026-06-13)

- **본체 완성·가동 중**: 설계→구현→게이트(정적+Docker)→채점→비평→개선 루프 +
  배치 모드 + 폰 대시보드. 테스트 249개 통과(tests/ 한정 실행).
- **2차 방향 확정**: 관측 데이터 중심 실험 장치로 재정의. 관측 체계 0단계
  (`observability.py`) 적용됨.
- **Design Bank B0 완료**: `bank_schema.py`(task_card v1 + 고정어휘 검증, 외부태그 거부)
  + `bank_db.py`(SQLite CRUD + goal해시·제목유사도 중복감지). 콜 0, 본체 비오염.
- **B1 완료**: `bank_llm.py`(GemmaDesigner=31B) + `bank_generate.py`(밸런서+재요청).
  31B로 카드 49장 생성, 검증 통과율 100%, 레벨 9/10/10/10/10 분산. `design_bank.sqlite`.
- **B2 코드 완료**: `--task-id` 접점(orchestrator, level과 동일 패턴) + `bank_run.py`
  (카드 단발 런, batch 미사용→배치 improve 차단) + `bank_report.py`(태그/레벨 조인 리포트).
- **B2 측정 환경 = 격리 worktree** `../arag-bank` (브랜치 `bank-b2-env`).
  결정: ① 정상 비평루프 유지(--rounds 기본) ② 배치 improve 차단(batch.py 미사용)
  ③ 학습파일 3종(lessons/critique_notes/evaluator_mistakes) **빈 상태**로 격리
  → 카드별 독립·재현 측정 + 본진 비오염. PROJECT_ROOT가 worktree라 runs/도 자동 분리.
  테스트 합계 265개 통과(tests/ 한정).
- **누적**: 82런, 성공 51 / 실패 31 (인프라 13 = 42%, junk 2 = 6.5%),
  artifact 평균 4.03, 유용 부산물당 $0.0194, 누적 $1.45.

## 돌고 있는 것

- **배치 없음**. readme-usability 배치(08:22 시작)는 09:00 `infra-outage`로 종료 —
  20개 요청 중 4개만 완주(성공 1, improve 1). README 가설은 표본 부족으로 미측정 → 재가동 필요.
- 26B(generator)가 새벽 시간대 500을 자주 뱉음 (3일째 패턴). `watch_resume.py`로
  복구 감시 가능.

## 다음 액션 (택1)

1. **B2 캠페인 실행** — `../arag-bank`에서 `python bank_run.py 20` (또는 30).
   카드 한 장씩 단발 런 → `python bank_report.py`로 태그별 붕괴 지점 첫 데이터.
   콜·시간 큰 작업(26B+31B, 도커). 끝나면 **스키마 v1 확정** 판단.
   ※ 본진(C:\Users\USER\arag)이 아니라 **worktree에서** 돌릴 것.
2. readme 실험 배치 **재가동** (26B 13시 이후 안정 확인됨) → NOCHANGE·README 지적률.
3. 프롬프트 실험 다음 후보 (PLAN §4): improve 계획 다이어트.

## 먼저 읽을 것

- 지침·역할분리·가드레일 → CLAUDE.md
- Design Bank 명세·단계, 실험 대기열 → PLAN.md
- 실패 분류·점수 규칙(정본) → `observability.py` 도크스트링
- 런 장부 → `runs/index.json` (prompt_version·level·score_split 포함)
- 분석 도구(콜 0) → `analyze_batch.py`, `observability.py`

## 기계 정본 (사람 문서보다 우선)
`runs/index.json` · `runs/*/events.jsonl` · `lessons.json` ·
`critique_notes.json` · `evaluator_mistakes.json` · `auto_state.json`
→ 문서와 충돌하면 이쪽이 진실.

---

## 실험 기록 (prompt_version별)

> 프롬프트(prompts.py / reviewer.py) 바꾸면: ① PROMPT_VERSION 갱신 ② 여기 추가.
> 형식: 날짜-변경요약. index.json에 찍혀 전후 비교의 분모를 가른다.

### 약속-커버리지 규칙 (2026-06-12, 버전문자열 없이)
- 목적: perfect-but-gap(만점인데 총평 지적) 감소. 변경: design_prompt에
  "수용기준은 아이디어의 약속을 검증, 기준 수 늘리지 말고 범위 정렬"
- **결과: 효과 미검출** (만점 총평 10/10 지적). 단 NOCHANGE 0/18 + 지적 결이
  약속위반→README 트집으로 이동 → 리뷰어 출구 문제가 측정을 가림

### 20260612-reviewer-nochange-exit (커밋 4e22912)
- 목적: 리뷰어가 NOCHANGE를 전혀 안 씀(0/18) 교정. 변경: review_prompt에
  판정 순서 — "벽"(약속 미이행/실행 불가/오해 유발)만 SUGGEST, nice-to-have는 NOCHANGE
- **측정(누적 총평 2건)**: 둘 다 SUGGEST지만 **질적 변화** — 트집 소멸, 둘 다
  "벽"(README 설치/사용법 부재)에 부합. 새 가설: 리뷰어가 후한 게 아니라
  README가 진짜 부실 → 아래 버전으로 이어짐

### 20260613-readme-usability (커밋 915949c, 측정 중)
- 목적: README 부실 가설 검증 (좋아지면 NOCHANGE가 자연히 나와야)
- 변경: readme_prompt에 HARD RULE("README만으로 설치·실행 가능") + 필수 섹션 5개
  (설치/빠른시작/사용법:모든 서브커맨드 예시/입력파일 형식)
- 관찰: README 계열 지적률(현재 2/2), NOCHANGE 등장 여부, README 생성 실패율
- **현황**: 적용 직후 20회차 배치 가동 — 결과 대기

---

## 세션 다이제스트 (1줄 요약, 상세는 git)

- **1~6차**: 본체 구축 — 설계 스키마, 정적 게이트, 오케스트레이터, Docker 게이트,
  부분합격·중재·자동개선 루프, idea_factory 적응형 난이도, 배치 모드.
- **7차**: 하네스 글 반영 — 평가자 노트(31B 교정 자료), improve 체인 깊이 2,
  regression/capability 분리, 컨텍스트 계측, 약속-커버리지 규칙.
- **8차**: 외부 리뷰 반영 — orchestrator 1,299줄을 phase_* 믹스인 7개로 분해,
  prompt_version 장부화, README 운영 문서화. 배치 로그 줄버퍼링, git 콘솔 숨김.
- **9차**: 대시보드 v3 — 팩토리오 폐기, "지금" 포커스 + 게이트 점검표 + 탭 3개
  (현황/기록/지표), REPORT 렌더링, 화면 고정 + 단계 경과시간.
- **10차**: 2차 방향 확정 — observability.py 0단계, Design Bank 계획, 문서 정리
  (CLAUDE/PLAN/HANDOFF 3분할).
