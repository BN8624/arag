# PLAN.md — ARAG 계획

> 지침은 [CLAUDE.md](CLAUDE.md), 진행상황은 [HANDOFF.md](HANDOFF.md).
> 이 문서는 **앞으로 할 일과 그 명세**만 담는다. 끝난 일은 HANDOFF로 간다.

## 0. 큰 그림 (2026-06-13 확정)

ARAG의 1차 산출물은 코드가 아니라 **관측 데이터** — "저가 모델의 장기 루프
적합성을 측정하는 실험 장치". 두 트랙을 병행한다:

- **본체(실행 루프)**: 계속 돌며 측정 데이터를 쌓는다. 프롬프트 실험은 배치당 1개.
- **Design Bank(별도 모듈)**: 통제된 과제 재료를 공급한다. 본체와의 접점은
  task_id 한 지점뿐 — 따로 개발하다 마지막에 붙인다.

진행 순서: **관측 체계(0단계, 완료) → Design Bank B0~B5 → 관측판 확장.**

---

## 1. 관측 체계 (0단계 — 완료, observability.py)

실패의 상위 원인과 부산물 가치를 콜 0으로 기계 채점. 상세 규칙은 코드가 정본.

### limit_type — 실패의 상위 원인
모든 실패는 단순 "모델 실패"가 아니라 상위 원인으로 먼저 분류한다.
근거가 명확할 때만 분류하고, 애매하면 **UNKNOWN**(억지 분류 금지 —
UNKNOWN 비율 자체가 taxonomy 보강 신호).

- `MODEL_LIMIT` — 같은 에러 반복, 시그니처 계속 깨뜨림, 수리 예산 소진,
  로그 읽고도 엉뚱한 수정 (no-progress / budget-exhausted / design-rejected)
- `LOOP_LIMIT` — 루프 구조가 기회를 못 줌 (수리 기회 부족, rollback 없음,
  실패 로그 전달 실패, 시간 예산 초과)
- `SPEC_LIMIT` — 시험/기준 결함 (31B 테스트 과함, 중재 blame=test, 시험지 재생성)
- `INFRA_LIMIT` — 외부 장애 (500/429/네트워크/타임아웃/pip 설치 실패).
  **오답노트에 넣지 않는다** — 학습 가능한 실패가 아니다
- `UNKNOWN` — 근거 불충분 (예: improve 계획 파싱 실패 — 모델 출력 불량일 수도,
  프롬프트 비대일 수도)

### artifact_score 0~5 — 부산물 가치 (전부 events 기계 채점)
- +1 design.json이 구조적으로 유효
- +1 events가 실패 위치를 특정 (게이트 지적/설계 반려/트레이스백)
- +1 실패 유형이 taxonomy에 매핑됨 (UNKNOWN이 아님)
- +1 오답노트로 전환된 교훈 있음 (lesson-recorded)
- +1 재현 가능 (llm_calls.jsonl 녹음 → --replay 가능)

품질: **good(4~5) / bad(2~3) / junk(0~1)**. 가장 나쁜 건 실패가 아니라
**관측 불가능한 실패(junk)** — 줄여야 할 건 실패율이 아니라 junk 비율이다.

### 비용 = 정보 비용
성공 비용이 아니라 "돈 써서 무슨 정보를 얻었나"로 본다.
1차: `cost_per_useful_artifact`(= 비용 / (성공 + good 실패)). 적용됨.
후행(데이터 쌓인 뒤): `cost_per_new_failure_class`, `cost_per_level_boundary_found`
— "새 클래스 / 한계선 발견" 판정 기준을 Design Bank B2 데이터 보고 정의.

---

## 2. Design Bank — 명세

### 2.1 목적
좋은 아이디어를 많이 저장하는 게 아니라, **실험 가능한 과제를 구조화해
모델 한계 측정에 쓰는 것**. 과제는 아이디어가 아니라 `task_card` 단위.

좋은 task_card 조건: 요구사항 명확 / 테스트 가능 / 난이도·태그 부착 /
예상 실패모드 / 실행 결과와 연결 가능 / 실패해도 관측 로그를 남김.

### 2.2 task_card 스키마 (v1)
```json
{
  "task_id": "T-000001",
  "source_model": "gemma-31b",
  "title": "CSV log summarizer with CLI options",
  "goal": "작은 CSV 로그를 읽고 상태별 요약을 출력하는 CLI 도구.",
  "difficulty_level": 2,
  "difficulty_tags": ["cli_arg_surface", "parser_logic", "stateful_io"],
  "expected_failure_modes": ["argument_parsing_error", "missing_edge_case"],
  "acceptance_criteria": ["--input 경로를 받는다", "status별 개수를 출력한다",
                          "빈 파일과 잘못된 컬럼을 처리한다"],
  "required_files": ["main.py", "parser.py", "tests/test_cli.py"],
  "test_oracle": "pytest 기준 전체 통과",
  "anti_goals": ["웹 서버 금지", "외부 DB 금지"],
  "notes_for_evaluator": "파일 I/O와 CLI 인자 표면을 동시에 보는 과제",
  "design_quality_score": null,
  "created_at": "AUTO",
  "schema_version": "task_card.v1"
}
```

### 2.3 고정 어휘 (자유입력 금지 — 검증이 외부 태그를 거부)

**difficulty_tags (12종)** — 난이도는 level 숫자보다 태그 조합이 중요:
`multi_file_contract` 여러 파일 간 함수명·import·시그니처 계약 /
`stateful_io` 파일 저장·로드, 상태 관리 / `numeric_precision` 부동소수·반올림·오차 /
`cli_arg_surface` CLI 인자·옵션·도움말·입력 검증 / `regression_sensitive` 기존 기능 보존 /
`parser_logic` 텍스트·CSV·JSON·로그 파싱 / `external_mock` 외부 API·네트워크 mock /
`test_generation` 테스트 설계 자체가 핵심 / `schema_validation` JSON·구조 검증 /
`error_handling` 예외·사용자 친화적 실패 / `refactor_required` 구조적 정리 /
`context_heavy` 긴 문맥 유지·요구사항 추적

**expected_failure_modes (13종)** — 실행 결과와 비교할 기준:
`import_mismatch` `signature_drift` `missing_edge_case` `argument_parsing_error`
`test_contract_mismatch` `state_persistence_error` `numeric_tolerance_error`
`parser_boundary_error` `regression_introduced` `mocking_failure`
`schema_violation` `overengineering` `under_specification`

**difficulty_level (1~5)**: 1 단일파일·단순함수 / 2 작은 멀티파일·CLI·파일I/O /
3 멀티파일 계약·상태관리·회귀방지 / 4 복잡한 설계변경·다단계·예외 다수 /
5 장기루프 한계측정용(여러 실패모드 동시·컨텍스트 유지 강요)

### 2.4 DB 구조 (SQLite 단일 파일 `design_bank.sqlite`)
- `tasks` (task_id PK, source_model, title, goal, difficulty_level, task_json,
  design_quality_score, created_at, schema_version)
- `task_tags` (task_id, tag) / `expected_failure_modes` (task_id, failure_mode)
- `task_reviews` (review_id PK, task_id, reviewer_model, review_json,
  revised_difficulty_level, design_quality_score, created_at)
- `run_results` (run_id PK, task_id, model_profile, success, artifact_score,
  limit_type, failure_class, cost_usd, report_path, events_path, created_at)
  — **정본 아님. runs/index.json에서 파생** (정본 충돌 방지)

### 2.5 모델별 역할 (1차 수집 목표)
| 모델 | 역할 | 목표 수량 |
|---|---|---:|
| 31B | 기준선 설계자 (스키마·태그 고정) | 300~500 |
| Gemini 3.5 Flash | 대량 설계자 (분포 채우기) | 1,000~2,000 |
| Gemini 3.1 Pro | 고품질 설계자 (level 4~5) | 200~300 |
| Gemini 3.1 Pro | 검수자 (난이도 재판정·태그 보정) | 300~500 |

---

## 3. Design Bank — 개발 단계 (병행, 격리)

### 격리 규칙 (본체 비오염)
1. **코드 격리**: `bank_*.py` + `design_bank.sqlite`만.
   orchestrator/batch/gates/prompts는 수정 금지 (접점 2곳 제외)
2. **접점 딱 2곳, B2에서만**: orchestrator `--task-id` 인자 → index에 task_id 기록(3줄);
   batch 아이디어 출처에 "bank에서 뽑기" 옵션 추가 (idea_factory 대체 아님, 병렬)
3. **실험 비오염**: 카드 생성은 실행 프롬프트를 안 바꾸므로 실험과 독립.
   31B 생성은 critic RPD를 쓰니 **배치 쉬는 시간에** (RPD 1,500 중 배치 ~200/일, 여유)
4. **모델 격리**: Gemini는 `bank_llm.py`에 한정. 본체 llm.py 수정 금지
5. 모든 모듈 콜 0 테스트 가능 (mock 설계자 주입)

### 모듈 구성
```
bank_schema.py    task_card v1 + validation (고정 어휘 외 거부, 동의어 금지)
bank_db.py        SQLite CRUD + 중복 감지(goal 정규화 해시 + 제목 유사도)
bank_generate.py  설계자 호출 + 분포 밸런서(부족 태그×레벨 우선) + 파싱 재요청 1회
bank_llm.py       provider 분리: gemma(기존 LLMClient) / gemini(B3에서 추가)
bank_report.py    태그×레벨 매트릭스 채움 현황 (콜 0) + 대시보드 섹션(B2 이후)
```

### 단계 (완료 기준)
- **B0 스키마+DB** (콜 0, 첫 작업, 배치와 무관)
  완료: 예시 카드 통과 + 외부태그·중복·스키마누락 전부 거부 테스트 통과
- **B1 31B 파일럿 50장** (콜 ~60, 무료)
  완료: validation 통과율 ≥90% + **사용자가 샘플 10장 폰 검토 OK** → 스키마 수정
- **B2 실행 검증 + 접점 연결** (코드 완료, 캠페인 실행 대기)
  카드 20~30장을 한 장씩 단발 런으로 완주 → observability와 조인해 **태그별 붕괴 지점 첫 데이터**.
  완료: task_id가 index↔bank 왕복 조회 + 태그별 결과 리포트 → **스키마 v1 확정**.
  - **측정 환경**: batch.py를 거치지 않고 `bank_run.py`로 단발 런(배치 improve 차단).
    런 안 비평루프는 유지(정상 루프 측정). 격리 worktree `../arag-bank`(브랜치
    `bank-b2-env`)에서 실행 — 학습파일 3종을 빈 상태로 두어 카드별 독립 측정 +
    본진 비오염. `--task-id` 접점만 본진 main에 머지됨(코어 로직 무변경).
  - 왜 worktree: lessons/critique_notes/evaluator_mistakes 경로가 PROJECT_ROOT
    하드코딩이라 플래그로 못 끈다. 코어 수정 없이 격리하려면 별도 체크아웃이 정답.
- **B3 Gemini 대량 생산** (크레딧 시작): 3.5 Flash 1,000~2,000장, 부족 조합 우선
- **B4 3.1 Pro 검수**: 고난도 200~300 + 검수 300~500, source_model 분리(편향 비교)
- **B5 관측판 확장**: 태그별 성공률·artifact_score, 모델별 붕괴 태그 조합

### 사용자 결정 지점
- B1 종료 시: 샘플 10장 검토 (폰, 5분)
- B3 진입 전: Gemini 키·크레딧 확인 + 1차 생산량 (1,000 vs 2,000)

### 위험 대응
쓰레기통화 → B1·B2 소량-검증-수정 강제, **대량 생산은 B2 끝나기 전 금지** /
모델 편향 → source_model 분리(B0부터) / 태그 혼란 → 고정어휘 외 검증 거부(B0부터) /
정본 충돌 → run_results는 파생 뷰로만(B0 결정)

---

## 4. 프롬프트 실험 대기열 (본체, 배치당 1개)

> 실험 규칙·측정 결과는 HANDOFF "실험 기록"에. 여기엔 **다음에 할 후보**만.

1. **improve 계획 프롬프트 다이어트** — 30,000자 도달 + "no usable plan" 중단
   누적 5건+. 컨텍스트 계측상 전 단계 최대(평균 22K자). 설계 전문+전체 코드를
   다 싣는 구조를 슬림화
2. **XML 태그 구획화** — 대문자 헤더(`ORIGINAL DESIGN:`)를 `<design_contract>` 류
   태그로. gemma 4 효과 미검증이므로 단독 실험 + 한 방 수정률 전후 비교.
   기대 효과 지점: 수리 프롬프트의 에러로그·파일·지시 경계 혼동
3. **outcome 중심 checks 강화** — stdout 매칭↓, 파일·JSON 내용 확인 선호
4. **비평가 UNKNOWN/NOCHANGE 출구** — 리뷰어가 계속 SUGGEST면 추가 조임

### 계약 협상 (2차 후보로만)
26B 자유 질의가 아니라 "정적 모호성 감지(콜 0) → 걸리면 31B 1회 재설계" 형태.
covered_by 커버리지 정적 검증과 함께 검토.
