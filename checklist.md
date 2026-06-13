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

## 2. 카드 6개 정의 (bank 스키마 재사용) ✅
- [x] 깨끗한 `design_bank.sqlite`에 게임/앱 카드 6장 (worktree `bank_cards_p2.py`, T-1~6)
- [x] difficulty_level L1/2/2/2/2/3, 비대화형(stdin 금지)으로 전부 설계
- [x] 5·6번(강화·전투) + 3번(리그): --seed 결정성 요구를 카드에 명시
- [x] (추가) llm.py 콜당 토큰·finish_reason 계측 — PLAN §8.2 (분산성 잘림 관측)

## 3. run metadata 필드 추가 ✅
- [x] index에 mode/notes_enabled 기록 (reporting._record_index)
- [x] 나머지 PLAN §4 필드는 plan2.build_record로 파생(정본 비저장, derived view)
- [x] protocol_fingerprint 객체 (plan2.protocol_fingerprint, 해시 X)
- [x] 테스트 (test_plan2)
- 보류: model_design/impl, elapsed_sec는 derived/렌더에서 보강(elapsed는 events로 추정)

## 4. 결과 라벨 5개 적용 ✅
- [x] limit_type → 5라벨 매핑 (plan2.run_label, 콜0)
- [x] 테스트: 각 라벨 케이스 (test_plan2)

## 5. 점수 2종 기록 (_auto/_user 2단계) ✅
- [x] prototype_score_auto / failure_usefulness_auto (plan2)
- [x] *_user = null + human_audit_status="pending" (build_record)
- [x] cost_usd 재사용

## 5.5 warm 노트 품질 필터 (USE/HOLD/DROP) ✅
- [x] 자동 분류 plan2_notes.classify_note (콜0 휴리스틱)
- [x] partition으로 USE만 추출 (warm 적재는 7단계 실행 시)
- [x] render_note_audit로 폰에서 변경 가능

## 6. 폰 감사 요약 생성 ✅
- [x] 런별 산문 1화면 plan2_audit.render_audit + 사람 체크 3개
- [x] 노트 후보 감사 plan2_notes.render_note_audit
- [x] ASCII/cp949 안전 (유니코드 기호 미사용)

## 7. 12런 실행 (worktree ../arag-bank)
- [ ] cold 6런 + 노트 후보 수확
- [ ] 수확분 warm 저장소 적재
- [ ] warm 6런
- [ ] 안정 시간대 실행(26B 새벽 500 회피), INFRA는 분모 제외·재시도

## 8. 결과 보고 + 포맷 수정
- [ ] 12런 요약을 폰으로 전달 → 사람 감사
- [ ] 카드/라벨/요약 포맷 피드백 반영
- [ ] HANDOFF 갱신, 캠페인2 범위 결정
