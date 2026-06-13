# Design Bank 병행 개발 계획 (구현 계획서)

> 설계 문서: `ARAG_DESIGN_BANK_PLAN.md` (무엇을) / 이 문서: 어떻게·어떤 순서로.
> 원칙 문서: `ARAG_LOOP_OBSERVABILITY_PRINCIPLES.md`

## 0. 병행 개발 원칙 (격리 규칙)

ARAG 본체는 그동안 계속 실험을 돈다. Design Bank가 본체를 건드리는 지점을
계약으로 못 박는다:

1. **코드 격리**: Design Bank는 `bank_*.py` 모듈군 + `design_bank.sqlite` 한 파일.
   orchestrator/batch/gates/prompts는 **수정 금지** (아래 접점 2곳 제외)
2. **접점은 딱 2곳**, 둘 다 마지막 단계(B2)에서:
   - orchestrator에 `--task-id` 인자 추가 → index 항목에 `task_id` 기록 (3줄)
   - batch의 아이디어 출처로 "bank에서 뽑기" 옵션 추가 (idea_factory 대체가 아니라 병렬 옵션)
3. **실험 비오염**: Design Bank 개발·생성 작업은 실행 루프 프롬프트를 안 바꾸므로
   prompt_versions 실험과 독립. 단 31B 카드 생성은 critic RPD를 쓰므로
   **배치가 쉬는 시간에 돌린다** (RPD 1,500 중 배치 소비 ~200/일이라 여유 큼)
4. **모델 격리**: Gemini 클라이언트는 `bank_llm.py`에 한정. 본체 llm.py 수정 금지
   (CLAUDE.md 2차 방향과 일치)
5. 모든 모듈은 콜 0 테스트 가능 (mock 설계자 주입)

## 1. 모듈 구성 (flat .py 컨벤션 유지)

```
bank_schema.py    task_card v1 정의 + validation
                  - 고정 태그 12종·실패모드 13종·level 1~5 (설계 문서 6~9장 그대로)
                  - 허용 외 태그 = 검증 실패 (동의어 금지)
bank_db.py        SQLite CRUD (tasks/task_tags/expected_failure_modes/
                  task_reviews/run_results — 설계 문서 14장 스키마)
                  - run_results는 정본이 아니라 index.json에서 파생 (정본 충돌 방지)
                  - 중복 감지: goal 정규화 해시 + 제목 유사도
bank_generate.py  설계자 호출 + 분포 밸런서
                  - 입력: 태그×레벨 목표 분포 → 부족 조합 우선 생성
                  - 출제 프롬프트: 스키마 JSON 강제 + 고정 어휘 목록 제시
                  - 파싱 실패 1회 재요청 (프로젝트 공통 규칙)
bank_llm.py       provider 분리: gemma(기존 LLMClient 재사용) / gemini(B3에서 추가)
bank_report.py    분포 현황 리포트 (태그×레벨 매트릭스 채움 상태, 콜 0)
                  + 대시보드 지표 탭에 카드 수/분포 섹션 (B2 이후)
```

## 2. 단계별 계획 (완료 기준 명시)

### B0. 스키마 + DB (콜 0) — 첫 작업
- bank_schema + bank_db + 테스트
- **완료 기준**: 설계 문서의 예시 task_card가 통과하고, 허용 외 태그·중복·
  스키마 누락이 전부 거부되는 테스트 통과
- 사람 결정 불필요. 배치 돌아가는 중에도 안전

### B1. 31B 파일럿 50장 (콜 ~60, 무료)
- bank_generate로 31B 카드 50장 (태그 12종 × level 1~3 위주 분포)
- **사람 검토**: 샘플 10장을 보기 좋게 렌더해서 폰으로 확인 → 태그/스키마 수정
- **완료 기준**: schema validation 통과율 ≥90% + 사용자가 샘플 10장 OK
- 목적: 대량 생산 전에 **스키마를 현실에 맞게 고정** (설계 문서 Phase 1)

### B2. 실행 검증 — 접점 연결 (추가 콜 0, 기존 배치 예산)
- 접점 2곳 연결 (--task-id 기록 + 배치의 bank 출처 옵션)
- 50장 중 20~30장을 일반 배치로 완주 → **태그별 성공률·artifact_score 첫 조인**
  (observability와 결합 — 여기서 "태그별 붕괴 지점" 첫 데이터)
- **완료 기준**: task_id가 index→bank로 왕복 조회되고, 태그별 결과 리포트가 나옴
- 이게 끝나야 스키마 v1 확정 → 대량 생산 자격

### B3. Gemini 접속 + 대량 생산 (크레딧 사용 시작)
- bank_llm에 gemini provider (.env에 GEMINI_API_KEY 별도)
- 3.5 Flash로 1,000~2,000장: 부족 태그 조합 우선, 자동 validation, 중복 제거
- **비용 추정**: 카드당 입력 ~1.5K + 출력 ~1K 토큰 → 2,000장 ≈ 5M 토큰
  ≈ Flash 단가 기준 수천 원 수준 (크레딧 30만 원의 ~1-2%)
- **완료 기준**: 태그×레벨 매트릭스에 빈 칸 없음 + validation 통과율 리포트

### B4. 3.1 Pro 검수 (크레딧)
- 신규 고난도(level 4~5) 200~300장 + 기존 카드 검수 300~500장
  (난이도 재판정, design_quality_score)
- source_model별 분리 저장 → 편향 비교 가능 (설계 문서 17.2)

### B5. 관측판 확장
- 지표 탭: 태그별 성공률 / 태그별 artifact_score / 모델별 붕괴 태그 조합
- cost_per_level_boundary_found는 "한계선 발견" 판정 기준을 B2 데이터 보고 정의

## 3. 사용자 결정이 필요한 것 (각 단계 진입 전)

- **B1 종료 시**: 샘플 10장 검토 (폰에서, 5분)
- **B3 진입 전**: Gemini API 키 발급·크레딧 연결 확인 + 1차 생산량 (1,000 vs 2,000)
- 그 외에는 자동 진행 가능

## 4. 일정 감각

- B0: 한 세션 (지금 가능, 배치와 무관)
- B1: 한 세션 + 31B 콜 1시간 (배치 쉬는 시간)
- B2: 배치 1~2회 (기존 측정 배치에 끼워서)
- B3~B5: B2 결과 보고

## 5. 위험과 대응 (설계 문서 17장의 구현 버전)

- 쓰레기통화 → B1·B2에서 소량-검증-수정을 강제 (대량 생산은 B3 전까지 금지)
- 모델 편향 → source_model 분리 저장은 B0 스키마부터 포함
- 태그 혼란 → validation이 고정 어휘 외 전부 거부 (B0부터)
- index.json/SQLite 정본 충돌 → run_results는 파생 뷰로만 (B0 결정 사항)
