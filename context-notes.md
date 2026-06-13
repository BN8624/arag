# context-notes.md — PLAN 2 결정 로그

> 작업 중 내린 결정과 그 이유. 계속 append. 다음 세션이 재유도 없이 이어가게.
> 명세 = [PLAN.md](PLAN.md), 체크리스트 = [checklist.md](checklist.md).

## 2026-06-13 — 방향 대전환: 벤치마크 → 프로토타입 측정

### 왜 갈아엎었나
B2 캠페인(8장)을 복구·완주한 뒤 데이터를 점검하다 측정 자체가 못 미더운 걸 발견.
- 격리 깨짐: worktree 학습파일이 비어있지 않아(lessons 2, critique 2) 카드 독립성 붕괴.
  모든 런에 "lessons injected" 찍힘 → 1번 카드와 41번 카드가 다른 조건.
- 표본 n=1: "L3부터 붕괴"의 근거가 MODEL_LIMIT 단 1건. 일화지 데이터 아님.
- 인프라 노이즈 42%, 매 세션 프롬프트 변경으로 분모가 계속 갈림.

### 결정 1 — 엔진은 유지, 측정만 리셋
엔진(오케스트레이터·게이트·observability)은 멀쩡(테스트 265 통과). 문제는 데이터.
→ 처음부터 재작성 거부. `_exploration/20260613/`로 기존 데이터 격리(삭제 아님,
엔진 디버깅엔 가치). worktree clean slate.

### 결정 2 — 엄밀 벤치마크 descope
파일수/계약수/도메인/oracle강도 축 + m×k 격자 + synthetic grid 설계를 논의했으나
"도구가 목적을 잡아먹는다"고 판단. ARAG의 원래 목표는 **프로토타입 생성기**지
벤치마크 연구가 아님. 무거운 측정 설계는 **보류**(폐기 아님).

### 결정 3 — 핵심 측정 = cold vs warm
같은 카드/모델/예산/프롬프트에서 노트 유무만 변경 → 오답노트/비평노트 효과 측정.
이게 ARAG의 "누적 학습이 저가 모델을 끌어올리나"라는 진짜 질문에 정렬.

### 결정 4 — 카드풀 = 게임/앱 6개
사용자(바이브코더)가 결과를 눈으로 판단 가능하고 흥미로운 주제로. 업무자동화
카드(CSV/영수증/로그)는 주 카드에서 제외. 6개: 숫자야구 / 퀴즈+JSON / 가위바위보리그 /
미니상점 / 아이템강화 / 자동전투RPG. 덱빌딩·방치형은 L3 확장으로 보류.

### 결정 5 — 첫 단계는 셰이크다운 12런
결론이 아니라 **장치 검증**. 6카드 × cold/warm × 1회. 깨끗한 라벨·비용·요약이
나오는지부터 확인하고 규모를 키운다.

### 코드 사실 (확인됨)
- 단발 런 노트 주입 지점은 **2곳뿐**: `phase_design._load_lessons`(lessons),
  `phase_implement._load_notes`(critique_notes). evaluator_mistakes는 배치 경로
  (`analyze_batch.harvest`)에서만 수확 → 단발 런 cold mode는 이 2곳만 끄면 됨.
- 측정·코드 실행은 격리 worktree `../arag-bank`(브랜치 bank-b2-env). 카드 저장소는
  `bank_*.py` + `design_bank.sqlite` 재사용.

### 결정 6 — warm 순서 확정 + 셰이크다운 성격 명시
순서: cold 6런(노트 OFF, 후보 수확) → 수확 노트 USE/HOLD/DROP 분류 → USE만 warm
적재 → warm 6런(노트 ON, 같은 카드 재시도). **이 셰이크다운은 노트 효과의 정식
측정이 아니라 파이프라인 검증.** same-card warm은 자기참조 편향이 있어 효과가
과대평가됨 → 정식 일반화 측정은 캠페인2(cross-card warm)로 분리.

### 결정 7 — warm 노트 품질 필터(USE/HOLD/DROP)
cold 실패를 아무거나 넣으면 잘못된 비평·과적합 패치·틀린 원인분석이 warm을 오염.
적재 전 3종 분류(기계 자동 → 폰 감사 변경 가능). USE만 주입.

### 결정 8 — 점수 2단계 + fingerprint 가볍게
점수는 *_auto(기계)/*_user(사람)로 분리, human_audit_status로 상태 추적.
protocol_version은 앵커, protocol_fingerprint는 조건을 펼친 객체(해시 시스템 X —
산으로 안 가게. 나중에 접으면 됨).

## 미해결 (다음 세션이 먼저 답할 것)
- temperature 고정값(추천 0.2) + AI Studio gemma의 temperature/seed 지원 여부(코드 확인).
- prototype_score_auto / failure_usefulness_auto 기계 산출 규칙(observability 재사용).
