# golem 체크리스트

## Golem Studio 파이프라인 §13 (Step 1~7 완주, 2026-06-17)
세부 측정·결정은 context-notes G25~G44, 현재상태·다음할일은 HANDOFF.md.
- [x] Step1 Contract Microkernel Replay (`contract_validator.py`·`replay.py`, replay 5/5, 키0)
- [x] Step2 Planning (`planning.py`, A/B/C + synthesis, FROZEN 계약)
- [x] Step3 Design (`design.py`, 4모듈 분해 + traceability)
- [x] Step4 Spec QA (`specqa.py`, 시나리오 구체화. SCN-006 오라클오류 G36 교정. BLOCKING 추적은 backlog)
- [x] Step5 Build v1 (`build_graded.py`, 합의 채점. 사다리 0.36→0.66→0.98→1.0)
- [x] Step6 Adversarial QA (`adversarial.py`, edge_cases 능동탐색 → EDGE-011/012 발견 → 계약 명문화로 소거)
- [x] logs 채점 갭 해소 (출력계약에 logs 줄 추가, RULE-07 로그 6/6 수렴)
- [x] Step7 Integration (`integration.py`, 최종 workspace 선정+static_gate+golden 채점+final_report. 방치형 24/24)
- [x] 장르확장 다리실험 — 발열/과열(결합) 카드: 합의 1.0, 골든 13/13. "결합=어렵다" 기각, 난이도는 틱 모호성·oracle 버그로 이동
- [x] 하네스 일반화 — build_graded·integration 계약구동(출력키=state_shape, 입력=시나리오 예시). 새 카드 코드변경 0
- [x] 자동 해소 루프 (`reconcile.py`) — 합의-vs-oracle 자동 diff + 31B 진단(AMBIGUOUS/ORACLE_BUG/BUILD_BUG)·AUTO/ESCALATE. diff/resolve/apply 검증 + 실측 1건
- [x] 외부 지적 수용분 하드닝(G45, 키0) — 합의-vs-oracle 자동diff wired / fixture 6종(replay 11/11) /
      module.exports.prop 미인식 버그 수정 / unique_issue_count lexical 라벨 / validator 정본+schema drift 경고 /
      path escape guard / assumptions·backlog 영속화 / FAILURE_TAXONOMY 통합 인벤토리(난립 방지, 매핑표 아님)
- [x] T0 reconcile 자동연결(G47, 코드 키0) — build_graded --reconcile/--apply: diff→resolve→AUTO적용→ESCALATE/BUILD_BUG 리포트. ESCALATE 자동적용 금지, BUILD_BUG는 재빌드 권장만
- [ ] (T1 전, 키0) AUTO 정확률 검증 로그 + 실패 사전분류(HARNESS/INFRA vs 카드/계약)를 reconcile/build_graded에 추가
- [ ] **T1 일반화 실험(설계=G48)** — 결합밀도 저/중/고 카드(고결합 1장 필수)를 --reconcile로. 첫 N=3은 정성 스모크. 1순위 지표=AUTO 정확률. Green=ESCALATE 낮음 AND AUTO 정확률 높음 AND oracle 일치(★키)
- [ ] 정량 판정 — multi-seed/동결합 다수 카드로 임계 기반(★키)
- [ ] 코어 다음 frontier = 자율 oracle × 고결합 카드 × reconcile calibration (UI/Asset는 별도 트랙, 결정적 렌더 채점법 선결)
- [ ] (backlog) levels 등 출력표면 확장 / adversarial BLOCKING 추적 / 발열 Adversarial QA·Integration 정식 완주

## (완료 기록) Golem Studio v0.1 Contract Microkernel Replay (2026-06-17)
- [x] `GolemStudioMode.md` 13장 구현 우선순위와 19장 Pending Decisions 재확인
- [x] `static_gate.py` 현재 CLI/함수 구조 확인 (평면 glob → src/ 못 봄 확인)
- [x] `golem/studio/schemas/module_manifest.schema.json` 작성 (v0.1 최소 필드, stdlib 손검증)
- [x] `golem/studio/fixtures/demo_pass/module_manifest.json` 작성 (runs/는 gitignore라 fixtures/로)
- [x] demo workspace CommonJS fake files 작성 (main.js + src/engine·state·movement.js)
- [x] import/export validator 작성 (`contract_validator.py`, checks 4종)
- [x] static_gate bridge 연결 (PENDING-003 I/O 계약)
- [x] static_gate.py src/ 지원 확장 (rglob+경로해소, 하위호환)
- [x] 음성 픽스처 4종 (export불일치·파일누락·순환·bare default)
- [x] `replay_result.json` 생성
- [x] `contract_validation_report.md` 생성
- [x] Gemini/Gemma API 호출 0회 확인
- [x] 검증: replay 5/5 통과, static_gate 무회귀(기존 평면 게임 ok:true 유지)

## Step 2 — Planning A/B/C 측정 (하니스 빌드+replay 완료, 실키 발사만 go 대기)
- [x] `planning.py` — A(self-review)/B(1+3)/C(1+10) arm, 리뷰어 키 병렬, dedup 메트릭(unique/dup_rate/blocking)
- [x] A안 정의 = lead 자기검토(self-review, 편향) → A/B/C가 "독립리뷰가 self-review 이기나" 측정
- [x] 리뷰 스키마(§6)·10축(§2.2)·PENDING-004 판정(§19) 반영
- [x] fake 픽스처 replay 검증 — 의도적 중복으로 dedup 작동 확인(A2<B6<C12 unique, dup 0.077), API 0회
- [x] (★키) `planning.py --idea 방치형게임` 실측 — A6<B11<C27 unique, 독립리뷰>self·10>3 둘 다 임계 통과(G27)
- [x] (★키) synthesis 추가 + 실발사 — BLOCKING 11→0, 부동소수점 floor() 못박음, 계약 FROZEN(G28). 패킷=planning_packet/
- [x] (키X) dedup 토큰 Jaccard 클러스터링 — 결론 강건성 확인(임계 무관 A<B<C). 진짜 의미 dedup은 보류(G29)
- [x] (★키) Build v0 `build.py` — FROZEN 계약 → gemma 구현 → static_gate+v0.1 정합+스모크. 방치형 cracked@4 10/11(G30)
- [x] (점검) §13 순서 어긋남 발견 — 1,2 후 5(Build)로 점프, 3·4 건너뜀. design.py import 버그 수정. 순서 복원(G31)
- [x] (★키) Step 3 Design `design.py` — 방치형 4모듈 분해(utils←state_manager←engine←main), RULE 6개 traceability, §7·§8.2 PASS. design_packet/

## §13 순서 — 남은 단계
- [x] (★키) Step 4 Spec QA `specqa.py` — 11 시나리오 구체화·RULE 6개 커버·오라클위험 표시. 단 초안(결함: ACTIVE 오라클오류·float경로 미검·BLOCKING 추적안됨 G32). 사용자: 초안으로 두고 진행
- [x] (★키) Step 5 Build v1 `build_graded.py` — design 4모듈 + specqa 시나리오 + 합의 채점. contract_validator에 strict 모드 추가(빌드=느슨, v0.1 5/5 무회귀). 게이트 3/11, **합의 0.36**(G33)
- [x] 발견: 출력 계약 미고정 → 빌드가 무슨 key 찍을지 제각각(undefined 버그 포함). 합의 채점이 "스펙 안 빡빡"을 특권golden 없이 잡음
- [x] (★키) 한 변수 실험 — 출력 계약 고정(4 key) → 합의 0.36→0.66, 게이트 3→8/11(G34). 방향 확인
- [x] 점검: 0.66 반쪽 — 빌드가 시나리오 actions 미실행(turn:0/undefined). 입력 스키마 미고정이 남은 원인
- [ ] (다음, ★키) 입력(시나리오) 스키마 고정 → 빌드가 actions 실행 → 합의 재측정(0.66→?)
- [ ] (★키) Step 6 Adversarial QA — edge_cases.json + acceptance draft 다듬기(ACTIVE)
- [ ] (backlog) specqa validator 강화(계약 외 상태값 거부+BLOCKING 해소 추적) / 측정 N≥10 장르확장

## 과거 히스토리

### Phase 0 — 셋업
- [x] 이름·폴더 확정 (golem, `arag/golem/`)
- [x] node 가용성 확인 (v24.15.0)
- [x] 플랜/체크리스트/컨텍스트노트 생성
- [x] 스케줄러 스펙 한 장 (후속 실험에서 대체됨)

### Phase 1 — 전투엔진 JS 스파이크 (T-000012 JS판, 4 고정 시나리오) — 완료
- [x] make_golden.py — game/로 시나리오 파티+정답 생성·검증 (4/4 골든 일치)
- [x] grade.py — node main.js --scenario N 출력 vs 골든 정확일치 + 첫불일치 (스모크 검증)
- [x] worker_prompt.py — PAMPHLET 규칙+고정파티+출력계약 (정답 비노출)
- [x] driver.py — 키 11개 병렬 select-best(워커=키) + --replay 점검모드 (plumbing 검증)
- [x] 스파이크 실행 — 런 20260616-130305, **cracked@10, 11시도 중 5통과**, 총 $0.031
- [x] 통과본 독립 재채점 — attempt01·10 둘 다 4/4 정확일치 (우연 아님 확인)
- [x] 통과본 검수 — 4파일 304줄, 껍데기·미사용 import 없음, 스케줄러 레퍼런스 일치 → 재작성 불필요

### 판단 기준 — 결과
- gemma JS 엔진이 4 시나리오 골든 정확일치하나 → **됨**. cracked@10 (Python T-000012 cracked@2 대비 더 어렵게 걸림, 통과율 5/11).
- Claude가 packet/diff만으로 얕게 끝내나 → **아니오**. 4파일 전부 읽고 로직 추적, 품질 양호 확인.
- 실패 6개 패턴: 시나리오1 턴 카운트 ±오차 4개(턴 스케줄러 frontier 동일) + require 경로 깨짐 2개.

### Phase 2 — 표현층 바인딩 (사용자 선택: 실용)
- [x] `golem/web/engine.browser.js` — 검증엔진(attempt10) 무수정 로직 + trace. 공유 모듈(browser+node).
      **표현층(스킨)이 갈아끼우는 단일 진실원.** 룩이 바뀌어도 이 파일은 안 바뀜.
- [x] `golem/web/battle.html` — 공유엔진 + **이모지 스킨**. 캐릭터 이모지·공격 들썩·피격 흔들림·
      데미지 숫자 플로팅·스킬 아이콘·HP/gauge바·상태배지·승자배너. 폰 세로. 스킨=SKIN 객체 한 곳.
- [x] `golem/web/samples.html` — 룩 비교 목업(A 이모지 / B 레트로도트 / C 네온). 사용자가 **A 이모지** 선택.
- [x] `golem/web/_verify.js` — 공유엔진 vs 골든 무회귀 가드. **4/4 PASS** (이모지 개편 후 재확인).
- [x] 아이폰 확인 — 테일스케일 `http://100.89.73.83:8731/golem/web/battle.html`로 폰 접속 OK.
- [ ] (선택) 다른 스킨(레트로/네온) 추가 시 SKIN을 스킨객체 배열로 승격 + 셀렉터. 지금은 이모지 1종.
- [ ] (선택) 인터랙티브화 — 스킬 선택 플레이는 엔진 변경(메카닉 확장)이라 골든 재검증 필요.

### Phase 3 — Game Bank + A 오라클 (검증엔진 라이브러리)
방향(사용자 2026-06-16): A 방식(Claude 레퍼런스 오라클)으로 여러 게임을 만들어 DB(은행)에 쌓고,
베이스로 확장. 단계 = 1)은행+A골격(키X) 2)새 게임 1개 생성(런·go필요) 3)확장 루프(런).
#### 1단계 — 은행 + A 파이프라인 골격 (키 안 씀) — 완료
- [x] `game_bank.py` — sqlite 카드 은행(스키마 + save/get/list). 카드 = 규칙·시나리오·골든·솔루션·레퍼런스.
- [x] `oracle.py` — JS 레퍼런스 impl → 골든 생성(grade 러너 재사용). **game/ 의존 제거 = A경로 핵심.**
- [x] `bank_init.py` — 카드 #1 "tempo-combat" 적재(규칙=RULES, 시나리오=golden/, 솔루션=attempt10).
- [x] 무회귀: oracle로 솔루션에서 골든 재생성 → 저장 골든 4/4 일치(game/ 없이 골든 나옴 증명).
- [x] driver/worker_prompt/grade 카드 파라미터화(`--card slug`, 기본값 유지). replay 양쪽 PASS, 프롬프트 동일.
- [x] `game_bank.sqlite` gitignore(바이너리·재생성 가능).
#### 2단계 — 새 게임(2048류 합치기 퍼즐) A 생성 (준비=키X 완료, 런=go필요)
- [x] 입출력 일반화 — 골든=평면 `key:value` dict 정확일치(전투의 winner/turns/hp도 자연 포함),
      입력=임의 JSON. grade/oracle/worker_prompt/driver 게임-중립화. **새 게임이 강제한 일반화.**
- [x] 카드#1 무회귀 — 일반화 후 bank_init 재적재, 솔루션 여전히 4/4 PASS.
- [x] 카드#2 "merge-2048" — Claude 결정적 2048 레퍼런스(board/moves/main.js)+규칙+4시나리오 →
      oracle 골든 → 적재. 레퍼런스 self-채점 PASS. 골든 손검산 OK(sc1 L→4·sc2 L→12 등).
- [x] **생성 런** `driver.py --card merge-2048` (런 20260616-143058) — **cracked@4, 11/11 전부 통과**,
      $0.027. attempt04 독립 재채점 4/4 정확일치(멀티파일 board/moves/main 157줄). 통과본=카드 solution 갱신.
      → **A 방식이 처음 보는 게임(2048)에도 됨 확정.** 전투(5/11)보다 깔끔 — 규칙이 명확할수록 잘 됨.

#### 3단계 — 확장 루프 (준비=키X 완료, 런=go필요)
선택 메카닉 = 2048 + 벽(장애물). 베이스 solution을 워커에 줘 "맨바닥 대비 확장이 싸게 되나" 측정.
- [x] 베이스 주입 경로 — worker_prompt.build_prompt(base_files=), driver `--base <slug>`.
- [x] 카드#3 "merge-2048-walls" — 확장 레퍼런스(moves.js만 벽 세그먼트화)+전체 규칙+4 벽시나리오 →
      oracle 골든. self-채점 PASS, 골든 손검산 OK(sc1 [2,-1,2,2]L→2,-1,4,2 등).
- [x] 확장 프롬프트 점검 — BASE IMPLEMENTATION(베이스 코드)+벽 규칙 포함(8966자).
- [x] **확장 런** `driver.py --card merge-2048-walls --base merge-2048` (런 20260616-144906) —
      **cracked@7, 11/11 전부 통과**($0.030). 맨바닥 2048(11/11)만큼 깔끔. 통과본=카드#3 solution.
      **재사용 증거**: attempt07이 board.js를 베이스 그대로(24줄 동일) 두고 moves.js만 벽 세그먼트로
      키움(67→99) + main.js 벽시나리오. = 맨바닥 재작성 아닌 진짜 확장. → **확장 루프 됨 확정.**

### Phase 4 — 자율 오라클: 31B가 골든까지 만든다 — 작동 입증
지금은 Claude가 오라클을 짰다. 사용자 제안 = 주제+최소규격만 주고 31B가 오라클 설계. 핵심 리스크 =
오라클 신뢰(출제=응시 같은 모델). 해결 = 오라클도 게이트(독립 gemma 합의).
- [x] `oracle_design.py` — 31B에 [주제+메타규격(META)] → 규칙·레퍼런스·시나리오 설계. 파싱+정적점검
      (멀티파일·Math.random없음·node실행·key:value)+oracle 골든화+카드 적재.
- [x] **자율 설계 런** (theme=Snake) — 31B 첫 시도 성공: game.js/main.js, 골든 생성. $0.003.
      규칙 2342자(좌표계·벽/자기충돌·먹이 리스폰·꼬리순서 명세). 카드 'snake-auto'.
- [x] **합의 검증 게이트** `driver --card snake-auto` — 독립 11개 중 **10/11 합의**(31B 골든과 정확일치).
      실패 1 = 출력형식 실수(규칙 해석 아님). 죽는 시나리오 포함 일치 → 모호점도 합의 안 깸. $0.021.
      → **자율 오라클 작동 확정**(강신뢰 과반 크게 넘음). 통과본=snake-auto solution.
- 결론: 31B가 게임+오라클을 스스로 설계 + 독립 합의 게이트가 신뢰 보증. golem 자율화 핵심 입증.

### Phase 5 — 랜덤 주제 대량 측정 캠페인 후보
메커니즘 입증됐으니 주제를 계속 바꿔 대량으로 돌려 측정. 측정축 = 주제별 오라클 생성 성공률 /
합의율 분포(명확↔모호) / 자율 신뢰 통과율 = **무료모델×자율오라클 한계 지도**. ⚠️대량 키 소비 =
사용자 명시 지시+사전 점검 필수. 현재 다음 작업은 아님.

## Golem Studio Mode 문서 정리 (2026-06-17)
- [x] `11명/팀원` 표현을 `11 worker slots/병렬 샘플링 슬롯`으로 재정의
- [x] v0.1 구현 범위를 Contract Microkernel Replay로 축소
- [x] 질문 등급, 변경 등급, deprecation, Spec QA/Adversarial QA, JSON traceability, 롤백 분류 반영
- [x] 문서 내부 충돌 표현 재검색
- [x] 문서 검증 결과 보고

## Golem Studio v0.1 Pending 기본값 정리 (2026-06-17)
- [x] v0.1 JS module format을 CommonJS only로 고정
- [x] module_manifest v0.1 최소 필드 예시 추가
- [x] static_gate bridge 입력/출력 JSON 기본값 추가
- [x] A/B/C 비교 provisional threshold 추가

## Golem Studio 선회 핸드오프 정리 (2026-06-17)
- [x] HANDOFF의 예전 생산 분할 Step 1 예정분 폐기 표시
- [x] 다음 작업순서를 Contract Microkernel Replay 기준으로 재작성
- [x] CLAUDE.md와 GolemStudioMode.md 충돌 여부 점검
- [x] 필요한 CLAUDE.md 우선순위 규칙 최소 반영
- [x] 문서 재검색 및 커밋
