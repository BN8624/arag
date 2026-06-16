# checklist.md — trace-diff 오라클 (첫-발산 국소화 피드백)

> 결정 로그 = [context-notes.md](context-notes.md) 결정27. 큰 방향 = [PLAN.md](PLAN.md).
> 한 단계씩, 끝나면 멈추고 보고. 측정 정합성 = 게이트 불변(최종 골든), 트레이스는 피드백 전용.

## 배경 (왜 이걸 하나 — 결정27 요약)
- 5사이클 cold/warm(110런) 결과: 노트효과 0(cold 13/55 vs warm 8/55, z≈1.2 비유의), 하네스 무결
  (INFRA 0·HARNESS 0). 원인 = **(B) 모델 실행정밀도 한계** — 실패 89건 중 86건이 "도는 코드인데
  시뮬 궤적이 1턴부터 발산"(turns 23↔13 등, 값이 넓게 흩어짐 = 각 런 서로 다른 작은 통합실수).
- 스펙·골든·레퍼런스 정합 검증 끝(seed파티=고정파티, combat 랜덤0, 노트=스펙일치). 명세미결정 기각.
- **레버**: 골든 피드백이 최종상태(turns 23↔13)만 줘 *어느 규칙이 몇 턴째* 깨졌는지 못 짚음 →
  자가수정·노트가 못 묾. `game/`엔 이미 `--trace`(이벤트 JSON)가 있다. 첫-발산 국소화 힌트를
  자가수정에 주입 = all-or-nothing을 단일스텝 수정신호로 변환. **유일한 미시도 개입.**
- 힌트 강도(사용자 결정) = **위치+범주**: '턴 N에서 발산, 네 행동=X, 어느 규칙 범주 의심'.
  골든 숫자는 비노출(공정성 유지, 답 떠먹이기 아님).

## 설계 (5조각)
- [x] **1. game/ 턴 트레이스 + 골든 생성**: combat에 턴별 정규 스냅샷(`turn=N actor=ID action=X
      | id=hp ...`) 한 줄/턴(`_turn_line`, run_battle가 turn_trace 반환). main.py `--turntrace`(JSON
      --trace와 공존). 4 골든 → `frozen/T-000012-trace/golden_traces/scenN.txt`(결정론·turns 23/17/19/29).
- [x] **2. 카드 변이**: DB 안 건드림(실험=하네스 변이). idea = T-000012 goal + `trace_run.TRACE_SPEC`
      (--trace 요구 문단, combat 포맷 일치). frozen/T-000012-trace = design.json+test_acceptance.py
      (T-000012 복사) + golden_traces. **베이스라인 frozen/T-000012 보존.**
- [x] **3. trace_diff.py (콜0)**: parse_trace/first_divergence/hint_text. 발산종류(actor/action/freeze/
      state/length/missing) + 규칙범주 추론. **골든 정답값 비노출**(테스트로 보장). 파싱실패 graceful.
- [x] **4. 자가수정 배선**: `phase_gates._add_trace_hint` — 골든 불일치 시 `run_turn_trace`로 모델
      --trace 실행 → trace_diff → 힌트 issue 추가. golden_traces 있을 때만. **게이트 불변**. 트레이스
      못 뽑으면(다른 시나리오 일치/디렉토리 없음/크래시) 조용히 기존 issue 유지.
- [~] **5. 캠페인 러너**: `trace_run.py` 작성 완료(trace_on/trace_off 2-arm, cold, KeyPool 병렬).
      **런 미기동** — ⚠️ 사용자 명시 지시 전엔 금지(memory no-autostart-runs).

## 검증 (단계마다)
- [x] 1 끝: 4 골든 트레이스 결정론 재현·turns 일치·최종상태 골든 일치. game test 14/14.
- [x] 3 끝: trace_diff 단위테스트(동일→None, actor/action/freeze/state/length/missing, 골든값 비노출) 15개.
- [x] 4 끝: mock으로 힌트주입·비골든실패 스킵·트레이스일치 no-op·디렉토리없음 no-op 테스트.
- [x] 전체 테스트 **351 통과**(334+신규, 회귀 0).

## 주의 / 함정
- **트레이스는 절대 게이트가 아니다.** 게이트 통과 판정은 최종 골든 토큰 그대로. 트레이스 오작동이
  PASS/FAIL을 바꾸면 안 됨(측정 오염). 피드백 품질만 바꾼다.
- 힌트에 골든 숫자(정답 HP/턴값) 넣지 말 것 — 위치+범주까지만(사용자 결정).
- 모델 트레이스 포맷이 틀려도 게이트엔 무영향(폴백). 트레이스 포맷 실패를 새 FAIL모드로 만들지 말 것.
- T-000012-trace는 베이스라인과 *다른 카드*다. 비교는 "trace arm vs 24% cold"로 명시(같은 카드 아님).

---

# 리뷰 #1~#6 하네스 강화 (별도 트랙, #7·#8 보류) — 완료
> 외부 코드리뷰 반영. 측정 신뢰도/계약 정합 보강. 각 항목 테스트 동반, 전체 회귀 0.
- [x] **#1 Docker 워크스페이스 격리**: `_run_in_docker`가 원본 대신 *임시 복사본*(원본 부모에
      생성→실행 후 폐기, .git·__pycache__ 제외)을 마운트. 생성코드가 success_signal 중
      test_acceptance.py/소스 못 건드림. 게이트 의미 불변. 테스트=원본 불변·복사본 폐기 증명.
- [x] **#2 pass rate**: `_pytest_pass_rate`가 error를 분모에 포함(`8 passed,1 failed,1 error`→8/10).
- [x] **#3 클래스 메서드 시그니처**: `_check_contracts`가 메서드도 arg수 대조(self/cls 양쪽 strip).
- [x] **#4 노트 로더 침묵**: `_load_notes` except가 `critique-notes-load-error` 이벤트+say 남김.
- [x] **#5 약한 오라클 라벨**: `_oracle_strength()`(헬퍼) → index `oracle_strength` strong/weak.
- [x] **#6 success_signal/criteria_checks 검증**: `_inline_code_parts`로 `python -c` 금지.
- [x] 전체 테스트 **364 통과**(351+13, 회귀 0).
