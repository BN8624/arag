# checklist.md — PLAN 2 셰이크다운 (12런)

> 명세 = [PLAN.md](PLAN.md), 결정 로그 = [context-notes.md](context-notes.md).
> 끝나면 체크. 한 단계씩, 끝나면 멈추고 보고.

## 0. 선결 결정 (착수 전)
- [x] warm 순서 확정 = cold→수확→정리(USE/HOLD/DROP)→warm 적재→warm 재시도 (PLAN §1)
- [x] 셰이크다운 = 효과 정식측정 아님, 파이프라인 검증 (PLAN §1 ⚠️ 명시)
- [ ] temperature 고정값 확정 (추천 0.2, 변동 최소화)
- [ ] AI Studio gemma가 temperature/seed를 받는지 코드로 확인 (못 받으면 seed=null)

## 1. cold/warm mode 분리 (최우선 코딩) ✅
- [x] orchestrator에 `notes_enabled`(기본 True) + CLI `--mode cold|warm`
- [x] `phase_design._load_lessons`: cold면 즉시 `[]` 반환 (+ notes-disabled 로그)
- [x] `phase_implement._load_notes`: cold면 즉시 `[]` 반환
- [x] 테스트: cold 런에 lessons/critique 주입 0건 단언 (콜 0 mock) — 268 통과
- [x] 검증: warm 런은 기존대로 주입됨 (회귀 없음)

## 2. 카드 6개 정의 (bank 스키마 재사용)
- [ ] 깨끗한 `design_bank.sqlite`에 게임/앱 카드 6장 (PLAN §2 표)
- [ ] card_id 규칙 L1/L2/L3, card_name, card_level 부여
- [ ] 5·6번 카드: 테스트 모드 seed/deterministic 요구를 카드 명세에 명시

## 3. run metadata 필드 추가
- [ ] index 기록에 PLAN §4 필드 추가 (protocol_version, protocol_fingerprint,
      mode, notes_enabled, model_design/impl, final_label, failure_stage,
      repair_rounds, *_auto/_user 점수, human_audit_status, cost_usd, elapsed_sec)
- [ ] protocol_fingerprint 객체 주입(해시 X, 조건 펼쳐 기록)
- [ ] 테스트: 필드 누락 없이 기록되는지

## 4. 결과 라벨 5개 적용
- [ ] observability limit_type → {PASS, PARTIAL_USEFUL, MODEL_FAIL, INFRA_FAIL,
      HARNESS_FAIL} 매핑 함수 (콜 0)
- [ ] 테스트: 각 라벨 케이스 매핑

## 5. 점수 2종 기록 (_auto/_user 2단계)
- [ ] prototype_score_auto / failure_usefulness_auto 기계 산출
- [ ] *_user = null + human_audit_status="pending" 슬롯
- [ ] cost_usd 기존 비용 집계 재사용 확인

## 5.5 warm 노트 품질 필터 (USE/HOLD/DROP)
- [ ] cold 수확 노트를 기계 자동 분류(USE/HOLD/DROP)
- [ ] USE만 warm 저장소 적재
- [ ] 폰 감사에서 분류 변경 가능

## 6. 폰 감사 요약 생성
- [ ] 런별 산문 1화면 요약 생성기 (PLAN §5 형식) + 사람 체크 3개
- [ ] 노트 후보 감사 화면(실패/교훈/판정 + USE/HOLD/DROP 체크)
- [ ] 폰에서 읽기 좋은 출력(ASCII, cp949 안전)

## 7. 12런 실행 (worktree ../arag-bank)
- [ ] cold 6런 + 노트 후보 수확
- [ ] 수확분 warm 저장소 적재
- [ ] warm 6런
- [ ] 안정 시간대 실행(26B 새벽 500 회피), INFRA는 분모 제외·재시도

## 8. 결과 보고 + 포맷 수정
- [ ] 12런 요약을 폰으로 전달 → 사람 감사
- [ ] 카드/라벨/요약 포맷 피드백 반영
- [ ] HANDOFF 갱신, 캠페인2 범위 결정
