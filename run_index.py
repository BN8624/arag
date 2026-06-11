"""런 메타데이터 인덱스: runs/index.json.

런이 끝날 때마다 한 줄 요약을 누적한다 (콜 0).
improve 모드(과거 런 조회), 적응형 난이도(최근 성적), 재발률 집계(실패 keyword)의
토대가 되는 데이터.

형식:
[
  {"run": "20260611-190509", "t": "...", "idea": "...", "status": "OK",
   "ok": true, "score": {"passed": 3, "total": 4},
   "calls": 18, "tokens": {...}, "cost_usd": 0.031,
   "fixes": {"static": 1, "exec": 2}, "critique_rounds": 1,
   "packages": ["openpyxl"], "failure_keywords": [...]}
]
"""

import json
import re
from pathlib import Path

MAX_ENTRIES = 1000  # 파일 비대 방지

# 어떤 실패에든 나오는 범용 단어 — 재발 판정에서 제외 (가짜 겹침 방지)
GENERIC_KEYWORD_TOKENS = {"cli", "tool", "python", "command", "line"}


def _keyword_tokens(keywords) -> set[str]:
    """키워드 목록 → 정규화된 토큰 집합.

    'data-processing'과 'data processing', 'cli tool'과 'cli'처럼 표기만 다른
    키워드가 어긋나지 않게 단어 단위로 쪼개 비교한다.
    """
    tokens: set[str] = set()
    for k in keywords or []:
        tokens |= set(re.findall(r"[0-9a-zA-Z가-힣]{2,}", str(k).lower()))
    return tokens - GENERIC_KEYWORD_TOKENS


def index_path(runs_dir: Path) -> Path:
    return Path(runs_dir) / "index.json"


def load_index(runs_dir: Path) -> list[dict]:
    path = index_path(runs_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def recurrence_stats(entries: list[dict]) -> dict:
    """오답노트 재발률 (콜 0).

    lesson이 주입된 런 중, 실패했고 실패 keyword가 주입 keyword와 겹치는 런 =
    "같은 실패 유형 재발". 배치가 쌓일수록 오답노트 효과의 공짜 증거가 된다.
    """
    injected = [e for e in entries if e.get("lessons_injected")]
    recurred = 0
    for e in injected:
        if e.get("ok"):
            continue
        failure = _keyword_tokens(e.get("failure_keywords"))
        inject = _keyword_tokens(e.get("lessons_injected"))
        if failure & inject:
            recurred += 1
    rate = round(recurred / len(injected), 3) if injected else None
    return {"injected_runs": len(injected), "recurred": recurred, "rate": rate}


def record_run(run_dir: Path, entry: dict) -> bool:
    """run_dir의 부모(runs/)에 있는 index.json에 entry를 추가.

    실패해도 회차 보고를 막지 않도록 예외를 내지 않는다.
    """
    try:
        run_dir = Path(run_dir)
        runs_dir = run_dir.parent
        entries = load_index(runs_dir)
        entries.append(entry)
        index_path(runs_dir).write_text(
            json.dumps(entries[-MAX_ENTRIES:], ensure_ascii=False, indent=2),
            encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001
        return False
