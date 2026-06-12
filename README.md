# arag — 생성기 (Generator)

아이디어 한 줄 → gemma 4 두 모델(**26B 구현 / 31B 설계·출제·비평**)이
설계→구현→검증→비평 루프를 자동으로 돌아 **멀티파일 Python CLI 프로토타입**을 만든다.

정확히는 "자동 개발기"가 아니라, **작은 모델이 멀티파일 프로토타입을 만들 때
어디서 어떻게 실패하는지 기록하고, 그 실패를 다음 루프의 제약으로 바꾸는 실험 하네스**다.
LLM이 틀린다는 걸 기본값으로 놓고 설계되어 있다: 정적 게이트(콜 0) → Docker 실행
게이트 → 채점표 → 비평, 층마다 자가수정 상한·진전 없음 감지·스냅샷/롤백.

> **주의: 민감한 아이디어를 입력하지 말 것.**
> 구글 AI Studio 무료 티어는 입력이 모델 개선에 쓰일 수 있다.

## 구조

```
orchestrator.py      루프 흐름 + 가드레일 + 스냅샷 (단계 로직은 phase_*로 분해)
  phase_design.py      [31B] 설계 생성/검증      phase_tests.py     [31B] 시험지 출제/수리
  phase_implement.py   [26B] 파일별 구현          phase_gates.py     게이트 + 자가수정 + 중재
  phase_critique.py    [31B] 품질심사 + 롤백      phase_improve.py   성공 런 개선
  reporting.py         README/REPORT/생산 장부    phase_common.py    공통 상수
gates.py             정적 게이트 (ast 기반, 콜 0)
docker_gate.py       실행 게이트 (Docker: 네트워크 차단, 타임아웃, stdin 차단)
design_validator.py  설계 JSON 검증 (멀티파일·순환참조·계약)
batch.py             배치 모드 (개선→총평→신규 생산 우선순위 루프 + 자가 정지)
idea_factory.py      [31B] 아이디어 출제 (GitHub 주제 기반, 적응형 난이도)
dashboard.py         폰 관제 대시보드 (읽기 전용 + 시작/종료예약 버튼)
reviewer.py          만점 런의 사용자 시점 총평 (31B 블랙박스 1콜)
lessons.py           오답노트(실패→설계 주입)   critique_notes.py  비평노트(검증된 비평→구현 주입)
evaluator_notes.py   평가자 실수 수집 (31B 교정 자료)
analyze_batch.py     배치 결과 분석 (콜 0)      llm.py            콜 래퍼 (간격·재시도·녹음·비용)
```

## 준비

1. `.env.example`을 `.env`로 복사하고 API 키를 넣는다.
2. `pip install -r requirements.txt`
3. `python config.py` → `[OK]` 확인
4. `python check_api.py` → 모델 연결·ID 확인
5. Docker Desktop 실행 (실행 게이트용. 없으면 자동으로 `--skip-exec` 동작)

## 실행 모드

```bash
# 단일 생산: 아이디어 하나 → 프로토타입 하나
python orchestrator.py "만들고 싶은 도구 아이디어 한 줄"

# 개선: 성공한 런을 더 좋게 (기존 기준은 회귀 방지선으로 보존)
python orchestrator.py --improve runs/<런이름> --feedback "고칠 점" "원래 아이디어"

# 배치: 출제→생산→총평→개선을 연속 운영 (회차 사이 종료예약 확인, 자가 정지 포함)
python batch.py --runs 10

# 대시보드: 폰에서 보는 공장 관제 화면 (Tailscale 등 사설망 IP로 접속)
python dashboard.py            # http://<PC IP>:8400

# 분석: 배치 결과 집계 (콜 0, 배치 도는 중에도 안전)
python analyze_batch.py

# 리플레이: 녹음된 LLM 응답으로 루프 재현 (API 콜 0 — 디버깅·리팩토링 검증용)
python orchestrator.py --replay runs/<런이름> --no-retry "원래 아이디어"

# API 장애 복구 감시: 26B가 살아나면 배치 자동 시작
python watch_resume.py --runs 20
```

## 결과물 읽는 법

런마다 `runs/<날짜시간>/` 아래에:
- `workspace/` — 생성된 프로토타입 (git 스냅샷 포함, README·pyproject 동봉)
- `REPORT.md` — 실행 방법, 수용기준 채점표, 비평 히스토리, 비용
- `design.json` / `events.jsonl` / `llm_calls.jsonl` — 설계·이벤트·콜 녹음
- `runs/index.json` — 전체 런 장부 (점수, 비용, 수리 횟수, 프롬프트 버전)

상태 라벨:
- `OK` — 게이트·채점표 전부 통과
- `OK (partial - ...)` — **불완전하지만 건질 수 있음**: 성공 신호는 통과,
  수용기준 일부 미달. 떨어진 기준은 장부에 남아 다음 배치의 자동 개선 표적이 된다
- `OK (salvaged ...)` — 도중 중단됐지만 마지막 게이트 통과본으로 출하
- `ABORTED` — 가드레일 발동 (자가수정 한도, 진전 없음, 시간 초과)
- `ERROR` — 인프라 장애 (API 5xx 등. 모델 실력과 무관)

## 비용·쿼터

- 무료 티어 기준 모델별 RPM 15 / RPD 1,500. 콜 래퍼가 4초 간격과 429 백오프를 강제
- 런당 콜 상한(기본 60)·시간 상한(기본 40분)·배치 회차 상한(최대 20)
- 비용은 유료 환산 추정치로 REPORT와 장부에 기록 (실측 런당 $0.005~0.05)

## 보안 주의사항

- **이 프로젝트는 신뢰할 수 없는 LLM 생성 코드를 Docker 안에서 실행하지만,
  완전한 보안 샌드박스는 아니다.** 민감한 파일이 있는 디렉터리를 마운트하지 말 것
- **대시보드를 외부 인터넷에 직접 노출하지 말 것** — 인증이 없다.
  Tailscale 같은 사설망 안에서만 쓸 것
- 의존성 설치는 화이트리스트 패키지만 허용되지만 공급망 위험이 0은 아니다

## 테스트 (API 키·Docker 불필요)

```bash
python -m pytest tests -q
```

전부 콜 0으로 도는 단위·모킹 테스트다. 루프 전체의 동작 검증은 `--replay`로
녹음된 런을 재현해서 한다.

## 현재 한계

- Python CLI 프로토타입 고정 (웹앱·라이브러리 미지원)
- gemma 4 26B/31B 조합 고정 — 다른 모델 조합에서의 역할 분리 효과는 미검증
- 단일 PC 운영 전제 (CI 없음, 런타임 상태 JSON을 저장소에 커밋하는 개인 프로젝트 방식)

구조와 규칙은 [CLAUDE.md](CLAUDE.md), 진행 기록은 [Progress.md](Progress.md) 참고.
