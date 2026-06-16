# golem 컨텍스트 노트 (결정 + 왜)

## G1 — 정체성: Claude 사용량 절감용 게임 룰엔진 오프로드
ARAG 본체(무료모델 frontier 연구)와는 별개의 실용 도구다. gemma가 손(구현), Claude가
머리(조율). 목적은 사용자가 Claude를 쓸 때 Claude를 덜 닳게 하는 것.
왜: 사용자 결정(2026-06-16). 연구 정체성 논쟁은 빠지고 실용 도구로 합의.

## G2 — 그릇 = JS/TS 웹 (Godot 아님)
근거: gemma 강점=Python/JS, 약점=GDScript. 사용자=폰 작업·판단 → 웹=즉시 플레이.
장르=로직중심 → 웹 적합. 출처: Gemma4 모델카드(HumanEval/MBPP=Python, 강점언어 Python/JS/SQL),
저자원언어 서베이(arxiv 2410.03981), godot-dodo(GDScript는 파인튜닝 필요), MultiPL-E(GDScript 미포함).
→ GDScript 천장을 재는 대신 강점언어로 비껴간다.

## G3 — Phase 1 = 스케줄러부터 (제일 어려운 것 먼저)
ARAG 실측: 난이도=창발적 통합, frontier 벽=틱/속도게이지 턴 스케줄러(T-000012, 단일≈1/3, cracked@2).
de-risk 원칙: 벽을 먼저 치면 뚫림/한계를 싸게 배운다.

## G4 — 격리: Phase 1은 host node + 타임아웃 (docker-node는 나중)
생성물=순수 계산 스케줄러(네트워크·FS 불필요)라 host node + 타임아웃 + temp dir로 충분.
ARAG 본체는 docker 격리(docker_gate) — golem도 멀티 시스템 통합 단계 가면 docker node로 격상.
node 미설치 시: docker node 이미지로 대체.

## G5 — 오라클: ARAG 트레이스diff 철학 재사용
골든 = 레퍼런스 구현이 뱉는 seed→트레이스(모델 비노출). 게이트 = 정확일치 diff(콜0).
자가수정 = 첫-발산 위치 힌트(ARAG 결정27의 JS판).

## G6 — 스파이크 범위 = 전투엔진 통째(스케줄러 단독 아님), 4 고정 시나리오
game/ 읽어보니 스케줄러 난이도가 상태이상·콤보와 분리 불가(타이밍 상호작용이 곧 난이도).
그래서 T-000012와 동일하게 *전투엔진 전체*를 JS로 재구현, 4 고정 시나리오(winner/turns/엔티티HP
정확일치)로 채점. RNG(파티생성)는 워커 범위서 제외(시나리오=고정 파티 입력) → CPython RNG
재현이라는 불공정 짐 없음. 골든은 game/로 공짜 생성(make_golden, 4/4 일치 검증). T-000012(파이썬
cracked@2)와 사과-대-사과.

## G8 — A 방식(Claude 레퍼런스 오라클)이 처음 보는 게임에 일반화됨 (2026-06-16)
golem을 일회성 데모에서 도구로: 검증엔진을 카드로 쌓는 은행(game_bank.sqlite) + A 오라클
(oracle.py — JS 레퍼런스→골든, game/ 의존 제거). 새 게임은 정답이 없다는 문제를, Claude가
레퍼런스 1벌 짜서 골든 생성으로 푼다. 검증: 카드#2 결정적 2048을 A로 적재 → 생성 런
**cracked@4, 11/11 전부 통과**(전투 카드 5/11보다 깔끔). 새 게임이 입출력 스키마(전투 전용
winner/turns/hp)를 강제로 일반화시킴 → 골든=평면 key:value 정확일치(전투·퍼즐 한 틀).
교훈 재확인: 규칙(RULES)이 레퍼런스를 빈틈없이 명세하면 싼 모델도 처음 보는 게임을 맞춘다
— frontier는 모델이 아니라 계약 정밀도에 있다. 다음 = 확장 루프(베이스 카드 + 메카닉 추가).

## G9 — 확장 루프 됨 + Phase 4 방향: 자율 오라클 (2026-06-16)
3단계 확장 루프 검증: 통과한 merge-2048 solution을 워커에 컨텍스트로 주고(driver --base) "벽 메카닉
추가" → cracked@7 11/11. 통과본이 board.js를 베이스 그대로 두고 moves.js만 벽 세그먼트화 = 맨바닥
재작성 아닌 진짜 재사용/확장. 은행이 베이스로 쓰일 때 확장이 싸게 됨을 입증.
**Phase 4 제안(사용자)**: 지금은 Claude가 오라클(레퍼런스+규칙+시나리오)을 손수 짠다 = 사실상 설계.
golem 목적이 Claude 절감이니 그 설계도 31B에 넘기자(주제+골든 최소규격만 Claude가). 핵심 리스크 =
**오라클 신뢰**: 출제(레퍼런스)와 응시(후보)가 같은 모델이면 상관된 오류로 가짜합격 가능. 해결 =
오라클도 게이트 통과 — 독립 gemma K개가 *규칙만* 보고 재구현해 골든에 합의하면 규칙이 정답을
명확히 담았다는 증거(레퍼런스 자의성 배제) + 그게 통과본. 합의 낮으면 규칙 모호 → 31B 재설계.
= select-best/출제·응시 분리 정신을 오라클 생성에 적용. 끝점 = 주제만 주면 도는 자율 게임 생성기.

## G10 — 자율 오라클 작동 입증: 31B가 오라클 설계 + 독립 합의로 신뢰 보증 (2026-06-16)
Phase 4 = 오라클(규칙+레퍼런스+시나리오) 생성 자체를 31B에 넘김(oracle_design.py). Claude는
메타규격(META: 평면 key:value·결정적·멀티파일·stdin금지·레퍼런스 의무)만 줌. 오라클 신뢰 리스크
(출제=응시 같은 모델 → 가짜합격)는 **합의 게이트**로 해소: 독립 gemma가 규칙만 보고 재구현해
레퍼런스 골든과 합의하는 비율 = 신뢰 점수. 검증: theme=Snake → 31B 첫 시도에 규칙 2342자+2파일
레퍼런스 설계, 합의 게이트 **10/11**(실패 1은 출력형식 실수). 죽는 시나리오·내가 짚은 head_pos
모호점도 합의 안 깸. → 자율 오라클 끝까지 작동. 신뢰 임계 데이터: 명확한 자율오라클이면 합의 매우
높음(10/11), 앞선 사람-오라클들(2048·벽 11/11, 전투 5/11)과 같은 결 — 합의율이 곧 규칙 명료도/
난이도 지표. 다음(Phase 5) = 랜덤 주제 대량 캠페인으로 합의율 분포 측정 = 무료모델×자율오라클
한계 지도. 주제 출처 미정(Claude 풀 vs 31B 자율).

## G13 — 부품 추가 시 시연 필수 (사용자 규칙, 2026-06-16)
부품0·1을 합의율(11/11)로만 보고하니 사용자(바이브코더)가 "눈으로 되는 걸 봐야 판단한다" →
**부품이 게이트를 통과하면 시연을 반드시 만든다**(숫자로 끝내지 말 것). 시연 = 통과본을 시나리오에
돌려 사람말 요약 + 격자 시각화(`@`=플레이어 `E`=적 등). 시연도 도구로 굳혀 부품마다 재사용(목표②,
손으로 다시 짜지 말 것). 규칙 정본 = CLAUDE.md "부품 추가 시 시연 필수". 방향 = G11.

## G12 — 타워디펜스 0/11 = 모델 아닌 계약 정밀도 (Claude 정밀화로 0→7/11, 2026-06-16)
Phase 5에서 타워디펜스만 0/11 완전 실패. 1원칙대로 오라클부터 의심 → 장부 발산 해부:
실패가 3갈래(크래시 5, 출력형식 kills=None 3, 로직불일치 kills=0·ticks=2 3)였고 단일 버그
아님. 손 트레이스로 시나리오1·2·3 골든을 만족하는 일관 해석 확인 → 31B 자율오라클 규칙이
**틱 종료 타이밍을 안 못박음**(종료를 currentTick +1 *전*에 판정하나 후에 판정하나 = off-by-one;
종료조건 "웨이브완료 AND 적0"의 AND 누락). **실험(단일변수)**: 골든 그대로 두고 규칙에만 실행
의미(루프 의사코드 + 종료조건 BOTH 명시 + ticks 정의 + 시나리오1 워크드 트레이스)를 덧붙인 카드
`auto-towerdef-tight`(`bank_add_towerdef_tight.py`, 골든동일 검증) → 같은 gemma 11개 재측정 =
**0/11 → 7/11 cracked@5 $0.019**. 겨냥한 로직불일치 3개가 **전부 0**(사라짐), 크래시 5→1. 잔여
실패 4 = 출력형식(kills 줄 미출력) — 틱로직 아님, 출력계약 예시로 잡을 다음 레버. **결론**: frontier는
모델능력이 아니라 계약 정밀도(반복 교훈 재확인). = 부품공장×시공자([[golem-direction]] G11)의 첫
하드 증거 — 시공자(Claude) 정밀화가 같은 부품공장(gemma)의 0을 7로 연다. 목표② 재사용 레시피
확보: "장르가 막히면 센 모델 말고 *실행의미 못박기 + 워크드 트레이스*" = 템플릿화 후보.

## G11 — 본 방향 확정: 부품공장×시공자, 목표=로그라이크, 개입최소화 2목표 (2026-06-16)
사용자가 프레임 교정: golem은 "작은 게임 통째 자율생성"이 아니라 **큰 게임 하나를 부품을 붙여
점점 키우는 것**이다. gemma=부품공장(결정적 룰엔진 부품), Claude=종합시공자(발주=계약작성 +
조립=계약대로 맞물림 + 갭메움=gemma가 못하는 부분 직접). = Phase 3 베이스주입(2048→2048+벽)의
일반화. **목표 큰 게임 = 턴제 로그라이크**(사용자 선택; 부품쌓기 교과서·결정적이라 골든채점 궁합·
바이브코더가 사람말 로그로 판단 가능). 발주 순서: 부품0(격자+결정적 이동)→적→전투→아이템→층이동→
시야·함정·적 다양화. **두 목표**: ① 일단 한 번 끝까지 만들며 Claude 손이 꼭 필요한 지점 실측 →
② 그걸 반복가능 패턴·도구로 굳혀 **Claude 개입을 점점 깎는다**(발주서→템플릿, 조립확인→정적게이트
콜0, 반복 갭메움→부품 사양 선반영). 부품당 Claude 콜·손댄 횟수 = 측정 지표(줄면 성공) = golem 본
목적(Claude 사용량 절감)의 실행형. 측정 재해석: Phase 5 합의율 = 통짜게임 신뢰도가 아니라 **부품별
gemma 신뢰도 지도**(높은 메카닉=발주만, 낮은=Claude가 메움). 새 핵심 미측정축 = **조립 가능성**
(부품 둘 이상이 계약대로 맞물리나).

## G7 — 드라이버 = 키 11개 병렬 select-best (워커=키), 독립 시도
처음 단일키 순차로 짰다가 사용자 지적(2026-06-16) — 키 11개는 RPM 쿼터가 각각 독립이라 병렬=11배.
arag select_run 패턴(KeyPool.checkout + ThreadPool, 첫 통과 시 미시작 취소) 채택. 시도는 독립
(self-fix 없음) = T-000012 병렬 select-best와 동일 모드. self-fix 웨이브는 옵션으로 미룸.


## G14 — 큰 걸음 검증: 4메카닉 동시도 31B가 쉽게 소화 (2026-06-16)
부품3에서 아이템·함정·계단·포션을 한 카드로 묶어 발주 → cracked@10, 11/11 통과($0.023). 캠페인이
frontier로 본 "여러 시스템 동시 맞물림"이 이 규모(턴제 격자)에선 안 막힌다. 단일 메카닉 부품은 너무
쉬워 비효율 → 사용자 결정으로 앞으로 큰 걸음(여러 메카닉/한 부품). 단일메카닉 cracked는 p0@4·p1@3·p2@10.

## G15 — 스케일은 출력토큰이 첫 천장(입력 아님), 측정 내장 (2026-06-16)
gemma는 상태없음(파일 못 읽음) → 베이스를 프롬프트에 주입(입력). 입력 TPM 무제한이라 안 막힘. 진짜
벽은 출력 32k(thinking 포함). 현 구조는 통째 재생성이라 게임 크면 출력도 통째로 커짐. 드라이버에 토큰
측정 내장(attempt·요약별 input/output/thinking, out+think vs 32k). p3 실측: 입력3896 / 출력코드~2132 /
thinking~3379 / out+think 최대 6619=20%. 여유 크나 어려운 부품서 thinking 부풀면 닿음. 사용자 지적.

## G16 — 완전 재설계: 엔진 모듈화 + 파일별 생성 (2026-06-16)
G15 해소. 사용자가 "완전 재설계" 택. ①엔진 6모듈: dungeon/chase/combat/items=안정·재사용(한번 쓰면 안
바뀜→재출력 안 함), engine=얇은 오케스트레이터+main. rogue-p3.solution을 모듈 베이스로 교체(골든 PASS,
bank_remodularize_p3.py). ②파일별 생성: 워커는 바뀐/새 파일만 출력, driver _one_attempt가 베이스+변경분
병합(안 낸 파일은 베이스서 채움). --replay로 검증(engine+main만 응답→나머지4 병합→PASS). 효과=부품당 출력이
전체 크기와 무관. 리스크(미검증): 모듈 추상화로 gemma 크랙률↓ 가능 → 부품4 키 발주로 확인 예정. 데모는
card.reference(모노) 사용이라 무영향.


## G17 — 재설계 검증: 모듈+파일별 생성이 스케일 해법으로 입증 (2026-06-16)
부품4(장비=무기·방어구·회복제단)를 모듈 베이스(rogue-p3) 위에 발주 → 11/11 cracked@10($0.020). 두 검증:
①gemma 11시도 전부 바뀐 4파일만 출력(combat·items·engine·main), 안정모듈(dungeon·chase)은 안 냄→
드라이버가 베이스서 병합. ②출력 토큰 감소(p3 ~2132 → p4 ~1937)인데 게임은 더 큼 = 파일별 생성 효과.
③모듈 추상화로 크랙률 안 떨어짐(G16 리스크 해소). 결론: 부품당 출력이 전체 크기와 무관 → 무한 확장
경로 확보. 앞으로 부품은 이 구조로 그대로 쌓는다(bank_add_roguelike_pN + driver --base 직전부품).


## G18 — gemma를 머리로: 자율 설계+자기 오라클, 합의로 검증 (2026-06-16)
사용자 직감("gemma 제대로 못 쓴다") 검증·확정. 원인 진단: 작음은 gemma 한계가 아니라 ①우리 정확일치
골든(손으로 못 쓰면 출제 못 함→작은 증분) ②소심한 주문. 설계 프로브(design_probe.py, 1콜): 야심 주문
주니 31B가 4개 맞물리는 시스템(LCG 절차생성·원소환경·상태이상·적 상태기계) 설계 — 결정성까지 스스로
챙김(고정 순회순서, Object.keys 회피). 새 작업방식 입증: oracle_design_ext.py = 31B가 베이스 위 원소
레이어를 [규칙+시나리오+레퍼런스] 자율 설계(out+think 8.6k=부품 4배), 레퍼런스로 골든 자가생성. 검증=
driver --card rogue-elem --base rogue-p4 → 독립 빌더 11/11 합의(cracked@3, $0.023), 전원 3파일만 출력
(파일별 생성 유지). **Claude는 규칙·시나리오·레퍼런스·골든 0줄**(브리프+베이스+형식만). 결론: gemma를
손→머리로 올리고 오라클을 자가설계+합의로 풀면, gemma 진짜 추론을 쓰고 Claude 개입은 실제로 급감(②).
self-bias 방어=빌더는 규칙만 보고 독립 구현→골든과 일치해야 함(규칙 안 따르는 골든오류는 불일치로 걸림).
미완: rogue-elem 시연(데모툴이 모듈 run(sc) 시그니처+grid 필드 미지원 → 데모 확장 필요).


## G19 — 정적 게이트 + 실행 격리 복원 (2026-06-17)
ARAG 무거운 파이프라인(정적게이트·도커·비평루프) 중 golem이 덜어낸 것 사용자 확인 후 핵심만 복원.
도커는 원래 없었음(golem은 node 직접 실행). 추가: static_gate.py(콜0) = node --check 구문 / require
그래프 도달성(고아 모듈=멀티파일 위장 차단) / npm 금지(빌트인·상대경로만) / Math.random 금지. grade.py
실행을 Node 권한모델(--permission --allow-fs-read=*)로 격리: 파일쓰기·자식프로세스·워커·네이티브 차단
확인(ERR_ACCESS_DENIED) + stdin DEVNULL. Docker 없이 호스트 격리. driver·oracle_design_ext가 채점/골든
생성 전 정적게이트 강제. 남은 공백: 네트워크는 권한모델이 안 막음(규칙·무npm으로 커버), required-but-unused는
미검(도달성만). 정확일치 오라클+합의가 여전히 주 게이트.

## G20 — 생산 분할(계층적 분해+인터페이스 계약) = 다음 프론티어 (2026-06-17, 사용자 아이디어)
관찰: 출력토큰 아직 ~8k(32k의 25%), 2-3배 여유. 사용자 제안: 병렬을 합의용으로만 쓰지 말고 *생산 자체*를
쪼개자 — 설계자가 전체를 A·B·C 모듈+계약으로 설계 → 모듈별 독립 빌더 분배 → 재귀 분할 → 조립. 효과:
①무한 크기(전체=Σ모듈, 각 모듈은 자기 32k 안에서만 → 출력천장 구조적 소멸) ②조립 가능성 직접 측정
(golem이 G6에서 못 잰 핵심 축) ③오케스트레이션 novelty(무료모델×오케 frontier 그 자체). 현 select-best와
차이: 같은 전체 중복생산이 아니라 다른 부분 생산→합침. 핵심 linchpin=인터페이스 계약 정밀도(모호하면 조립
실패=프론티어 데이터). 계획=Step1 PoC(설계자 manifest 확장 + 분배기/조립기 신규, --replay로 키없이 먼저),
Step2 모듈별 합의, Step3 재귀 분할. 착수 합의됨(다음 세션 시작점).

## G21 — Golem Studio Mode 문서 수정 방향 (2026-06-17)
사용자 판단: Golem Studio Mode 핵심은 유지하되 첫 구현 범위를 대폭 축소. 11개 Auth Key는 독립 인격이 아니라
역할별/관점별 `worker slot`으로 재정의한다. 다양성은 키 자체가 아니라 review_axis, temperature, 출력양식,
금지사항, 리뷰 기준에서 만들어야 하며 duplicate_issue_rate와 unique_issue_count로 측정한다. v0.1은 전체 스튜디오가
아니라 Contract Microkernel Replay로 제한한다: fake planning packet, module_manifest schema, fake build output,
import/export validator, static_gate bridge, replay report. 문서에는 질문 등급(BLOCKING/ASSUMED/DEFERRED),
변경 등급(L0~L4), DEPRECATION_REQUEST, Spec QA/Adversarial QA, JSON traceability 정본, 실패 분류별 롤백 기준을
반영한다. 과제는 산으로 가지 않게 문서 정정에 한정한다.

## G22 — Golem Studio v0.1 pending 기본값 (2026-06-17)
추가 판단: 남은 문제를 전부 상세 설계로 확장하면 문서가 다시 비대해지므로 `Pending Decisions / Known Open
Problems` 섹션으로 분리한다. 단 구현을 막는 항목은 v0.1 기본값을 고정한다. JS 모듈은 CommonJS only,
manifest는 `schema_version/module_format/entry/files[].path,exports,imports`만 사용, static_gate bridge는
`workspace_path`와 `manifest_path` 입력 및 `ok/checks/errors/warnings` 출력으로 고정한다. A/B/C 비교 기준은
임시값으로 둔다: B는 A 대비 unique_issue_count +30%, C는 B 대비 +20% 또는 추가 BLOCKING issue 1개 발견 시
유효. 10회 이상 실행 후 조정한다.

## G23 — HANDOFF 선회: 생산 분할 폐기, Contract Microkernel 우선 (2026-06-17)
사용자 지시: 기존 HANDOFF의 생산 분할 Step 1 예정분은 폐기하고, Golem Studio Mode 문서 방향으로 선회한다.
다음 작업은 11 worker slots 투입이나 분산 빌드가 아니라 v0.1 Contract Microkernel Replay다. 이유는 구현
시작 전에 module manifest와 실제 CommonJS 코드의 파일/export/import 계약을 기계적으로 검증할 수 있어야
역할 순환 구조가 무너지지 않기 때문이다. CLAUDE.md는 golem 폴더 전체 지침으로 유지하되, Golem Studio 구현
범위에서는 GolemStudioMode.md와 HANDOFF.md를 우선하도록 보강했다. CommonJS, npm 금지, Math.random 금지,
사용자 go 없는 키 런 금지는 기존 CLAUDE.md와 충돌하지 않는다.

## G24 — 문서 역할 축소 정리 (2026-06-17)
사용자 지시로 golem 문서 역할을 좁혔다. HANDOFF.md는 현재 위치와 다음 액션만, CLAUDE.md는 작업 규칙만,
GolemStudioMode.md는 새 설계 정본, context-notes.md는 결정 로그, checklist.md는 현재 활성 체크리스트를
맨 위에 두고 과거 Phase는 히스토리로 둔다. README.md는 전체 내용을 삭제하고 "개인 프로젝트 임."만 남겼다.

## G25 — Golem Studio v0.1 Contract Microkernel Replay 구현 + 사전 반박 (2026-06-17)
사용자가 "구현 전 반박부터" 요구 → 핵심 이견 정리. ① "11 slot 역할 순환"은 slot이 상태없는 샘플러라
메커니즘상 무의미한 포장(키=병렬성일 뿐), 진짜 substance는 Ambiguity Review+Traceability+FROZEN 계약.
② 헤드라인 11과 §15 실제 기본값 3 충돌 + 본체 결론(분해=차이없음, select-best가 해법)과 긴장 →
A/B/C 비교를 전체 파이프라인 짓기 전에 먼저 측정해야. ③ PENDING-002 bare-default 금지는 Step2에서
실제 gemma 코드를 거를 수 있음(의식적 결정 필요). v0.1 방향 자체(키X 계약 검증부터)는 옳음.
사용자 결정: 폴더는 src/ 유지+확장 래칫 대비, 음성 픽스처 포함.
구현: golem/studio/ 신설. contract_validator.py(checks 4종 manifest_schema/file_exists/import_export/
static_gate, PENDING-003 I/O 계약), replay.py, schema, 픽스처 5종(통과1+음성4: export불일치·파일누락·
순환·bare default). 픽스처는 fixtures/(runs/는 .gitignore라 추적 안 됨 — Step2+ 생성물용으로 비움).
static_gate.py를 rglob+경로해소로 확장(하위호환 — 평면 require는 그대로).
검증: replay 5/5 통과(API 0회), static_gate 무회귀(기존 merge-2048 attempt04 ok:true 유지, 신규 src/
워크스페이스 ok:true). 왜 이렇게: validator는 valid 입력만 보면 미검증이라 음성 픽스처로 "이빨" 증명.
다음(키 필요, go 대기): Step 2 Planning 팀만 실제 worker slot, 단 A/B/C부터 측정.

## G26 — Step 2 Planning A/B/C 측정 하니스 (키X replay 검증, 2026-06-17)
사용자 "고" → Step 2 진입. 프로젝트 검증된 2단계 패턴(준비=키X replay → 별도 go로 실발사) 유지.
이번엔 G25 권고대로 전체 6단계 짓기 전에 **Planning 한 단계 A/B/C부터** 측정하는 하니스만 만들었다.
핵심 설계결정: **A안 = lead 자기검토(self-review)**로 정의. 본체 핵심원칙(출제자=채점자 분리, self-grading
bias)에 맞춰 A/B/C가 정확히 "독립 리뷰어가 self-review를 이기나"를 측정하게 함. B=1+3, C=1+10(§15).
재사용: llm.py(LLMClient/KeyPool, 키별 페이서·429백오프·RPD 회계), driver의 키병렬 패턴. 31B=critic 역할.
구현: planning.py — arm별 run, 리뷰어 ThreadPool 키병렬, dedup 메트릭(unique_issue_count/duplicate_issue_rate/
blocking_count), §19 PENDING-004 판정(B>A +30%, C>B +20%). 스키마=§6, 10축=§2.2. fake/real caller 분리.
검증: fixtures/planning_demo/fixture.json(의도적 중복 포함)으로 replay → A2<B6<C12 unique, dup 0.077,
BLOCKING은 리뷰어에서만 1, API 0회. **plumbing 증명일 뿐 — 데이터 가짜, 리뷰어 실효는 실키 측정에서 갈림.**
다음(★키, go 대기): `planning.py --idea "..."` 실측 1회 → 독립리뷰 실효·reviewer 기본개수 판정.

## G27 — Planning A/B/C 첫 실측: 방치형게임 (2026-06-17, 키 씀)
사용자 아이디어="방치형게임"(틱 자원축적+업그레이드, 결정적 CLI로 적합). 31B 실호출.
결과: A(self) unique 6/blocking 3 → B(1+3) 11/6 → C(1+10) 27/12. B>A gain 0.83(≥0.30✓),
C>B gain 1.46(≥0.20✓). **둘 다 PENDING-004 임계 통과 = 독립리뷰가 self-review를 이기고, 10이 3을 이김.**
이슈 품질 진짜: 부동소수점 반올림(costMultiplier^level=float → 결정적 정확일치 깨는 1순위)을 리뷰어
여럿이 독립으로 잡음, '^' XOR/지수 해석 모호, 실패액션 처리(halt vs skip), 잘못된 scenario/upgrade id
처리, 최종상태 출력형식 등 — 전부 오라클 깨는 실질 모호성. self(A)는 일부만 잡음.
→ **G25의 내 회의(리뷰어 구조=죽은무게?)에 반하는 첫 실증거.** 단 두 caveat: ① N=1(§19는 ≥10 요구),
② dedup이 문자열정규화라 의미중복 못 잡음 → 같은 float반올림 이슈가 표현만 바꿔 여러 unique로 과대계상.
즉 방향(리뷰어 도움됨)은 신뢰, 크기(27 등)는 부풀려짐. 콜 비용=AI Studio 무료(api_calls 정밀집계 미연동).
다음 선택지: (a)아이디어 더 돌려 N 쌓기 (b)dedup 의미기반 개선 (c)synthesis로 진행(lead가 BLOCKING→0
정리+contract_packet). 권고=(c) 먼저(구조 실효는 정성적으로 충분히 확인) 또는 (b)로 측정 신뢰 먼저.

## G28 — Planning synthesis 실측: 방치형게임 계약 FROZEN (2026-06-17, 키 씀, 사용자 (c) 선택)
planning.py에 synthesis 추가: 초안→리뷰어10→lead가 이슈 흡수해 BLOCKING→0 + 계약 패킷(§4 핵심) 굳힘.
fake replay 검증(BLOCKING1→흡수→FROZEN) 후 실발사. 결과: 방치형게임 리뷰어 BLOCKING 11개 →
decisions 9/assumed 3/deferred 2로 전부 흡수 → 미해소 0 → **CONTRACT_STATUS: FROZEN**.
핵심 성과: 리뷰어가 잡은 부동소수점 모호성을 계약이 못박음 — **RULE-03 currentCost =
floor(baseCost*(costMultiplier**level))**. 그 외 WAIT만 턴증가, 잘못된 id 로그+스킵, energy>=1000 승리,
WON후 액션무시, 잘못된 scenario exit(1) 등 결정적 정확일치 깨던 모호점 전부 닫음. interface_contract=
2파일(main.js+engine.js, v0.1 validator의 module_manifest와 동형 → 그대로 물림), acceptance 3.
산출물: golem/studio/planning_packet/(concept/gdd/ambiguity_review/contract/acceptance_tests/questions/STATUS).
→ Golem Studio thesis(역할순환 리뷰→모호성 없는 FROZEN 계약) 실물 산출. caveat: acceptance expect가
아직 산문(정확값 아님) — golden 정확일치는 Build/오라클 단계 몫.
다음 후보: Build 단계 = FROZEN 계약을 기존 driver.py 11키 select-best에 줘 gemma 구현 → static_gate +
v0.1 contract_validator(매니페스트 정합!) + grade. 단 grade는 golden 필요 → 오라클(A방식/31B 레퍼런스) 연결 필요.

## G29 — 측정 신뢰 보강: dedup 어휘 클러스터링 + 결론 강건성 (2026-06-17, 키X)
사용자 "측정보강 나중에????" 지적 → 옳음. 게임은 도구, 측정이 본질. Build보다 측정 신뢰부터.
dedup을 정확일치 문자열 → 토큰 Jaccard 클러스터링(th=0.5, stdlib only, 불용어 제거)으로 교체.
정직한 한계: G27 실데이터 재측정 시 C 27→25(th0.5)밖에 안 줄음. 부동소수점 이슈가 "floating point
determinism"/"rounding method"/"rounding logic" 등 서로 다른 어휘로 ~3회 등장 → 어휘기반은 못 묶음.
진짜 의미 dedup = 임베딩(외부패키지=stdlib규칙 위반) or LLM 패스(키·다소 순환). → 보류.
핵심 발견(자보다 중요): 임계 0.5→0.4→0.3→0.25로 조여도 C 25→23→21→20. **A6 < B11 < C20~25,
gain 둘 다 임계 한참 위 — 어떤 자로 재도 방향 안 뒤집힘.** 즉 자는 부정확해도 "독립리뷰>self,
10>3" 결론은 강건. 효과 크기가 자의 흔들림보다 큼. caveat 남음: N=1(generalization 미검).
남은 측정 가치 = N≥10을 **서로 다른 장르 아이디어**로(모호한 게임 vs 명확한 게임에서 리뷰어 효과 다른가)
— 이게 §19의 진짜 목적(메트릭 정밀화 아니라 일반화). ★키 필요. 신규 run은 새 dedup 자동 사용.

## G30 — Build v0: FROZEN 계약 → gemma 구현 → v0.1 검증기 정합, end-to-end (2026-06-17, 키 씀)
사용자 "빌드로 전진". Build v0 스코프 = golden 정확일치(오라클) 보류, '계약대로 굴러가나'까지.
build.py: Planning 패킷의 interface_contract를 매니페스트로, data_contract를 규칙으로 gemma(31B critic)에
줘 멀티파일 구현 → 3중 게이트(static_gate + contract_validator 매니페스트 정합[v0.1 재사용!] + 스모크
node main.js --scenario 1 크래시 없이 key:value). fake build로 replay 검증 후 11키 select-best 실발사.
결과(방치형 계약): **cracked@4, 10/11 통과**. attempt04 검수=진짜(main 55+engine 66줄, 매니페스트대로
main.js+src/engine.js, GameState/GameEngine export). 실행: sc1 자원축적, sc2 에너지부족 처리, sc3 turn1000
WON — 규칙 실제 구현. 1실패=스모크 빈출력. **정직 caveat: 10개가 각각 다른 숫자(상수·시나리오 입력이
golden으로 미고정) → "10통과"=계약대로 굴러가는 게임 10개지 같은 정답 10개 아님. 정확일치=오라클(v1).**
의의: 아이디어 한 줄("방치형게임") → 리뷰→FROZEN 계약 → gemma 구현 → v0.1 매니페스트 정합 검증이
실모델로 한 줄에 꿰임. 처음 만든 v0.1 validator가 실 gemma 산출물에서 값을 함(설계 의도 실현).
build_runs/는 .gitignore(생성물). 다음: Build v1=오라클 골든으로 정확일치 채점 / or 측정 N≥10 장르확장.

## G31 — 순서 점검 + Step 3 Design 실행 (2026-06-17, 키 씀)
사용자 "문서 정독한거 맞아"·"처음부터 점검" 지적 → 옳음. §13 순서(1→2→3 Design→4 Spec QA→5 Build→6
Adv QA)를 어기고 1,2 후 5(Build)로 점프했었음. Build v0는 스파이크로 남기고 순서 복원.
점검서 design.py가 import 버그(_find_cycle은 contract_validator에 있음)로 안 돌던 것 발견·수정.
또 회귀 replay가 planning_compare.md를 가짜로 덮은 것 git restore.
design.py(§7·§8.2·§13 Step3 그대로): Planning 패킷 → lead 모듈분해+traceability → 리뷰어10 → synthesis
→ system_design.md/module_manifest.json/traceability.json/traceability_report.md. validator=모든 REQ가
≥1모듈·≥1테스트, manifest에 없는 파일/없는 test id 실패, 순환없음.
실행(방치형 계약): REQ6, **4모듈 분해**(utils 순수계산 ← state_manager 상태전이 ← engine 조율 ← main I/O),
각 모듈 책임·금지 명시, RULE-01~06 전부 추적연결, validator PASS, BLOCKING 2. **Build v0 통짜 2파일을
교정 — 진짜 멀티파일 분해**(프로젝트 핵심 "파일 간 정합성"). 산출=design_packet/.
다음(§13 순서): Step 4 Spec QA → Step 5 Build 재실행(이번엔 design 매니페스트+grade) → Step 6 Adv QA.

## G32 — Step 4 Spec QA: 채점가능 시나리오 초안 (결함 포함, 2026-06-17, 키 씀)
specqa.py: Planning/Design → lead가 산문 수용기준을 기계 시나리오로 + 오라클위험 표시 → 리뷰어10 →
synthesis. 산출 acceptance_tests_draft.json, oracle_risk_review.json. validator(§8.4)=모든 REQ ≥1 시나리오.
fake replay 검증(REQ6 커버, SCN-004 오라클위험 표시, PASS) 후 실행.
실행(방치형): 11시나리오, 전부 구체 입력(constants/initialState/actions)+정확 expected, RULE-01~06 커버,
validator PASS. 모델이 multiplier를 정수로 골라 float 회피→오라클위험 0(일리 있음).
**정직한 결함(점검서 발견)**: ① SCN-006 expected gameStatus "ACTIVE" — 계약엔 PLAYING뿐(모델이 없는
상태 지어냄=TEST_ORACLE_ERROR) ② RULE-03 float floor을 정수 multiplier로 테스트→정작 float 경로 미검
③ SCN-011 빈 시나리오(커버 0) ④ BLOCKING 5 떴는데 specqa 하니스가 synthesis 해소 추적 안 함(§13은 0
요구, planning은 추적했음) → 0 증명 못 함. **validator가 헐거움 — 커버리지만 보고 의미결함 못 잡음.**
사용자 결정: 초안으로 두고 Step 5 진행(draft는 Step 6 Adv QA가 다듬는 게 §11 설계, ACTIVE는 Step5
빌드-합의가 잡음). backlog: specqa validator 강화(계약 외 상태값 거부 + BLOCKING 해소 추적).
다음: Step 5 Build 재실행 — design 4모듈 manifest + specqa 시나리오 + 합의 채점(특권 golden 아님).

## G33 — Step 5 Build v1: 합의 채점이 "스펙 아직 안 빡빡"을 잡아냄 (2026-06-17, 키 씀)
build_graded.py: Build v0(2파일 스파이크)와 달리 ① Design 4모듈 manifest를 목표로, ② Spec QA 시나리오를
scenarios.json으로 공통 제공, ③ 정답을 특권 golden이 아니라 **빌드 다수합의**로 잼(사용자 산출물축소
우려 반영 — 오라클=자, not 우리). 오라클위험 시나리오는 채점 제외.
**발견1 — validator가 빌드엔 과하게 빡셈**: 첫 실행 0/11. 원인=정확-import-엣지 conformance가 멀쩡한
빌드(attempt02: 4모듈 정확, 단 main이 utils 한 번 더 import)를 거부. v0.1엔 맞지만 자유구현엔 과함.
→ contract_validator에 strict 파라미터 추가(기본 True=v0.1 정확일치 유지, 5/5 무회귀). Build는 strict=False
(선언 export는 있어야/추가 허용, 매니페스트 내부 추가 엣지 허용, 매니페스트 밖 import만 금지).
**발견2(핵심) — 합의 0.36**: 느슨 모드 재실행 3/11 게이트 통과(나머지=출력 안 함·고아 등 진짜 버그).
통과 3개도 거의 모든 시나리오에서 불일치. 원인 점검: SCN-001에서 attempt02 `gameStatus: undefined`(버그),
07 `levels:{}/productionRate:1`, 11 `gameStatus:PLAYING` — **무슨 key를 찍을지조차 제각각**. 즉 FROZEN
계약·Design·Spec QA를 다 거쳤어도 **출력 계약(정확한 key 집합·형식)이 안 박혀** 빌드가 안 모임.
**이게 합의 채점의 값**: 특권 golden 없이 "스펙이 아직 안 빡빡하다"를 정량화(0.36)+원인(출력계약 미고정) 지목.
다음: 출력 계약을 시나리오별 expected key 집합으로 못박기(Spec QA/계약 강화) → 그 뒤 합의 재측정.
Build v0(build.py)은 스파이크로 잔존. build_runs/는 gitignore.

## G34 — 한 변수 실험: 출력 계약 고정 → 합의 0.36→0.66 (2026-06-17, 키 씀)
build_graded 프롬프트에 **고정 출력계약**(정확히 4 key: turn/energy/productionRate/gameStatus, 같은 순서·
형식 + 상수는 시나리오 것 사용, 기본 gen1 명시) 추가. 한 변수만 바꿔 재측정(한 번에 한 변수 원칙).
결과: 게이트 3/11→**8/11**, 합의 0.36→**0.659**. → "계약을 빡빡하게 하면 싼 모델이 수렴한다" 방향 확인.
**단 정직 caveat — 0.66은 반쪽**: SCN-001 점검서 통과 8개가 둘로 갈림 — 절반 `turn:0`(액션 미실행),
절반 `turn:undefined`(파싱버그). WAIT 2회면 turn:2여야 하는데 **아무도 시나리오 액션을 실행 안 함**.
출력 key는 맞췄지만(→합의↑) **시나리오 입력 스키마(constants/initialState/actions가 이질적·일부 산문)가
미고정**이라 빌드가 입력을 못 읽음. 즉 합의 일부는 "기본값 우연 동의"=hollow.
다음 변수: **입력(시나리오) 스키마 고정** — scenarios.json 형식을 한 가지로 못박고 builds가 actions를
실제 실행하게 → 합의 재측정(진짜 수렴 보기). 이게 §11/§13 흐름상 Spec QA 강화 + Step6로 이어짐.

## G35 — 한 변수 실험: 입력 스키마 고정 → 합의 0.66→0.98 (2026-06-17, 키 씀)
G34의 반쪽 caveat(빌드가 actions 미실행) 원인 규명·제거. **원인 = 입력 스키마 미고정으로 액션 키 추측**:
시나리오 데이터는 `{"action":"WAIT"}`·`{"action":"UPGRADE","id":...}`인데 빌드 9개 전부 `action.type`/
`action.generatorId`를 읽음 → 어떤 액션도 매칭 안 됨 → turn:0 no-op에 다같이 모인 것이 0.66의 정체.
상수 키도 시나리오 `multiplier` vs 계약(RULE-03) `costMultiplier` 불일치.
**고친 것(한 변수=입력 스키마)**: build_graded 프롬프트에 INPUT CONTRACT 추가 — 액션 형식(verb=`action`,
gen=`id`, NOT type/generatorId), 상수 키(`costMultiplier`), 캐노니컬 디폴트(turn0/energy0/levels0/PLAYING,
productionRate는 입력서 안 받고 RULE-04로 도출). 시나리오 상수 multiplier→costMultiplier 통일(값 동일,
expected 불변). 출력계약·설계·모델은 G34 그대로 고정.
**결과**: 게이트 8/11→**9/11**, 합의 0.659→**0.98**. 그리고 **진짜 수렴 확인**(no-op 아님): SCN-001
turn2/energy6/productionRate6(업그레이드 실제 적용), SCN-002 "Insufficient energy"+energy0, SCN-007
turn2/energy2 — 전부 expected 일치. 액션이 실제로 돈다.
**남은 0.02 = 진짜 명세 구멍(no-op 잔재 아님)**: SCN-009/010만 합의 8/9로 갈림. 승리판정(RULE-05/06)
**타이밍** 미고정 — SCN-010(시작 energy1000+WAIT): 다수 빌드는 WAIT 먼저 적용(turn1/energy1001/WON),
expected는 시작 시점 WON→이후 액션 무시(turn0/energy1000). "액션 처리 전에 승리체크 하느냐"가 계약에
안 박힘. 이건 Step6 Adversarial QA / specqa가 메울 자리(RULE-05/06에 평가시점 명문화).
**결론**: 입력+출력 스키마 둘 다 못박으면 31B가 0.36→0.66→0.98로 거의 완전 수렴. "계약 빡빡→싼 모델
수렴" 방향 정량 확정. 다음 frontier = 명세의 평가시점 같은 엣지를 계약에 박는 것.
