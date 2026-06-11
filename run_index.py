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
from pathlib import Path

MAX_ENTRIES = 1000  # 파일 비대 방지


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
