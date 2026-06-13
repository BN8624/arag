# ARAG Design Bank 설계 문서

## 0. 문서 목적

이 문서는 ARAG를 단순 자동 코딩기가 아니라 **저가 모델의 장기 루프 적합성을 측정하는 루프 엔지니어링 실험 장치**로 확장하기 위한 설계 문서다.

핵심 아이디어는 현재 ARAG 실행 루프와 별도로, **설계만 계속 생성하고 태그별·난이도별로 분류해 DB화하는 Design Bank**를 만드는 것이다.

Design Bank는 실행 루프가 사용할 통제된 실험 과제 재료를 제공한다. 즉, 실행 루프는 무작위 과제가 아니라 난이도와 태그가 통제된 과제를 대상으로 모델 한계와 루프 한계를 관측한다.

---

## 1. 핵심 관점

ARAG의 1차 산출물은 코드가 아니라 **관측 데이터**다.

코드는 관측을 발생시키기 위한 테스트 물체에 가깝다. 중요한 것은 최종 결과물이 아니라 루프를 돌리며 생기는 다음 부산물이다.

- `REPORT.md`
- `events.jsonl`
- `design.json`
- 실패 유형
- 반복 에러
- 수정 흔적
- 비용 로그
- 오답노트 후보
- 모델별 난이도 한계선
- 태그별 붕괴 지점

따라서 ARAG의 핵심 질문은 다음이다.

> 이 모델은 같은 루프에서 몇 난이도까지 유용한 실패 부산물을 남기며 버티는가?

---

## 2. 전체 구조

ARAG는 두 개의 루프로 분리한다.

```text
[Design Loop]
31B / Gemini 3.5 Flash / Gemini 3.1 Pro
→ 실험 과제 설계
→ 태그·난이도·예상 실패모드 부여
→ 검수
→ task_db 저장

[Execution Loop]
task_db에서 과제 선택
→ 26B/31B 또는 다른 모델 조합으로 실행
→ 성공/실패/부산물 기록
→ task_id에 결과 연결

[Analysis]
태그별 성공률
태그별 artifact_score
태그별 cost_per_useful_artifact
모델별 붕괴 지점
루프 한계 / 모델 한계 / 스펙 한계 / 인프라 한계 분리
```

---

## 3. Design Bank의 목적

Design Bank의 목적은 좋은 아이디어를 많이 저장하는 것이 아니다.

목적은 **실험 가능한 과제를 구조화해서 모델 한계 측정에 사용하는 것**이다.

따라서 과제는 단순 아이디어가 아니라 `task_card` 단위로 저장한다.

좋은 `task_card`는 다음 조건을 만족해야 한다.

1. 요구사항이 명확하다.
2. 테스트 가능하다.
3. 난이도와 태그가 붙어 있다.
4. 예상 실패모드가 있다.
5. 실행 루프 결과와 연결 가능하다.
6. 실패해도 관측 가능한 로그를 남길 수 있다.

---

## 4. 모델별 역할

### 4.1 31B

31B는 현재 ARAG 루프에서 설계를 담당하는 기준선 모델이다.

역할:

- 기준선 설계자
- 기존 ARAG 스타일의 과제 분포 생성
- 태그 체계와 난이도 기준 초기 검증
- Design Bank의 초기 seed 생성

추천 수량:

```text
31B 설계 카드 300~500개
```

31B 단계의 목표는 대량 생산이 아니라 **schema와 태그 체계를 고정하는 것**이다.

### 4.2 Gemini 3.5 Flash

Gemini 3.5 Flash는 대량 확장용 주력 설계자로 사용한다.

역할:

- 태그별·난이도별 과제 대량 생성
- 빈 태그 조합 보강
- 다양한 과제 유형 확장
- 실행 루프용 task pool 확대

추천 수량:

```text
Gemini 3.5 Flash 설계 카드 1,000~2,000개
```

이 단계의 핵심은 단순히 많이 만드는 것이 아니라, **태그와 난이도 분포를 균형 있게 채우는 것**이다.

### 4.3 Gemini 3.1 Pro

Gemini 3.1 Pro는 대량 생산용이 아니라 고품질 기준선과 검수자로 사용한다.

역할:

- 고난도 설계 생성
- 기존 task_card 검수
- 난이도 재판정
- 태그 보정
- 애매한 과제 수정
- 31B/3.5 Flash 설계 품질 비교 기준선

추천 수량:

```text
Gemini 3.1 Pro 신규 설계 카드 200~300개
Gemini 3.1 Pro 검수 카드 300~500개
```

3.1 Pro는 많이 쓰는 모델이 아니라 **척도를 잡는 모델**로 사용한다.

---

## 5. 1차 수집 목표

30만 원 상당의 Google 크레딧이 있다면, 처음부터 너무 크게 잡지 말고 다음 정도를 1차 목표로 삼는다.

| 모델 | 역할 | 목표 수량 |
|---|---|---:|
| 31B | 기준선 설계자 | 300~500 |
| Gemini 3.5 Flash | 대량 설계자 | 1,000~2,000 |
| Gemini 3.1 Pro | 고품질 설계자 | 200~300 |
| Gemini 3.1 Pro | 검수자 | 300~500 |

1차 목표:

```text
신규 task_card 1,500~2,800개
검수 기록 300~500개
```

이 정도면 태그별·난이도별 실험 재료로 충분히 의미 있는 규모다.

---

## 6. task_card 기본 스키마

모든 설계 모델은 동일한 스키마로 출력해야 한다.

태그와 실패 유형은 자유입력이 아니라 고정 목록에서 선택하게 한다.

```json
{
  "task_id": "T-000001",
  "source_model": "gemma-31b",
  "title": "CSV log summarizer with CLI options",
  "goal": "작은 CSV 로그 파일을 읽고 상태별 요약을 출력하는 CLI 도구를 만든다.",
  "difficulty_level": 2,
  "difficulty_tags": [
    "cli_arg_surface",
    "parser_logic",
    "stateful_io"
  ],
  "expected_failure_modes": [
    "argument_parsing_error",
    "missing_edge_case",
    "test_contract_mismatch"
  ],
  "acceptance_criteria": [
    "CLI에서 --input 경로를 받는다.",
    "status 컬럼별 개수를 출력한다.",
    "빈 파일과 잘못된 컬럼을 처리한다."
  ],
  "required_files": [
    "main.py",
    "parser.py",
    "tests/test_cli.py"
  ],
  "test_oracle": "pytest 기준으로 모든 테스트 통과",
  "anti_goals": [
    "웹 서버를 만들지 않는다.",
    "외부 DB를 사용하지 않는다."
  ],
  "notes_for_evaluator": "파일 I/O와 CLI 인자 표면을 동시에 보는 과제",
  "design_quality_score": null,
  "created_at": "AUTO",
  "schema_version": "task_card.v1"
}
```

---

## 7. difficulty_level 기준

난이도는 숫자 하나만으로 충분하지 않지만, 기본적인 레벨은 필요하다.

### Level 1

단일 파일, 단순 함수, 명확한 입력/출력.

예:

- 문자열 처리
- 간단한 계산
- 단일 파일 파서
- 작은 유틸 함수

### Level 2

작은 멀티파일 또는 CLI/파일 I/O 포함.

예:

- CLI 인자 처리
- CSV/JSON 읽기
- 간단한 테스트 구조
- 에러 처리 일부 포함

### Level 3

멀티파일 계약, 상태 관리, 회귀 방지 요구.

예:

- 여러 모듈 간 함수 계약
- 상태 저장/로드
- 기존 기능 유지
- 테스트 추가/수정 필요

### Level 4

복잡한 설계 변경, 다단계 로직, 예외 처리 다수.

예:

- 플러그인 구조
- 캐시/동기화
- 복잡한 파서
- 실패 복구 로직

### Level 5

장기 루프 한계 측정용 고난도 과제.

예:

- 여러 실패모드가 동시에 존재
- 회귀 방지가 매우 중요
- 테스트와 설계의 정합성이 어려움
- 모델의 컨텍스트 유지 능력을 강하게 요구

---

## 8. difficulty_tags 고정 목록

난이도는 level보다 태그 조합이 더 중요하다.

초기 태그 목록은 다음과 같이 시작한다.

```text
multi_file_contract
stateful_io
numeric_precision
cli_arg_surface
regression_sensitive
parser_logic
external_mock
test_generation
schema_validation
error_handling
refactor_required
context_heavy
```

| 태그 | 의미 |
|---|---|
| `multi_file_contract` | 여러 파일 사이의 함수명, import, 시그니처 계약이 중요함 |
| `stateful_io` | 파일 저장/로드, 상태 관리가 포함됨 |
| `numeric_precision` | 부동소수점, 반올림, 오차 허용 등이 중요함 |
| `cli_arg_surface` | CLI 인자, 옵션, 도움말, 입력 검증이 중요함 |
| `regression_sensitive` | 기존 기능을 깨뜨리지 않는 것이 중요함 |
| `parser_logic` | 텍스트/CSV/JSON/로그 파싱 로직이 중요함 |
| `external_mock` | 외부 API, 네트워크, 파일시스템 등을 mock해야 함 |
| `test_generation` | 테스트 설계 자체가 중요한 과제 |
| `schema_validation` | JSON/schema/구조 검증이 핵심 |
| `error_handling` | 예외 처리와 사용자 친화적 실패가 중요함 |
| `refactor_required` | 기존 코드를 구조적으로 정리해야 함 |
| `context_heavy` | 긴 문맥 유지와 요구사항 추적이 중요함 |

---

## 9. expected_failure_modes 고정 목록

예상 실패모드는 나중에 실행 결과와 비교하기 위한 기준이다.

초기 목록:

```text
import_mismatch
signature_drift
missing_edge_case
argument_parsing_error
test_contract_mismatch
state_persistence_error
numeric_tolerance_error
parser_boundary_error
regression_introduced
mocking_failure
schema_violation
overengineering
under_specification
```

각 실패모드는 실행 루프의 실제 실패 taxonomy와 연결되어야 한다.

---

## 10. limit_type 분류

실패는 단순히 모델 실패로 처리하지 않는다.

모든 실패는 상위 원인인 `limit_type`으로 먼저 분류한다.

```text
MODEL_LIMIT
LOOP_LIMIT
SPEC_LIMIT
INFRA_LIMIT
```

### MODEL_LIMIT

모델이 로그, 계약, 수정 지시를 처리하지 못한 경우.

예:

- 같은 import 오류 반복
- 함수 시그니처를 계속 깨뜨림
- 테스트 로그를 읽고도 엉뚱한 수정
- critic 지적을 반영하지 못함

### LOOP_LIMIT

루프 구조가 충분한 수리 기회, rollback, 메모리, 게이트를 제공하지 못한 경우.

예:

- 수정 기회가 부족함
- 실패 로그가 다음 프롬프트로 잘 전달되지 않음
- rollback이 없어 코드가 계속 꼬임
- 게이트가 실패 원인을 제대로 분리하지 못함

### SPEC_LIMIT

설계, 테스트, 수용 기준이 애매하거나 잘못된 경우.

예:

- 테스트가 요구사항보다 과함
- 수용 기준이 모호함
- 설계와 테스트가 서로 충돌함
- 과제 자체가 모델 비교에 부적절함

### INFRA_LIMIT

모델/루프가 아니라 인프라 문제인 경우.

예:

- 500 에러
- 429 rate limit
- 네트워크 오류
- API 응답 불안정
- 타임아웃

---

## 11. useful_artifact_score

ARAG에서는 실패도 좋은 실패와 나쁜 실패로 나눈다.

실패 런마다 `artifact_score`를 0~5점으로 계산한다.

```text
artifact_score 0~5

+1 실패 위치가 특정됨
+1 실패 유형이 taxonomy에 매핑됨
+1 재현 가능한 명령/로그가 남음
+1 다음 수정 지시나 오답노트로 전환 가능한 교훈이 있음
+1 설계/계약/테스트 중 무엇을 바꿔야 하는지 단서가 있음
```

중요한 것은 성공 여부만이 아니다.

핵심 질문:

```text
실패했더라도 다음 루프에 쓸 수 있는 관측 데이터를 남겼는가?
```

---

## 12. junk_failure 정의

ARAG에서 가장 나쁜 실패는 실패 자체가 아니라 **관측 불가능한 실패**다.

`JUNK_FAILURE`는 다음과 같은 경우다.

```text
- 로그가 비어 있음
- 실패 원인을 특정할 수 없음
- 모델 출력이 형식 위반이라 파싱 불가
- 테스트가 실행되지 않음
- 인프라 오류와 모델 오류가 섞여 구분 불가
- 다음 프롬프트/오답노트로 전환할 교훈이 없음
```

우선적으로 줄여야 할 것은 실패율이 아니라 `JUNK_FAILURE` 비율이다.

우선순위:

```text
성공 > 좋은 실패 > 나쁜 실패 > 관측 불가능한 실패
```

---

## 13. 비용 지표

ARAG의 비용은 성공 비용보다 **정보 비용**으로 봐야 한다.

기존 비용 지표:

```text
cost_per_hour
cost_per_run
monthly_cost
```

추가해야 할 비용 지표:

```text
cost_per_useful_artifact
cost_per_converged_fix
cost_per_new_failure_class
cost_per_level_boundary_found
```

특히 중요한 지표는 다음이다.

```text
cost_per_level_boundary_found
```

ARAG의 목적은 단순히 앱을 만드는 것이 아니라, 모델-루프 조합이 어디서 무너지는지 찾는 것이기 때문이다.

---

## 14. DB 구조 초안

처음에는 복잡한 시스템보다 SQLite 하나로 충분하다.

### tasks 테이블

```sql
CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  source_model TEXT NOT NULL,
  title TEXT NOT NULL,
  goal TEXT NOT NULL,
  difficulty_level INTEGER NOT NULL,
  task_json TEXT NOT NULL,
  design_quality_score REAL,
  created_at TEXT NOT NULL,
  schema_version TEXT NOT NULL
);
```

### task_tags 테이블

```sql
CREATE TABLE task_tags (
  task_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (task_id, tag)
);
```

### expected_failure_modes 테이블

```sql
CREATE TABLE expected_failure_modes (
  task_id TEXT NOT NULL,
  failure_mode TEXT NOT NULL,
  PRIMARY KEY (task_id, failure_mode)
);
```

### task_reviews 테이블

```sql
CREATE TABLE task_reviews (
  review_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  reviewer_model TEXT NOT NULL,
  review_json TEXT NOT NULL,
  revised_difficulty_level INTEGER,
  design_quality_score REAL,
  created_at TEXT NOT NULL
);
```

### run_results 테이블

```sql
CREATE TABLE run_results (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  model_profile TEXT NOT NULL,
  success INTEGER NOT NULL,
  artifact_score INTEGER,
  limit_type TEXT,
  failure_class TEXT,
  cost_usd REAL,
  report_path TEXT,
  events_path TEXT,
  created_at TEXT NOT NULL
);
```

---

## 15. 대시보드 방향

대시보드는 진행 상황 표시기가 아니라 **실험 관측판**이어야 한다.

기존 대시보드가 보여주는 것:

```text
성공률
호출 수
비용
최근 실행 상태
```

앞으로 추가해야 할 것:

```text
태그별 성공률
태그별 artifact_score 평균
태그별 repeat_error_rate
limit_type 분포
failure_class 분포
JUNK_FAILURE 비율
cost_per_useful_artifact
cost_per_level_boundary_found
모델별 붕괴 태그 조합
```

중요한 대시보드 질문:

```text
이 모델은 어떤 태그 조합에서 무너지는가?
실패했을 때 유용한 관측 데이터를 남기는가?
돈을 쓴 만큼 새로운 실패 클래스나 한계선을 발견했는가?
```

---

## 16. 실행 계획

### Phase 1: 스키마 고정

목표:

```text
task_card schema v1 확정
difficulty_tags 고정
expected_failure_modes 고정
limit_type 4분류 확정
artifact_score 기준 확정
```

작업:

```text
31B로 50~100개 생성
사람이 일부 검토
schema 수정
태그 목록 수정
```

### Phase 2: 31B 기준선 생성

목표:

```text
31B 설계 카드 300~500개
```

작업:

```text
태그별 최소 수량 확인
난이도별 분포 확인
중복 제거
품질 낮은 카드 제거
```

### Phase 3: Gemini 3.5 Flash 대량 확장

목표:

```text
Gemini 3.5 Flash 설계 카드 1,000~2,000개
```

작업:

```text
부족한 태그 조합 우선 생성
level 1~5 균형 조정
중복 제거
자동 schema validation
```

### Phase 4: Gemini 3.1 Pro 검수 및 고난도 생성

목표:

```text
Gemini 3.1 Pro 신규 카드 200~300개
Gemini 3.1 Pro 검수 카드 300~500개
```

작업:

```text
난이도 재판정
태그 보정
품질 점수 부여
고난도 level 4~5 카드 생성
애매한 카드 수정 또는 폐기
```

### Phase 5: 실행 루프 연결

목표:

```text
task_db에서 task_id를 선택해 ARAG 실행 루프에 투입
```

작업:

```text
task_id를 REPORT/events/design과 연결
실행 결과를 run_results에 저장
태그별 결과 분석
모델별 붕괴 지점 관측
```

### Phase 6: 관측판 대시보드

목표:

```text
대시보드를 성공률판에서 실험 관측판으로 변경
```

작업:

```text
artifact_score 표시
limit_type 분포 표시
failure_class 분포 표시
태그별 성능 표시
cost_per_useful_artifact 표시
```

---

## 17. 위험 요소

### 17.1 설계 DB가 쓰레기통이 되는 문제

과제를 많이 만드는 것보다 품질 관리가 중요하다.

대응:

```text
schema validation
중복 제거
design_quality_score
3.1 Pro 검수
사람이 초기 샘플 검토
```

### 17.2 모델 편향 문제

31B가 만든 과제를 26B/31B가 풀면 같은 계열 모델에 유리한 편향이 생길 수 있다.

대응:

```text
31B, 3.5 Flash, 3.1 Pro 출처를 분리 저장
source_model별 결과 비교
외부 과제 seed 일부 추가
```

### 17.3 태그 혼란 문제

모델이 자유롭게 태그를 만들면 DB가 망가진다.

대응:

```text
고정 태그 목록 사용
허용되지 않은 태그는 validation 실패
동의어 금지
tag normalization 적용
```

### 17.4 난이도 숫자 과신 문제

level 2라고 다 같은 level 2가 아니다.

대응:

```text
difficulty_level + difficulty_tags 조합으로 해석
태그별 붕괴 지점 분석
3.1 Pro로 일부 난이도 재판정
```

---

## 18. 최종 정의

ARAG는 자동 코딩기가 아니다.

ARAG는 저가 모델이 장기 반복 루프 안에서 어디까지 유용한 관측 데이터를 남기며 버티는지 측정하는 **루프 엔지니어링 실험 장치**다.

Design Bank는 이 실험 장치에 통제된 과제 재료를 공급하는 하위 시스템이다.

Design Bank의 목적은 다음이다.

```text
1. 실험 가능한 과제를 구조화한다.
2. 난이도와 태그를 통제한다.
3. 실행 루프의 실패를 해석 가능하게 만든다.
4. 모델별·태그별 한계선을 찾는다.
5. 다음 루프 엔진 후보를 데이터로 선택하게 만든다.
```

최종 목표는 좋은 결과물을 한 번에 만드는 것이 아니라, **모델과 루프의 한계를 관측 가능한 데이터로 축적하는 것**이다.
