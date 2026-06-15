# HANDOFF.md — 진행상황 스냅샷

## ▶ 새 세션 여기부터 (3단계만)
1. **읽기**: 이 파일의 `지금 어디` + `다음 액션` 두 섹션만. 그거면 바로 시작 가능.
2. **지금 할 일 (한 줄)**: 병렬 인프라+RPD트래커+대시보드 그리드 완료, **전31 베이스라인 측정 완료
   (cracked@2/7시도, 429=0)**. 다음 = (선택) **4home 비용 측정** 또는 **warm 캠페인**. 상세 = `다음 액션`.
3. **막히면**: "왜 이렇게 정했나"는 `context-notes.md` 결정번호로, "큰 방향"은 `PLAN.md`.

**문서 용도 (필요할 때만 펼쳐라):**
| 문서 | 용도 | 언제 |
|---|---|---|
| **HANDOFF.md** (여기) | 현재 상태 + 다음 할 일 | **항상 먼저** |
| CLAUDE.md | 프로젝트 규칙·제약(어떻게 일할지) | 처음 1회 |
| context-notes.md | 결정 로그(왜 이렇게 됐나, 결정 1~20) | 특정 결정 궁금할 때 |
| PLAN.md | 큰 명세·로드맵 | 방향 의심될 때 |
| game/PAMPHLET.md | RPG 규칙·데이터계약·AI정책 | 조립카드/모듈 작업 시 |
| checklist.md | 세부 체크리스트 | 진행 추적 |

> 최신 상태만 둔다. 상세 프로즈는 git 히스토리·context-notes에.

## 지금 어디 (2026-06-15)

**층1(능력매핑) 완료, 층2(오케스트레이션) 진행 중. 조립카드 T-12 = 통합 frontier 실측 완료.**
50런으로 harness_lift +48%p, select-best가 단일카드를 1~2번에 넘음 → 난이도=창발적 통합. 그래서
모듈식 RPG(`game/` 골든)를 세우고 **조립 카드 T-000012**(전 시스템 통합, 4시나리오 골든 정확일치)로
진짜 통합 frontier를 측정했다.

### 🔑 조립카드 T-000012 측정 결과 (2026-06-15 17:54, 결정21 후보)
- **병렬 select-best로 통과**: 3-병렬 cap8 / 31단독 cold / 설계·오라클 고정(frozen/T-000012).
  **웨이브1 2번째 시도(sel02) 통과** — 4 시나리오 골든 *정확 일치*(후한통과 아님). 1 PASS /
  2 진짜 exec-실패 / 0 INFRA. → **단일시도 ≈1/3: 통합은 진짜 어렵지만 뚫리는 벽**(결정20 정량확인).
- **🔴 또 하네스 버그였다(최대 산출)**: 1차 측정은 전 시도가 가짜 `contract-missing`으로 죽음 —
  계약 게이트가 클래스메서드를 *맨이름*('run')으로만 등록, 정규화 계약명('BattleSimulator.run')과
  대조 실패. 안 고쳤으면 "통합 불가"로 오결론. **고침 + 회귀테스트**(gates.py, test_harness_fixes).
- **병렬 인프라 신설**: llm.py 전역 페이서(프로세스 단일 락·4초 — 워커수 무관 RPM15 상한, 9스레드
  실측 정확 4초 간격). select_run.py 인-프로세스 3-병렬 스레드풀(웨이브, 통과시 잔여미실행, 75분/시도).
  500 INTERNAL은 서버측·시변(11시 깨끗/오후 33%), 과거 순차런에도 있던 기존현상 — 병렬 탓 아님(429 0).
- 부수: 단계 로그 모델 라벨을 하드코딩→실제 모델명(get_model). frozen/ = 추적되는 고정 아티팩트.

### 설계 스왑 = frontier 귀속 완료 (2026-06-15 18:30, 결정21)
- **설계 A(140607, 4파일 BattleSimulator) vs B(135401, 5파일 status_effects분리·BattleEngine)**,
  오라클 동일·정답 고정(success_signal 29토큰 + 같은 test_acceptance.py), 같은 병렬 select-best.
- **둘 다 ≈1/3 (A: 1P/2F cracked@2, B: 1P/2F cracked@1), 둘 다 한 웨이브에 깸. 통과본 골든 정확일치.**
- **결론: frontier = 통합 *구현*, 설계 선택 아님.** 확연히 다른 분해가 같은 통과율 → 설계는 레버
  아님("분해 vs 통짜 차이없음"이 통합카드까지 확장). 어려움=여러 시스템 동시 정합 구현.
- N=3/설계라 표본 작음(정성결론은 확고, 통계 빡빡하진 않음). 보강은 한계효용 낮아 보류(사용자 결정).
- 도구: `python select_run.py <frozen-dir>`로 고정설계 스왑. frozen/T-000012(A)·T-000012-b(B).

(배경: 벤치마크/Design-Bank → "무료 gemma × 오케스트레이션 frontier"로 재정의됨, 상위모델 폐기.)

### 이번 세션 핵심 결과 (카드 4·5·6, 공정 하네스)
- **🔴 측정도구 버그 2개 발견·수리 (최대 산출)**: 과거 "모델 실패"의 상당수가 하네스 버그였음.
  - 계약 게이트가 **클래스 메서드를 못 봐** false contract-missing (T-5) → 메서드 인식 수정.
  - success_signal이 **단일 substring**이라 brittle (T-6: 모델은 성공했는데 oracle이 틀림)
    → **토큰 리스트(전부 포함)** 허용 + 스키마 + 프롬프트 견고화.
  - 고친 뒤 T-5·T-6이 깨끗이 PASS → **그 실패는 100% 하네스 탓**이었음.
- **구현은 26B = 31B** (L2-3): 26코더·26통짜 cold 모두 3/3. 싼 빠른 손으로 이 난이도 충분.
- **분해 vs 통짜(`--whole`) 차이 없음**: 아키텍처는 이 난이도에서 레버 아님.
- **노트(cold/warm) 효과 없음**: 이미 cold에서 통과(천장효과).
- **출력 한도 = 비제약**: thinking 끄거나 줄이면 단일콜 700줄도 무잘림. thinking 기본 ON 유지.
  thinking 폭주(분산)는 26B 현상, 31B는 얌전.
- **역할배정 = 미결**: role-26all / role-26head31hands가 **전부 INFRA(아침 API 장애)로 실패**
  → 26B 머리 능력은 *측정 안 됨*. API 안정 시 재실행 필요.

### L4-5 frontier 첫 측정 (2026-06-14, 결정 15)
- **카드 제작 완료**: T-000007(L4 파티전투), T-000008(L5 세이브 로그라이크). `bank_cards_l45.py`.
- **🔑 분산(variance) 발견**: L4를 26all-cold로 돌리니 1차 FAIL(26B 설계가 rich/click 끌어와
  API 오용) → fresh 재측정 PASS(2/2). **같은 조건인데 갈림** = 천장 아니라 설계 선택 흔들림.
  L5는 26all-cold PASS(4/4). 즉 한 번 런으로 "한다/못한다" 단정은 오판(직전에 그럴 뻔).
- **로그 정교화 반영**: index.json에 `critic_model`/`generator_model`/`whole`/`duration_sec`
  추가(역할·아키텍처·시간 정본화). 새 모듈 `variance.py` = 조건별 통과율(C)+노트델타(D).
  화이트리스트(rich/click)는 유지(사용자 결정). 테스트 298 통과.

### 결론 한 줄
공정한 하네스에선 **26B·31B 둘 다 L2-3을 다 한다.** L4도 천장이 아니라 **분산** 구간으로 보임
(26all PASS 가능). frontier 측정은 이제 **조건별 N회 통과율**로 천장 vs 분산을 갈라야 한다.

## 큰 결정 3개 (이번 세션, 정본)
- **역할 구성 확정(결정16)**: #4 31머리/26손=홈, #1 31단독=폴백(26B 죽으면 31손 자동강등),
  #2 26단독=낮 연구, #3 26머리/31손=폐기. 무료대체재 없음(Flash Lite=코딩 열위, 비상용도 기각).
- **난이도 재정의(결정17)**: L1~L5 감 라벨 폐기. 난이도는 선언 아니라 **반복 통과율로 사후 확정**.
  파일수·"상태로직 어렵다" 폐기. 오라클엄격도=측정품질(행동만 검증), K=런조건, dependency는
  관측값 신뢰, 실측은 카드에 저장 말고 계산, `spec_complete`로 난이도 vs 출제불량 분리.
- **로그 정교화**: index에 critic_model/generator_model/whole/duration_sec + `variance.py`.

## L4 cold/warm 결과 (26all, 완료)
- **cold 1/3, warm 1/3 → 노트 델타 +0%.** L4 26all은 분산 구간(천장 아님), warm 무효(주입
  노트가 시그니처·라벨 일반론이라 실패 원인 못 짚음). `variance.py T-000007`로 확인됨.

## 50런 결과 (31단독 cold, 완료 2026-06-15 06:51)
- **harness_lift = +48%p (헤드라인)**: 첫시도 22% → 자가수정후 70%. 50런 중 24런을 self-fix가
  건짐. **가치는 모델이 아니라 오케스트레이션 루프.** 총 콜 427(8.5/런), 12.8h(15분/런, thinking이
  시간 먹음), 환산 $0.61.
- **통과율**: T-1/3/4/6=100%, T-2=57%, T-5=50%, T-8=33%, **T-7=16%(벽)**. 분할 73% > 통짜 66%
  (통짜는 frontier 못 깸, 어려운 카드서 더 나쁨).
- **레벨≠난이도 확정**: L3(T-6)=100% > L2 둘(T-2·T-5)=50%대, L5(T-8)>L4(T-7).
- **T-7·T-5 실패 = 진짜 모델 한계**(pytest 로직 실패, 상태/확률). 하네스 깨끗 = free win 없음.

## select-best 결과 = frontier가 확률임 (결정20)
- select-best(retry+게이트선택 cap8)이 **모든 단일카드를 1~2번에 깸**: T5·T7·T8(1~2), 새 T9수식·
  T10정규식·T11상태모듈(전부 1). T7 16%도 retry로 싸게 넘음.
- **난이도 세 번 틀리고 얻음**: ≠검사수 ≠깊이 ≠신규규칙. **난이도=창발적 통합**(여러 시스템이
  여러 턴 함께 돌며 동시에 맞아야). 단일 모듈은 다 쉽다(명시적이면 모델은 번역만).

## 모듈식 RPG 착수 → `game/` 폴더 (측정과 분리, 결정20)
- **`game/` = 게임 정본 + 골든 오라클 소스.** PAMPHLET.md(신규규칙·계약·AI정책) + 레퍼런스
  구현(entities/status/skills/combat/main) + test_reference 10/10 통과 검증. 결정적.
- 골든 예: seed1→영웅14턴 / seed3→적33턴 / seed7→영웅10턴. (`cd game && python main.py --seed N`)
- 모델엔 비노출(정답지). 껍데기(에셋)는 나중 어댑터.

## 이번 세션 산출 (2026-06-15, 병렬 인프라 + RPD + 대시보드 + 베이스라인)
- ✅ **병렬 인프라**(결정22, checklist 1~3): 키풀+키별페이서(llm) / 연속리필+early-stop(select_run) /
  도커 세마포어2+메모리캡(docker_gate). 키 11개 실통과. 워커=키.
- ✅ **RPD 트래커**(결정23): key_usage.py = 키×모델×태평양날짜 일일콜수 집계+자동차단(1450),
  키 원문 미저장(지문). 자정 후 자동복귀. RPM은 4초 페이서가 담당(못 줄임).
- ✅ **전31 베이스라인 측정 + 심층분석(결정24)**: `T-000012 31solo width6` → **cracked@2, 7시도, 429=0**.
  실패 6건 100% 진짜 통합미스(하네스 무결, 4시나리오 전부틀림=all-or-nothing). **frontier 정체 규명 =
  틱/속도게이지 턴 스케줄러 엣지케이스**(게이지 이월·우선순위 재평가·상태틱 순서·콤보 리셋). 통과본이
  최저비용, 좁은빔=쌈. 장부 select_ledger.jsonl 마지막 줄.
- ✅ **전수조사 정리**: lessons.json 더미 "y" 20개 근원(테스트 격리 누락) 수리+청소(74→54). 영속파일
  오염 벡터 lessons 한 곳뿐 확인(나머지 격리됨).
- ✅ **대시보드 병렬 그리드**(현황 탭 개조): _live_runs로 라이브 런 전부 타일화(시도/단계/마지막/
  경과/수리/점수/상태). RPD 스트립. 라이브≥2면 그리드, 단독이면 기존 카드.
- ✅ **코드 전수검토 + 문서정리**: 활성 루프 전수 정독 + 55파일 위험패턴 스캔(bare except 0·
  mutable default 0). 잠복함정 정리(load_env·_name_used·by_run). AGENTS.md 삭제(CLAUDE.md 중복),
  CLAUDE.md 낡은 사실 정정(쿼터=키별병렬·통합frontier·비평1회), checklist 완료표기, 미해결 갱신.

## 돌고 있는 것
**측정 없음.** 대시보드 서버 8400에 **새 코드(병렬 그리드)로 재기동됨** — http://100.89.73.83:8400.
- 그리드는 **라이브 병렬 런이 돌 때만** 채워짐(끝나면 15분 후 윈도우 밖). 데모하려면 병렬 런 1회 필요.

## 다음 액션 (★다음 세션 여기부터)
1. **(선택) 4home 비용 측정 (안정 시간대만)**: `python select_run.py T-000012 4home <width>` →
   31solo 베이스라인과 비용↔통과율 비교(원목표). 26손이라 **미국 피크(UTC밤~아침=한국저녁~) 회피**.
   RPD 트래커가 깔려 있으니 키별 소진 자동관리됨. width 작게=비용측정.
2. **warm 캠페인**: 누적 노트(lessons/critique_notes)로 cold 대비 델타.
3. **형태 확장(별도 축)**: 어댑터 → 2D 방치형.
- (메모) 대시보드 그리드 실제 확인은 병렬 런 돌 때 폰에서 http://100.89.73.83:8400 현황 탭.

### 완료(이번 세션, 폴백)
- ✅ **가용성 폴백**(결정16): generator 429/5xx 소진 시 critic 모델로 1회 강등. 폴백대상=critic이라
  31단독·26단독은 generator==critic → 자연 no-op. `llm.py` _generate_with 추출 + 테스트 3.

## 카드 현황 (design_bank.sqlite, 10장 — gitignore라 bank_cards_*.py로 재빌드)
- T-1~8: L1-5 게임/앱(bank_cards_p2/l45). T-9 수식·T-10 정규식(bank_cards_l6). T-11 상태모듈(bank_cards_rpg).
- **T-9~11 = 단일관심사라 쉬움**(select-best 1번). T-12 = 조립카드(전 시스템 통합) = 단일시도 ≈1/3.
- **frozen/T-000012/** = 추적되는 고정 아티팩트: design.json(140607, 4파일 stdlib) + workspace/
  test_acceptance.py(손-박제 골든 오라클, game/ 레퍼런스로 4/4 재검증). resume용.

### 완료된 결정/작업 (이번 세션)
- ✅ **브랜치 단일화(결정18)**: 단일 워크트리 `C:\Users\USER\arag`, main 하나. 새 브랜치 금지.
- ✅ **최소 스키마(결정17)** / ✅ 50런·select-best 측정 / ✅ index 정리(104→56, 백업: zip +
  index.json.bak-preprune) / ✅ game/ 레퍼런스+골든.
> 전략(결정19): 팔 제품은 자꾸 녹음. ARAG 가치=연구/방법론/검증하네스/벤치마크.

## 측정 도구 (콜0)
- 관측 분류·점수: `observability.py`(limit_type/artifact_score) → `plan2.py`(라벨5/점수_auto/
  fingerprint, 파생) → `plan2_audit.py`(폰 감사 산문) / `plan2_notes.py`(USE/HOLD/DROP).
- 분산·노트효과: `variance.py`(조건별 통과율=천장/분산 + cold/warm 델타). index 새 필드
  (critic_model/generator_model/whole/duration_sec)에서 그룹 파생.
- 출력한도 프로브: `probe_output_limit.py`(모드별), `probe_ceiling.py`(큰 n). 일회성.
- 캠페인 드라이버: `select_run.py`(★층2 select-best: 통과까지 반복·cap·"몇번에 깸"),
  `obs_run.py`(31단독 관찰 50런, 통짜/분할 교대), `l45_run.py`(L4 cold/warm),
  `night_run.py`·`whole_run.py`·`recheck_run.py`·`cont_26b.py`·`auto_campaign.py`(과거 캠페인).
- 게임 정본·골든: `game/`(레퍼런스 RPG, `python game/main.py --seed N`로 골든 생성).

## 기계 정본 (사람 문서보다 우선)
- 코어: `runs/index.json`(+ critic_model/generator_model/whole/duration_sec/mode/prompt_version),
  `runs/*/events.jsonl`, `runs/*/llm_calls.jsonl`(콜당 토큰·finish_reason).
- 환경: **단일 워크트리 `C:\Users\USER\arag`(main)**. 카드 8장 = `bank_cards_p2.py`(L1-3) +
  `bank_cards_l45.py`(L4-5). DB `design_bank.sqlite`(gitignore). 과거 측정데이터 전체는
  `arag-bank-data-backup-20260614.zip`(280MB)에 보관 — 라이브 트리엔 index.json만 둠(prune).
- 캠페인 장부: `runs/night_ledger.jsonl` `whole_ledger.jsonl` `recheck_ledger.jsonl`
  `auto_ledger.jsonl`(⚠️ 06:47 이전 = 죽은 auto_campaign 노이즈, 시간 필터 필요).

## 세션 다이제스트 (1줄, 상세는 git·context-notes)
- **~10차**: 1차 본체 + observability 0단계 + Design Bank B0~B2.
- **11차(2026-06-13)**: B2 캠페인 복구→데이터 점검에서 측정 신뢰성 붕괴 발견. **대전환** —
  PLAN 2(게임/앱 cold/warm) 재설계, cold-mode·llm계측·plan2 모듈, 출력한도 실측(천장 비제약·
  thinking ON), 통짜 모드, **하네스 버그 2개 수리**, 26B=31B(L2-3) 확정, 상위모델 폐기.
  역할배정은 INFRA로 미결. 다음 = L4-5 frontier 사다리.
