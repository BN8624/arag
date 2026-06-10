# arag — 생성기 (Generator)

아이디어 한 줄 → gemma 4 두 모델(26B 구현 / 31B 설계·비평)이
설계→구현→검증→비평 루프를 자동으로 돌아 **멀티파일 Python CLI 프로토타입**을 만든다.

> **주의: 민감한 아이디어를 입력하지 말 것.**
> 구글 AI Studio 무료 티어는 입력이 모델 개선에 쓰일 수 있다.

## 준비

1. `.env.example`을 `.env`로 복사하고 API 키를 넣는다.
2. `pip install -r requirements.txt`
3. `python config.py` → `[OK]` 확인
4. `python check_api.py` → 모델 연결·ID 확인
5. Docker Desktop 실행 (실행 게이트용. 없으면 `--skip-exec`로 생략 가능)

## 사용

```
python orchestrator.py "만들고 싶은 도구 아이디어 한 줄"
```

결과는 `runs/<날짜시간>/` 아래에:
- `workspace/` — 생성된 프로토타입 (git 스냅샷 포함)
- `REPORT.md` — 실행 방법, 수용기준, 비평 히스토리
- `design.json`, `events.jsonl` — 설계와 전체 이벤트 로그

## 테스트 (API 키 불필요)

```
python -m pytest tests -q
```

구조와 규칙은 [CLAUDE.md](CLAUDE.md) 참고.
