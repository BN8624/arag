# Progress: 생성기 1차 스프린트 완료 + 2차 스프린트(1·2단계) 완료 + D-2 목표 달성

## 현황 요약 (2026-06-11 갱신)
- **상태**: 2차 스프린트 D-2(외부 API 앱 지원) 목표 달성. 테스트 75개+ 통과
- **D-2 검증 완료**: pypdf + openpyxl + mock 모드가 한 런에서 동작 확인
  → "PDF 청구서 텍스트 추출 → AI API(mock) → xlsx 저장" 아이디어로 OK 달성
- **오늘 추가 수정**:
  - 토큰 카운트 구현 (REPORT.md에 input/output/thinking 표시)
  - 만점 빌드 비평 스킵 (3/3 PASS 시 critique 단계 자체 생략)
  - 31B 테스트 버그 수정 (존재하지 않는 파일 경로 → pytest.raises 또는 tmp_path 강제)
  - click 테스트 버그 수정 (main() 직접 호출 → CliRunner 강제)
  - prompts.py 화이트리스트 동기화 (gates.py에는 있었으나 HARD_RULES에 빠진 openpyxl·pypdf·Pillow 추가)
  - gemma-4-26b 복구 확인 후 .env 원복

## 남은 버그
- **4번째 기준 오판정**: API 키 없을 때 exit 1이 정답인 기준을 검증이 FAIL로 봄.
  `criteria_checks`에 `expect_exit_code` 필드 추가 또는 설계 규칙 수정 필요.

## 바로 다음 작업

1. **4번째 기준 버그 수정** — criteria_checks에 "오류 종료가 정답인 기준" 지원
2. **`--resume <run_dir>` 기능** — 이전 실패 런의 design.json + test_acceptance.py 재사용,
   구현 단계부터 재시작 (비용 절감 + 빠른 재도전)

---

## 구현 완료된 신기능

### 1. 수용기준 채점표 (Acceptance Criteria Scoreboard)
**해결한 문제**: 비평가가 추측으로 리뷰하던 문제 → 증거 기반 리뷰로 전환

**구현 내용**
- `docker_gate.py::run_criteria_checks()`: 설계 단계에서 정의한 각 수용기준마다 CLI 커맨드 실행
- 각 기준별 PASS/FAIL 채점표 생성
- 채점표를 비평가 입력에 포함시켜 "이 기준이 정말 깨졌는가"를 실행 증거로 판단 가능

### 2. 오답노트 (Failure Lessons)
**해결한 문제**: 초기 설계 실수가 반복되던 문제 → 실패→개선→재도전 사이클

**구현 내용**
- `lessons.py`: 실패 이력 기록 → 31B에게 의뢰 → keyword 추출
- `orchestrator.py::_load_lessons()`: 저장된 lessons 로드
- `prompts.py::design_prompt()`: 유사 주제 과거 실패 교훈을 설계 단계에 주입

### 3. 자동 재시도 (Auto-Retry with Lessons)
**해결한 문제**: 막힌 전체 프로젝트를 버리고 다시 시작해야 하던 문제

**구현 내용**
- `orchestrator.py::main()`: 1차 실패 시 lessons 수집 + 자동 재도전
- 재도전 시 3개 lessons 주입 → 새 설계 → 새 구현 → 게이트 재통과

### 4. 외부패키지 화이트리스트 + && 체인 커맨드
- `gates.py::ALLOWED_PACKAGES`: requests, rich, click, tabulate, yaml, dateutil,
  tqdm, colorama, jinja2, markdown, openpyxl, pypdf, Pillow
- `docker_gate.py::install_packages()`: pip install 통합
- `design_validator.py`: && 체인 각 단계 python 시작 검증

### 5. 외부 API 모킹 검증 패턴 (D-2)
- 31B가 설계 때 가짜 API 응답(fixture) 출제
- 게이트는 mock 모드로 전체 파이프라인 자동 검증 (네트워크 차단 유지)
- 정적 게이트에 API 키 하드코딩 탐지 추가

### 6. 만점 비평 스킵
- `orchestrator.py::_phase_critique_loop()`: 채점표 전항목 PASS 시 critique 단계 생략
- 비평 바퀴를 돌려 통과 빌드를 깎는 낭비 방지

### 7. 토큰 카운트
- `llm.py`: `usage_metadata` 파싱, `self.tokens` 누적
- `orchestrator.py::_write_report()`: REPORT.md에 input/output/thinking 토큰 요약

### 8. 테스트 품질 규칙 강화 (prompts.py)
- 존재하지 않는 파일 경로 → pytest.raises 또는 tmp_path 강제
- click 사용 시 CliRunner 강제 (main() 직접 호출 금지)

---

## 검증 현황

### 유닛 테스트
- **75개+ 통과** (test_gates, test_new_features, test_stage1_features, test_stage2_mocking, test_orchestrator_mock, test_schema, test_design_validator)

### 엔드투엔드 검증
| 주제 | 결과 | 채점표 | 특이사항 |
|------|------|--------|---------|
| 온도 변환 CLI | ✅ | - | 초기 검증 |
| 계산식 파서 | ✅ | - | 초기 검증 |
| 가계부 CLI | ✅ | - | 초기 검증 |
| 마크다운 표 생성기 | ✅ (4차) | 4/4 | 3회 실패 후 lessons 주입으로 성공 |
| 환율 변환 CLI | ✅ (salvage) | 3/3 | 핑퐁 감지 + salvage |
| **pypdf+openpyxl+mock (D-2)** | **✅** | **3/4** | pytest 7/7, LGTM 1라운드 조기 종료 |

**D-2 런 상세** (runs/20260611-174511-retry)
- API calls: 18 / Tokens: input 51K / output 12K / thinking 63K
- extractor.py → pypdf 사용 ✅
- exporter.py → openpyxl 사용 ✅
- 4번째 기준만 FAIL (exit 1 오판정 버그 — 코드는 맞음)

---

## 향후 로드맵 (우선순위 순)

### 즉시
1. **4번째 기준 오판정 버그** — criteria_checks `expect_exit_code` 지원
2. **`--resume <run_dir>`** — 실패 런 재사용 (설계+테스트 건너뛰기)

### A. 프로덕션급 격상 (결과물 퀄리티)
- README 자동 생성 ✅ (이미 구현됨)
- 패키징 (pyproject.toml) — API 0콜, 기계적 생성

### B. 산출물 형태 확장
1. 라이브러리 (낮음)
2. 웹 API 서버 (중간)
3. GUI tkinter (중간) — 바이브코더에게 체감 가치 최대

### C. 토큰카운트 ✅ (완료)

### D-2. 외부 API 앱 지원 ✅ (완료)

### E. 보류
- Discord 봇 상태 전송
- 밤샘 배치 모드 (아이디어 큐 순차 실행)

---

## 기록

- **1차 완료**: 2026-06-11
- **2차 D-2 완료**: 2026-06-11
- **테스트 coverage**: 75개+ ✓
- **총 API 콜 (오늘)**: ~130 (sop 검증 런 포함)
- **주요 교훈**:
  - prompts.py HARD_RULES와 gates.py 화이트리스트는 항상 동기화
  - click 테스트는 CliRunner로만 (standalone_mode=False → None 반환 함정)
  - 26B thinking 토큰이 31B보다 훨씬 많음 (추론 비중 높은 구조)
  - gemma-4-26b 500 오류 시 gemini-3.1-flash-lite로 임시 대체 가능
