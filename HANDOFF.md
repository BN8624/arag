# HANDOFF.md — 진행상황 스냅샷

> 새 세션은 이 파일 먼저. 지침 = [CLAUDE.md](CLAUDE.md), 계획 = [PLAN.md](PLAN.md),
> 결정 로그 = [context-notes.md](context-notes.md), 체크리스트 = [checklist.md](checklist.md).
> 최신 상태만 둔다. 상세 프로즈는 git 히스토리·context-notes에.

## 지금 어디 (2026-06-14)

**방향 대전환 완료.** 벤치마크/Design-Bank 중심에서 **"무료 gemma × 오케스트레이션의
frontier"**로 재정의(상위모델 에스컬레이션 영구 폐기). 측정 장치를 PLAN 2로 재설계하고,
어려운 카드(L2-3 게임/앱)로 첫 실측을 돌렸다.

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

## 돌고 있는 것
- **role-26head31hands-cold (T-000007 L4)** — `l45_run.py`, 재시도 중(130937-retry).
  26B 머리가 또 rich/click 설계 → 31B 손이 수리 중. API 백오프로 느림. 완료 시 장부
  `auto_ledger.jsonl` 기록. (이 런은 구버전 reporting.py로 기록돼 새 필드 없음.)

## 다음 액션
1. **role-26head31hands(L4) 완료 확인** → 26all과 비교(머리 차이가 rich 선호에서 갈리나).
2. **조건별 반복 측정(N≥3)**: `variance.py`로 천장/분산 가르기. 한 번 런 결론 금지.
   분산이면 레버 = "설계 선택 좁히기"(stdlib 강제·plain 출력·`--resume` 설계 고정)지 모델 교체 아님.
3. **L4-5 warm 캠페인** → `variance.py` (D) 노트델타 계산(지금은 cold만이라 D 비어있음).
4. (보류) 아키텍처 사다리 #3 시니어+주니어·국소패치 — frontier에서 #2 통짜가 무너질 때만.

## 측정 도구 (콜0)
- 관측 분류·점수: `observability.py`(limit_type/artifact_score) → `plan2.py`(라벨5/점수_auto/
  fingerprint, 파생) → `plan2_audit.py`(폰 감사 산문) / `plan2_notes.py`(USE/HOLD/DROP).
- 분산·노트효과: `variance.py`(조건별 통과율=천장/분산 + cold/warm 델타). index 새 필드
  (critic_model/generator_model/whole/duration_sec)에서 그룹 파생.
- 출력한도 프로브: `probe_output_limit.py`(모드별), `probe_ceiling.py`(큰 n). 일회성.
- 캠페인 드라이버(worktree): `night_run.py`(6h cold/warm), `whole_run.py`(통짜 비교),
  `recheck_run.py`(재측정), `cont_26b.py`(26B 후속), `auto_campaign.py`(무인 순차).

## 기계 정본 (사람 문서보다 우선)
- 코어: `runs/index.json`(+ mode/notes_enabled/prompt_version 기록), `runs/*/events.jsonl`,
  `runs/*/llm_calls.jsonl`(콜당 토큰·finish_reason 기록).
- 측정 환경: 격리 worktree `../arag-bank`(브랜치 `bank-b2-env`). 카드 6장 = `bank_cards_p2.py`.
  탐색기 데이터는 `_exploration/`(gitignore).
- 캠페인 장부: `runs/night_ledger.jsonl` `whole_ledger.jsonl` `recheck_ledger.jsonl`
  `auto_ledger.jsonl`(⚠️ 06:47 이전 = 죽은 auto_campaign 노이즈, 시간 필터 필요).

## 세션 다이제스트 (1줄, 상세는 git·context-notes)
- **~10차**: 1차 본체 + observability 0단계 + Design Bank B0~B2.
- **11차(2026-06-13)**: B2 캠페인 복구→데이터 점검에서 측정 신뢰성 붕괴 발견. **대전환** —
  PLAN 2(게임/앱 cold/warm) 재설계, cold-mode·llm계측·plan2 모듈, 출력한도 실측(천장 비제약·
  thinking ON), 통짜 모드, **하네스 버그 2개 수리**, 26B=31B(L2-3) 확정, 상위모델 폐기.
  역할배정은 INFRA로 미결. 다음 = L4-5 frontier 사다리.
