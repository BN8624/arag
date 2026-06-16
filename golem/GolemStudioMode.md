# Golem Studio Mode 제안서

## 11개 Gemma Worker Slot 기반 역할 순환형 가상 게임회사 구조

## 0. 배경

현재 `arag/golem` 서브프로젝트는 Gemma 계열 모델을 이용해 작은 JS 게임/룰 엔진을 자동 생성하고 검증하는 실험이다.

지금까지는 모델의 안정성을 너무 낮게 보고, 산출물을 지나치게 작게 제한한 경향이 있었다. 하지만 실제 실험에서는 Gemma4가 작은 범위의 게임 규칙 엔진을 매우 쉽게 생성하는 모습을 보였다.

따라서 다음 단계는 단순히 “작은 게임을 여러 개 만들기”가 아니라, **11개의 Gemma worker slot을 역할별 샘플링 슬롯처럼 운영해서 더 큰 산출물을 만들 수 있는지 검증하는 것**이다.

핵심 아이디어는 다음과 같다.

> 11개 worker slot을 독립 인격으로 간주하지 않고, 단계마다 기획팀·설계팀·개발팀·QA팀·통합팀으로 역할과 검토 관점을 바꿔가며 사용하는 “역할 순환형 가상 게임회사” 구조를 만든다.

이 구조를 임시로 **Golem Studio Mode**라고 부른다.

---

## 1. 목표

Golem Studio Mode의 목표는 다음이다.

1. Gemma4를 단순한 소형 코드 생성기로 쓰지 않고, 단계별 팀 작업자로 활용한다.
2. 11개 Auth Key를 11개의 병렬 샘플링 슬롯으로 묶어 사용한다.
3. 같은 11개 worker slot이 기획팀, 설계팀, 개발팀, QA팀, 통합팀으로 순환한다.
4. 각 팀은 `lead slot 1 + reviewer slot 10` 구조로 움직인다.
5. 팀 간 인수인계는 대화가 아니라 **계약 패킷 문서**로만 한다.
6. Claude의 역할은 직접 코딩이 아니라 총괄 감리, 계약 검토, 최종 승인으로 줄인다.
7. 최종적으로 Claude Code의 토큰 부담을 줄이고, Gemma 11개 슬롯을 하위 실무 샘플러처럼 활용한다.

---

## 2. 핵심 개념

### 2.1 역할 순환형 워커풀

기존 멀티에이전트 구조는 보통 역할이 고정된다.

예:

```text
기획자 1명
설계자 1명
개발자 5명
QA 3명
통합자 1명
```

하지만 Golem Studio Mode는 다르다.

```text
Round 1: 11개 worker slot = 기획팀
Round 2: 11개 worker slot = 설계팀
Round 3: 11개 worker slot = 개발팀
Round 4: 11개 worker slot = QA팀
Round 5: 11개 worker slot = 통합/수정팀
```

즉 11개 worker slot이 고정 인격이 아니라, 단계마다 책상을 옮기듯 다른 역할과 review_axis를 수행한다.

중요한 제한도 명시한다.

```text
11개 worker slot은 독립 인격이 아니다.
동일 프롬프트 10회 반복을 다양성으로 간주하지 않는다.
각 reviewer slot은 서로 다른 review_axis를 가져야 한다.
결과 리포트에는 duplicate_issue_rate와 unique_issue_count를 기록한다.
```

---

### 2.2 Lead 1 + Reviewer Slot 10 패턴

각 부서는 항상 같은 패턴으로 작동한다.

```text
1. lead slot 1개가 초안 작성
2. reviewer slot 10개가 서로 다른 review_axis로 독립 검토
3. lead slot은 10개의 의견을 통합
4. 통합 결과를 계약 패킷으로 고정
5. 다음 팀으로 전달
```

중요한 점은 reviewer slot들이 서로 대화하지 않는다는 것이다.
자유 토론을 시키면 비용이 커지고 산출물이 산으로 갈 수 있다.

따라서 구조는 “회의”가 아니라 **비동기 문서 리뷰**여야 한다.

예를 들어 기획 리뷰의 10개 축은 다음처럼 나눈다.

```text
Reviewer 1: 규칙 모호성만 찾기
Reviewer 2: 빠진 실패 케이스 찾기
Reviewer 3: 상태 객체에 반영 안 된 규칙 찾기
Reviewer 4: 테스트하기 어려운 규칙 찾기
Reviewer 5: 너무 복잡한 기능 찾기
Reviewer 6: 중복 규칙 찾기
Reviewer 7: 용어 충돌 찾기
Reviewer 8: 구현 난이도 위험 찾기
Reviewer 9: 범위 초과 기능 찾기
Reviewer 10: 다음 단계 인수인계 위험 찾기
```

---

## 3. 가장 중요한 원칙: 계약 모호성 제거

이 구조에서 제일 중요한 문제는 모델 체급이 아니라 **팀 간 계약의 모호성**이다.

기획팀이 만든 문서를 설계팀이 다르게 해석하고, 설계팀이 만든 manifest를 개발팀이 다르게 해석하면 실패한다.

따라서 팀에서 팀으로 넘어가기 전에 반드시 **Ambiguity Review**, 즉 모호성 사냥 단계를 넣어야 한다.

---

## 4. 계약 패킷 구조

팀 간 인수인계는 단일 `기획안.md`가 아니라, 다음과 같은 계약 패킷으로 해야 한다.

```text
HANDOFF_PACKET/
├─ 01_goal.md              # 이번 단계의 목표
├─ 02_decisions.md         # 이미 확정된 결정
├─ 03_terms.md             # 용어 정의
├─ 04_scope.md             # 포함/제외 범위
├─ 05_contract.json        # 다음 팀이 반드시 지켜야 할 기계적 계약
├─ 06_examples.md          # 맞는 예시 / 틀린 예시
├─ 07_acceptance_tests.md  # 통과 기준
└─ 08_questions.md         # BLOCKING / ASSUMED / DEFERRED 질문 분류
```

이 구조를 **Golem Contract Relay**라고 부른다.

핵심은 다음이다.

> 각 팀은 이전 팀의 최종 계약 패킷만 읽고 작업한다.
> 이전 논의 과정 전체를 읽지 않는다.
> 말이 아니라 파일이 기억 역할을 한다.

---

## 5. 팀 간 계약의 5종류

### 5.1 목표 계약

무엇을 만들지, 무엇을 만들지 않을지를 명확히 한다.

예:

```text
목표:
- 텍스트 기반 로그 출력 게임
- 타일 이동
- 적 전투
- 아이템 획득
- 환경 상호작용

비목표:
- 그래픽 렌더링 없음
- 실시간 입력 없음
- 랜덤 맵 생성 없음
- 외부 패키지 없음
- 네트워크 없음
```

작은 모델에게는 “해야 할 것”보다 “하지 말아야 할 것”이 매우 중요하다.

---

### 5.2 용어 계약

같은 단어를 모든 팀이 같은 의미로 쓰도록 한다.

예:

```text
turn: 플레이어 명령 1개가 처리된 횟수
tick: 현재 사용하지 않음
enemy: hp, x, y, type을 가진 객체
blocked tile: player와 enemy가 이동할 수 없는 타일
hazard tile: 이동은 가능하지만 효과가 발생하는 타일
```

---

### 5.3 데이터 계약

게임 상태 객체의 구조를 고정한다.

예:

```json
{
  "turn": 0,
  "player": {
    "x": 1,
    "y": 1,
    "hp": 5,
    "inventory": []
  },
  "enemies": [
    {
      "id": "e1",
      "type": "slime",
      "x": 3,
      "y": 1,
      "hp": 2
    }
  ],
  "tiles": [
    {
      "x": 2,
      "y": 2,
      "type": "fire"
    }
  ],
  "log": []
}
```

개발팀은 이 구조를 임의로 바꾸면 안 된다.
계약 의미 변경이 필요하면 `CHANGE_REQUEST.md`를 만들어야 한다.

---

### 5.4 인터페이스 계약

각 모듈의 파일명, export, import를 고정한다.

예:

```json
{
  "files": {
    "state.js": {
      "exports": ["createInitialState", "cloneState"]
    },
    "movement.js": {
      "exports": ["applyMove"],
      "imports": ["state.js"]
    },
    "combat.js": {
      "exports": ["applyAttack"],
      "imports": ["state.js"]
    },
    "engine.js": {
      "exports": ["runCommand", "runScenario"],
      "imports": ["movement.js", "combat.js"]
    }
  }
}
```

이렇게 해야 개발팀이 `movePlayer`, `doMove`, `handleMovement`처럼 제각각 함수명을 만들지 않는다.

---

### 5.5 테스트 계약

규칙은 반드시 예상 결과와 함께 있어야 한다.

예:

```text
Scenario: wall_block

초기 상태:
- player at (1,1)
- wall at (2,1)

입력:
- MOVE_EAST

기대 결과:
- player remains at (1,1)
- turn increases by 1
- log contains "BLOCKED"
```

말로 된 규칙만 있으면 안 된다.
반드시 테스트 가능한 형태여야 한다.

---

## 6. Ambiguity Review

다음 팀으로 넘기기 전에 reviewer slot 10개는 구현이나 아이디어 추가를 하지 않는다.
오직 모호한 부분만 찾는다.

출력 형식은 JSON으로 제한한다.

```json
{
  "ambiguous_terms": [],
  "missing_rules": [],
  "conflicting_rules": [],
  "underspecified_outputs": [],
  "risky_assumptions": [],
  "questions_for_lead": []
}
```

lead slot은 이 10개의 리뷰를 받아 계약 패킷을 수정한다.

질문은 0개가 아니어도 된다.
대신 모든 질문은 다음 세 종류로 분류되어야 한다.

```text
BLOCKING: 다음 단계로 넘어가면 안 되는 질문
ASSUMED: 명시적 가정으로 고정하고 진행하는 질문
DEFERRED: 후속 버전으로 미루는 질문
```

완료 조건은 다음이다.

```text
BLOCKING questions = 0
ASSUMED questions는 assumptions.md에 기록
DEFERRED questions는 backlog.md에 기록
```

수정 후 반드시 다음 상태를 선언한다.

```text
CONTRACT_STATUS: FROZEN
```

계약이 FROZEN된 뒤에는 다음 팀이 임의로 계약을 바꿀 수 없다.
다만 변경은 다음 등급으로 나누어 처리한다.

```text
L0: 문서/포맷 수정
- 오타, 설명 보강, 파일 정리
- 승인 없이 가능

L1: 명명/경로 수정
- 함수명, 파일명, export 이름 정정
- validator 통과 조건이면 가능

L2: 테스트 보강
- 기존 계약 의미를 바꾸지 않는 테스트 추가
- QA 단계에서 가능

L3: 계약 의미 변경
- 규칙, 상태 구조, 모듈 책임 변경
- CHANGE_REQUEST.md 필요

L4: 범위 변경
- 기능 추가/삭제, 게임 목표 변경
- lead slot 또는 Claude 감리 승인 필요
```

---

## 7. Traceability JSON

기획 요구사항이 설계, 코드, 테스트와 어떻게 연결되는지 추적해야 한다.
정본은 Markdown이 아니라 JSON이어야 한다.

예:

```json
{
  "REQ-001": {
    "text": "플레이어는 북/남/동/서 이동 가능",
    "design_modules": ["movement.js"],
    "exports": ["applyMove"],
    "tests": ["SCN-001", "SCN-002"],
    "status": "covered"
  },
  "REQ-002": {
    "text": "벽으로 이동하면 위치는 변하지 않는다",
    "design_modules": ["movement.js"],
    "exports": ["applyMove"],
    "tests": ["SCN-003"],
    "status": "covered"
  }
}
```

validator는 다음을 확인해야 한다.

```text
- 모든 REQ가 최소 1개 module에 연결됨
- 모든 REQ가 최소 1개 test에 연결됨
- manifest에 없는 파일이 trace에 나오면 실패
- 존재하지 않는 test id가 trace에 나오면 실패
```

사람이 읽는 `traceability_report.md`는 JSON에서 생성되는 보조 문서로 둔다.

---

## 8. Definition of Done

각 팀은 완료 기준을 가져야 한다.

### 8.1 기획팀 완료 기준

```text
- 핵심 루프가 명확함
- 플레이어 행동 목록이 있음
- 적/아이템/타일/승패 조건이 정의됨
- 비목표가 명확함
- 모호성 리뷰 완료
- BLOCKING questions가 0개
- ASSUMED questions가 assumptions.md에 기록됨
- DEFERRED questions가 backlog.md에 기록됨
```

### 8.2 설계팀 완료 기준

```text
- 모든 REQ가 하나 이상의 모듈에 배정됨
- 모든 모듈이 파일명과 exports를 가짐
- 순환 의존성 없음
- 테스트되지 않는 REQ 없음
- module_manifest.json 존재
- traceability.json 존재
- traceability_report.md는 traceability.json에서 생성됨
- BLOCKING questions가 0개
```

### 8.3 개발팀 완료 기준

```text
- 모든 manifest 파일 존재
- 모든 export 이름 일치
- node --check 통과
- static_gate 통과
- 외부 패키지 없음
- Math.random 없음
- acceptance_tests 통과
```

### 8.4 Spec QA 완료 기준

```text
- 기획/설계 문서가 테스트 가능한 표현을 가짐
- acceptance_tests 초안 존재
- expected output이 모호한 시나리오가 표시됨
- 각 REQ에 최소 1개 테스트 후보 연결
- TEST_ORACLE_ERROR 위험이 분리됨
```

### 8.5 Adversarial QA 완료 기준

```text
- 정상 시나리오 존재
- 실패 시나리오 존재
- 경계 조건 시나리오 존재
- 각 REQ에 최소 1개 테스트 연결
- golden output이 명확함
- 구현을 깨는 edge_cases.json 존재
```

---

## 9. 산출물 크기를 키우는 방법

Gemma4에게 단순히 “크게 만들어라”라고 하면 안 된다.
대신 각 단계마다 최소 산출물 예산을 줘야 한다.

### 9.1 기획팀 산출물 깊이 조건

```text
- 핵심 루프 1개
- 각 플레이어 행동은 입력, 상태 변화, 실패 케이스, 로그 출력, 테스트 후보를 가짐
- 각 적 타입은 이동 규칙, 공격 규칙, HP/피해량, 지형 상호작용, 사망 시 효과 중 최소 2개 이상에서 차이를 가짐
- 각 아이템은 획득 조건, 상태 변화, 실패 케이스, 로그 출력, 최소 1개 테스트 시나리오를 가짐
- 각 타일은 진입 가능 여부, 효과 발동 시점, 로그 출력, 최소 1개 테스트 시나리오를 가짐
- 실패/예외 상황은 관련 REQ와 연결됨
```

### 9.2 설계팀 산출물 깊이 조건

```text
- 각 모듈은 책임, 입력, 출력, 금지 책임을 가짐
- 각 export 함수는 호출자, 입력 schema, 반환 schema, 실패 케이스를 가짐
- 상태 객체 schema 정의
- 이벤트 타입은 발생 조건과 소비 모듈을 가짐
- 금지된 의존성 명시
- 각 모듈별 테스트 포인트가 REQ와 연결됨
```

### 9.3 개발팀 산출물 깊이 조건

```text
- main.js 포함
- manifest에 정의된 src 모듈 포함
- 테스트 가능한 순수 함수 중심
- 외부 패키지 금지
- Math.random 금지
- 모든 명령은 deterministic
- 각 export는 manifest의 이름과 일치
```

산출물을 키우는 방식은 “프롬프트에 크게 만들라고 쓰기”가 아니라 **최소 산출물 계약을 명시하는 것**이다.

---

## 10. 확장 래칫

한 번 통과한 기능은 기본적으로 다음 버전에서 유지한다.
이를 **확장 래칫**으로 관리한다.

예:

```text
Golem Studio v0
- 이동
- 벽
- 로그
- 5개 시나리오

Golem Studio v1
- 적
- 공격
- HP
- 10개 시나리오

Golem Studio v2
- 아이템
- 인벤토리
- 효과
- 15개 시나리오

Golem Studio v3
- 환경 타일
- 상태 이상
- 연쇄 효과
- 20개 시나리오

Golem Studio v4
- 퀘스트
- 승패 조건
- 스코어
- 30개 시나리오
```

v2에서 아이템이 들어갔다면 v3에서 아이템이 사라지면 안 된다.
다만 잘못 만든 기능까지 무조건 끌고 가면 안 된다.
아래 조건 중 하나에 해당하면 제거나 축소가 가능하다.

```text
1. 해당 기능이 2회 이상 연속으로 통합 실패를 유발
2. 테스트 대비 구현 복잡도가 과도함
3. 다른 핵심 기능과 계약 충돌 발생
4. 현재 목표 버전의 scope를 벗어남
5. QA가 유지 비용이 크다고 판정
```

제거 시 `DEPRECATION_REQUEST.md`를 작성한다.
래칫은 무조건 쌓기가 아니라, 성공한 기능은 유지하되 실패한 기능은 근거를 남기고 제거할 수 있는 구조다.

---

## 11. 제안하는 Golem Studio Mode 파이프라인

```text
Stage 1: Planning
- concept.md
- gdd.md
- ambiguity_review.json

Stage 2: Design
- system_design.md
- module_manifest.json
- traceability.json

Stage 3: Spec QA
- acceptance_tests_draft.json
- oracle_risk_review.json

Stage 4: Build
- src/*.js
- implementation_notes.md

Stage 5: Adversarial QA
- acceptance_tests.json
- edge_cases.json

Stage 6: Integration
- final workspace
- static_gate_result.json
- grade_result.json
- final_report.md
```

처음부터 전부 구현하지 말고, 1차 구현은 다음만 해도 된다.

```text
Planning → Design → Spec QA → Build → Adversarial QA → Integration
```

---

## 12. 추천 폴더 구조

```text
golem/
  studio/
    roles/
      executive.md
      planning_lead.md
      planning_reviewer.md
      design_lead.md
      design_reviewer.md
      dev_lead.md
      dev_reviewer.md
      qa_lead.md
      qa_reviewer.md
      integration_lead.md

    stages/
      01_planning.yaml
      02_design.yaml
      03_spec_qa.yaml
      04_build.yaml
      05_adversarial_qa.yaml
      06_integration.yaml

    schemas/
      contract_packet.schema.json
      module_manifest.schema.json
      ambiguity_review.schema.json
      traceability.schema.json
      acceptance_tests.schema.json

    artifacts/
      concept.md
      gdd.md
      system_design.md
      module_manifest.json
      traceability.json
      traceability_report.md
      acceptance_tests_draft.json
      acceptance_tests.json
      final_report.md

    runs/
      <timestamp>/
        planning/
        design/
        spec_qa/
        build/
        adversarial_qa/
        integration/
        report.md
```

---

## 13. 구현 우선순위

바로 LLM 병렬 실행부터 만들면 안 된다.
먼저 계약 패킷과 검증기를 만들어야 한다.

### Step 1: Contract Microkernel Replay

실제 API 호출 없이 fake output으로만 검증한다.
이 단계는 Golem Studio 전체가 아니라 계약 검증 마이크로커널만 만든다.

작업:

```text
1. fake_planning_packet.json 작성
2. module_manifest.schema.json 작성
3. fake src/*.js build output 추가
4. import/export validator 작성
5. static_gate bridge 연결
6. replay_result.json 생성
7. contract_validation_report.md 생성
```

이 단계에서는 Gemini/Gemma API 호출 금지.
목표는 게임 생성이 아니라 manifest에 적힌 파일, export, import와 실제 코드가 일치하는지 기계적으로 검증하는 것이다.

---

### Step 2: Planning 팀만 Gemma로 실행

처음에는 기획팀만 실제 worker slot을 사용한다.

```text
- planning_lead 1회
- planning_reviewer 3회 또는 10회
- 선택한 reviewer 수만큼 ambiguity review 생성
- planning_lead synthesis 1회
- contract_packet 생성
```

성공 기준:

```text
- BLOCKING questions가 0개
- concept.md 생성
- gdd.md 생성
- ambiguity_review.json 생성
- contract_packet 검증 통과
```

---

### Step 3: Design 팀 실행

Planning 산출물을 입력으로 받아 설계팀을 실행한다.

성공 기준:

```text
- module_manifest.json 생성
- traceability.json 생성
- traceability_report.md 생성
- 모든 REQ가 모듈에 연결됨
- 모든 REQ가 테스트 후보에 연결됨
- 순환 의존성 없음
- BLOCKING questions가 0개
```

---

### Step 4: Spec QA 팀 실행

Design 산출물을 입력으로 받아 테스트 가능한 계약인지 먼저 검토한다.

성공 기준:

```text
- acceptance_tests_draft.json 생성
- oracle_risk_review.json 생성
- 모든 REQ가 최소 1개 테스트 후보에 연결됨
- expected output이 모호한 시나리오가 표시됨
- BLOCKING questions가 0개
```

---

### Step 5: Build 팀 실행

Design 산출물을 입력으로 받아 모듈별 구현을 수행한다.

성공 기준:

```text
- manifest에 정의된 모든 파일 존재
- export/import 일치
- node --check 통과
- static_gate 통과
- grade 통과
```

---

### Step 6: Adversarial QA 팀 실행

Adversarial QA팀은 구현을 새로 하지 않는다.
오직 깨질 만한 케이스를 만든다.

성공 기준:

```text
- acceptance_tests.json 생성
- edge_cases.json 생성
- 각 REQ별 최소 1개 테스트 존재
- 실패 케이스가 명확한 expected output을 가짐
```

---

## 14. Claude의 역할

초기에는 Claude가 lead slot 역할을 일부 맡아도 된다.

하지만 최종 목표는 다음이다.

```text
Gemma key 1 = lead slot
Gemma key 2~11 = reviewer slot
Claude = 총괄 감리 / 최종 승인 / 실패 원인 판단
```

Claude가 직접 코드를 많이 쓰면 이 구조의 의미가 줄어든다.
Claude는 가능한 한 다음에 집중해야 한다.

```text
- 계약 패킷이 모호하지 않은지 검토
- 게이트 실패 원인 판단
- 잘못된 단계로 롤백
- 다음 실험 방향 결정
- 위험한 구조 변경 차단
```

---

## 15. 측정 지표

기존의 `11/11 통과`만으로는 부족하다.

Golem Studio Mode에서는 다음을 기록해야 한다.

```text
- stage별 성공률
- ambiguity 개수
- BLOCKING / ASSUMED / DEFERRED questions 개수
- contract freeze까지 걸린 호출 수
- manifest 검증 실패 수
- import/export mismatch 수
- static_gate 실패 원인
- grade 실패 원인
- Claude가 직접 수정한 코드 줄 수
- Claude 토큰 사용량
- Gemma 토큰 사용량
- 최종 산출물 파일 수
- 최종 테스트 수
- 이전 버전 대비 기능 증가량
- duplicate_issue_rate
- unique_issue_count
- accepted_review_count
- contract_validation_failure_count
- build_failure_count
- final_pass_rate
- latency
```

핵심 지표는 단순히 Gemma 통과율이 아니라:

```text
Claude touch 감소량
계약 모호성 감소량
산출물 복잡도 증가량
```

이다.

11개 슬롯 효과는 반드시 비교군으로 측정한다.

```text
A안: single Gemma
- planning → design → build를 단일 Gemma가 수행

B안: 1 lead + 3 reviewers
- lead 초안
- reviewer 3개 축
- lead synthesis

C안: 1 lead + 10 reviewers
- lead 초안
- reviewer 10개 축
- lead synthesis
```

C안이 B안보다 unique issue를 충분히 늘리지 못하면 10 reviewers를 기본값으로 쓰지 않는다.
기본값은 3 reviewers로 두고, 위험 단계나 실패 반복 단계에서만 10 reviewers로 승격한다.

---

## 16. 실패 분류와 롤백 기준

실패했을 때 Claude가 감으로 판단하면 다시 Claude touch가 늘어난다.
따라서 실패는 다음처럼 분류하고 롤백 위치를 정한다.

```text
SPEC_AMBIGUITY
- 요구사항이 서로 다르게 해석 가능
- Planning 또는 Design으로 롤백

MANIFEST_MISMATCH
- 파일명/export/import 불일치
- Design으로 롤백

IMPLEMENTATION_BUG
- 계약은 맞는데 코드 동작이 틀림
- Build로 롤백

TEST_ORACLE_ERROR
- 테스트 기대값이 계약과 다름
- Spec QA로 롤백

INTEGRATION_ERROR
- 개별 모듈은 맞지만 조립 실패
- Integration 또는 Design으로 롤백

SCOPE_BLOAT
- 기능이 너무 많아져 핵심 목표 실패
- Planning으로 롤백하거나 DEPRECATION_REQUEST.md 생성
```

---

## 17. 주의할 실패 패턴

### 17.1 회의가 길어지는 문제

11개 slot이 서로 대화하면 비용이 폭발한다.
반드시 독립 리뷰 후 lead slot이 통합하는 구조여야 한다.

### 17.2 그럴듯한 말만 많고 결정이 없는 문제

모든 단계는 파일 산출물로 종료해야 한다.
다음 단계는 대화 로그가 아니라 최종 파일만 읽어야 한다.

### 17.3 계약 변경 남발

다음 팀이 이전 팀의 결정을 계속 바꾸면 시스템이 무너진다.
계약 의미 변경은 반드시 `CHANGE_REQUEST.md`로 처리한다.
단, L0~L2 변경은 validator와 단계 규칙 안에서 빠르게 처리한다.

### 17.4 산출물 축소

모델이 안전하게 가려고 이전보다 작은 게임을 만들 수 있다.
이를 막기 위해 확장 래칫과 산출물 깊이 조건이 필요하다.

### 17.5 테스트 없는 요구사항

모든 요구사항은 최소 하나의 테스트와 연결되어야 한다.

---

## 18. 최종 요청

Claude는 현재 `arag/golem` 구조를 확인한 뒤, 바로 대규모 구현에 들어가지 말고 다음 순서로 진행해라.

1. 기존 golem 구조를 깨지 말 것.
2. `golem/studio/` 하위에 Golem Studio Mode를 별도 실험 모드로 추가할 것.
3. 먼저 Contract Microkernel Replay부터 만들 것.
4. 실제 Gemini/Gemma API 호출은 Step 1에서 금지할 것.
5. module manifest schema, import/export validator, fake artifacts, static_gate bridge, replay report를 먼저 만들 것.
6. replay가 통과한 뒤 Planning 팀만 실제 호출하는 Step 2로 넘어갈 것.
7. 모든 단계 산출물은 파일로 저장할 것.
8. 다음 단계는 이전 단계의 최종 계약 패킷만 읽게 할 것.
9. Claude가 직접 코드를 많이 쓰는 구조가 아니라, Gemma worker slots가 역할 순환하며 산출물을 키우는 구조를 목표로 할 것.

---

## 19. 한 줄 요약

Golem Studio Mode는 다음 구조다.

> 11개의 Gemma Auth Key를 독립 인격이 아니라 역할별 병렬 샘플링 슬롯으로 순환 배치하고, 팀 간 인수인계는 계약 패킷으로 고정하여, 작은 모델들이 모호성 없이 큰 산출물을 단계적으로 만들어가게 하는 역할 순환형 가상 게임회사 구조.

우선 구현 목표는 다음이다.

> `Contract Microkernel Replay + manifest validation + import/export validator + fake build output + static gate bridge`

이게 통과한 뒤에만 실제 worker slots를 투입한다.
