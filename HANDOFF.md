# HANDOFF.md — 진행상황 스냅샷

## ▶ 새 세션 여기부터 (3단계만)
1. **읽기**: 이 파일의 `지금 어디` + `다음 액션` 두 섹션만. 그거면 바로 시작 가능.
2. **지금 할 일 (한 줄)**: **조립 카드 T-000012 select-best 저항 검증 실행** — `python select_run.py`
   (31단독 cold, cap8). cap 안에 못 깨면 진짜 통합 frontier. 카드는 제작·DB삽입 완료(아래).
   상세는 `다음 액션` 1번. 규칙은 `game/PAMPHLET.md`, 골든은 `python game/main.py --seed N`.
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

**층1(능력매핑) 완료, 층2(오케스트레이션) 착수 중.** 50런으로 harness_lift +48%p 확인,
select-best가 단일카드 frontier를 1~2번에 넘음 → **난이도=창발적 통합**임을 발견. 그래서
모듈식 RPG(`game/` 골든 레퍼런스)를 세우고, 다음은 **조립 카드**로 진짜 통합 frontier를 찾는다.
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

## 돌고 있는 것
**없음.** (대시보드 서버만 8400에 떠있음 — http://100.89.73.83:8400, 31단독 필터.)

## 다음 액션 (★다음 세션 여기부터)
1. **조립 카드 T-000012 저항 검증 실행**: `python select_run.py`(31단독 cold, cap8). 카드 제작·삽입
   완료(`bank_cards_assembly.py`, goal에 PAMPHLET 전체+4시나리오 고정파티+골든 자체포함, 오라클=A
   winner/turns/final_hp 정확일치). 모호점 2개(턴=행동단위·스킵포함 / 틱내 재처리·이월)는 goal에
   명시로 못 박아 가짜 MODEL_FAIL 차단. 파티는 고정데이터(후자 노선 — RNG 재현 요구 안 함).
   **cap 안에 못 깨면 드디어 진짜 frontier.** 장부: runs/select_ledger.jsonl.
   - 골든은 `game/main.py --seed N`(또는 `--trace`)으로 재생성(레퍼런스가 정본).
   - ⚠️ select_run은 실제 API 호출 = 시간/쿼터 소모. 아침 API 장애시간 피해서 실행.
2. **frontier 확정 후** → **폴백 구현**(`llm.py` 26B 5xx/429 소진 시 31B 1회 강등, 26단독 no-op,
   테스트) → **시니어+주니어(26주니어/31시니어)**: select-best 바닥선보다 *싸게* 통합 깨나.
3. **warm 캠페인**(맨 뒤): 누적 노트로 cold(70%) 대비 델타. T-5·T-7을 노트가 구하나.
4. **형태 확장(별도 축)**: 어댑터 → 2D 방치형.

## 카드 현황 (design_bank.sqlite, 10장 — gitignore라 bank_cards_*.py로 재빌드)
- T-1~8: L1-5 게임/앱(bank_cards_p2/l45). T-9 수식·T-10 정규식(bank_cards_l6). T-11 상태모듈(bank_cards_rpg).
- **T-9~11 = 단일관심사라 쉬움**(select-best 1번). 진짜 frontier는 *조립 카드*(아직 미제작).

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
