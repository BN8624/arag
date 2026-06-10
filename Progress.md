# Progress: 생성기 1차 스프린트 완료

## 현황 요약
- **상태**: 1차 핵심 기능 완성 (4개 신기능 통합)
- **검증**: 테스트 50/50 통과, 마크다운 표 제너레이터 4연속 성공 (API 4콜)
- **다음 단계**: 향후 고려사항 로드맵 (Discord 봇 연동, 토큰카운트)

---

## 구현 완료된 신기능

### 1. 수용기준 채점표 (Acceptance Criteria Scoreboard)
**해결한 문제**: 비평가가 추측으로 리뷰하던 문제 → 증거 기반 리뷰로 전환

**구현 내용**
- `docker_gate.py::run_criteria_checks()`: 설계 단계에서 정의한 각 수용기준마다 CLI 커맨드 실행
- 각 기준별 PASS/FAIL 채점표 생성 (예: `[PASS] CSV→마크다운 변환 가능 / [FAIL] 합계 행 미생성`)
- 채점표를 비평가 입력에 포함시켜 "이 기준이 정말 깨졌는가"를 실행 증거로 판단 가능

**검증**: 마크다운 표 제너레이터에서 4/4 수용기준 통과 확인

---

### 2. 오답노트 (Failure Lessons)
**해결한 문제**: 초기 설계 실수가 반복되던 문제 → 실패→개선→재도전 사이클

**구현 내용**
- `lessons.py`: 실패 이력 기록 (idea, 실패 원인) → 31B에게 의뢰 → keyword 추출
- `orchestrator.py::_load_lessons()`: 저장된 lessons 로드
- `prompts.py::design_prompt()`: 유사 주제의 과거 실패 교훈을 설계 단계에 주입
- 마크다운 표 예: 3회 실패 → "CLI 인자 매핑 규칙 명시" 교훈 추출 → 4차 설계에 주입 → 성공

**검증**: 마크다운 표에서 lessons.json 2건 주입으로 4차 시도 성공

---

### 3. 자동 재시도 (Auto-Retry with Lessons)
**해결한 문제**: 막힌 전체 프로젝트를 버리고 다시 시작해야 던 문제

**구현 내용**
- `orchestrator.py::main()`: 1차 실패 시 lessons 수집 + `--no-retry` 미설정이면 자동 재도전
- 재도전 시: 3개 lessons 주입 → 새 설계 → 새 구현 → 게이트 재통과
- 실패 기록(`events.jsonl`, `lessons.json`) 저장으로 히스토리 추적 가능

**검증**: 계산식 파서, 가계부 모두 1회 완주. 마크다운 표은 3회 실패 후 lesson 기반 4차 성공

---

### 4. 외부패키지 화이트리스트 + && 체인 커맨드
**해결한 문제**: 표준 라이브러리만으로 제약된 도구 폭 → 10종 화이트리스트로 완화 + 멀티스텝 지원

**구현 내용**
- `gates.py::ALLOWED_PACKAGES`: requests, rich, click, tabulate, yaml, dateutil, tqdm, colorama, jinja2, markdown
- `gates.py::external_imports()`: 워크스페이스에서 실제 사용한 외부패키지만 추출 (선언 아님)
- `docker_gate.py::install_packages()`: pip install 한 번에 통합 + 마커 파일로 재설치 방지
- `design_validator.py::_non_python_parts()`: "&&" 체인의 각 단계가 python으로 시작하는지 검증
- `docker_gate.py::_as_argv()`: && 체인을 sh -c로 변환 → 실행 단계에서 처리
- `prompts.py::HARD_RULES`: 화이트리스트 10종 명시 + "각 && 단계는 python으로 시작" 규칙 추가

**검증**: 마크다운 표에서 `python main.py create-sample test.csv && python main.py convert test.csv --sum-cols "1" --align "L,R"` 성공 (click 활용)

---

## 검증 현황

### 유닛 테스트 (test_gates.py, test_new_features.py)
- **총 50개 테스트 통과**
  - 화이트리스트 검증: 4개
  - 수용기준 커맨드 검증: 3개
  - 오답노트 기능: 5개
  - && 체인 명령: 2개
  - 외부패키지 매핑(pip name ↔ import name): 2개
  - 기타: 34개

### 엔드투엔드 검증
| 주제 | 시도 | API 콜 | 결과 |
|------|------|--------|------|
| 온도 변환 CLI | 1회 | 4 | ✓ 통과 |
| 계산식 파서 | 1회 | 4 | ✓ 통과 |
| 가계부 CLI | 1회 | 4 | ✓ 통과 |
| 마크다운 표 생성기 | 4회 | 4+12+12+4=32 | ✗✗✗ 후 ✓ |

**최종 성공 사례** (마크다운 표, 4차 시도)
```
[START] C:\Users\USER\arag\runs\20260611-000243
[NOTE] 3 lessons injected from past failures
[PHASE] design (31B) → [OK] accepted
[PHASE] implement (26B) → [OK] converter.py, main.py
[GATE] static + exec → [OK] passed
[SCORE] 4/4 acceptance checks passed
[PHASE] critique (31B) → [OK] LGTM (early exit)
[OK] completed
[INFO] API calls: 4
```

---

## 파일 변경 사항

| 파일 | 변경 내용 |
|------|---------|
| `gates.py` | ALLOWED_PACKAGES dict 추가, external_imports() 함수 강화 |
| `docker_gate.py` | install_packages(), run_criteria_checks(), _as_argv() 추가 |
| `design_validator.py` | _non_python_parts() 추가 (&&체인 검증) |
| `lessons.py` | 전체 신규: load_lessons(), find_relevant(), record_lesson() |
| `orchestrator.py` | _load_lessons(), _ensure_packages(), _run_scoreboard(), _record_failure() 추가 |
| `prompts.py` | HARD_RULES 업데이트, design_prompt()에 lessons 주입, criteria_checks 스키마, critique_prompt()에 scoreboard 추가 |
| `test_gates.py` | external_imports 테스트 추가 (requests whitelist, numpy rejection) |
| `test_new_features.py` | 전체 신규: 16개 테스트 (whitelist, criteria_checks, lessons) |

---

## 향후 고려사항

### 1. Discord 봇 상태 전송 + status.json
**목표**: 사용자가 폰에서 생성 진행 상황을 real-time으로 모니터링

**구현 계획**
- `status.json`: 현재 run 디렉토리, phase (design/implement/gate/critique), progress, API 콜 수
- Discord webhook or bot: 단계 완료마다 메시지 전송 (emoji + 진행률)
- Polling interval: 5초 (로컬 파일 시스템이므로 지연 무시 가능)

**제약**: 기존 개인툴(웹 관제)보다 간단한 구현이지만, 사용자가 Windows PC 안 되면 휴대폰에서만 폰 볼 수 있음

### 2. 토큰카운트 기능
**목표**: 모델별(31B/26B), 단계별(design/implement/critique) 토큰 사용량 추적

**구현 계획**
- Gemma 4 API response에 usage 필드 파싱
- `tokens_used.json`: {model, phase, input_tokens, output_tokens, thinking_tokens(31B만)}
- Report.md에 "API cost summary" 섹션 추가
- 쿼터 모니터링: RPM 15, TPM ∞ → 장기 실행 시 사용 패턴 분석

**추적 대상**
- 자가수정 횟수별 토큰 증가량 (K=3 제한이 충분한지 검증)
- 비평-개선 바퀴 2~3회의 누적 토큰 (LGTM 조기 종료 효과)
- 오답노트 주입이 토큰 절감에 기여하는 정도

---

## 다음 마일스톤

1. **즉시** (선택)
   - Discord 봇 통합 (webhook 또는 discord.py)
   - tokens_used.json 추적 + Report.md에 포함

2. **2차 스프린트** (향후)
   - 2-3문장 아이디어 처리 (현재는 한 줄 고정)
   - 비표준 라이브러리 프로젝트 지원 (go, js, 등)
   - 사용자 피드백 루프: CLI 인터페이스 (generate --idea "..." --max-cost 50)

---

## 기록

- **1차 완료**: 2026-06-11
- **테스트 coverage**: 50/50 ✓
- **마크다운 표 검증**: 3회 실패 → 오답노트 교훈 주입 → 4차 성공
- **총 API 콜**: ~60 (온도변환 4 + 계산식 4 + 가계부 4 + 마크다운 32)
- **주요 교훈**: 
  - 멀티스텝 도구는 success_signal이 && 체인을 지원해야 함
  - 실패→lesson→재도전 사이클이 설계 개선에 효과적
  - 화이트리스트로 도구 폭을 적절히 완화해야 유용성 vs 관리 비용 균형
