# Design Bank SQLite 저장소: task_card CRUD + 중복 감지 (콜 0)
"""design_bank.sqlite 단일 파일 저장소.

테이블(PLAN §2.4): tasks / task_tags / expected_failure_modes / task_reviews.
run_results는 runs/index.json 파생 뷰이므로 B0에선 만들지 않는다(정본 충돌 방지).

중복 감지: goal 정규화 해시(정확 중복) + 제목 difflib 유사도(근사 중복).
insert_task가 거부하고 사유를 DuplicateTask로 던진다.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from bank_schema import SCHEMA_VERSION, normalize_goal, validate_card

DEFAULT_DB = Path(__file__).resolve().parent / "design_bank.sqlite"

TITLE_SIMILARITY_THRESHOLD = 0.85

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id              TEXT PRIMARY KEY,
    source_model         TEXT NOT NULL,
    title                TEXT NOT NULL,
    goal                 TEXT NOT NULL,
    goal_hash            TEXT NOT NULL,
    difficulty_level     INTEGER NOT NULL,
    task_json            TEXT NOT NULL,
    design_quality_score REAL,
    created_at           TEXT NOT NULL,
    schema_version       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_goal_hash ON tasks(goal_hash);
CREATE TABLE IF NOT EXISTS task_tags (
    task_id TEXT NOT NULL,
    tag     TEXT NOT NULL,
    PRIMARY KEY (task_id, tag)
);
CREATE TABLE IF NOT EXISTS expected_failure_modes (
    task_id      TEXT NOT NULL,
    failure_mode TEXT NOT NULL,
    PRIMARY KEY (task_id, failure_mode)
);
CREATE TABLE IF NOT EXISTS task_reviews (
    review_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id                TEXT NOT NULL,
    reviewer_model         TEXT NOT NULL,
    review_json            TEXT NOT NULL,
    revised_difficulty_level INTEGER,
    design_quality_score   REAL,
    created_at             TEXT NOT NULL
);
"""


class DuplicateTask(Exception):
    """중복 과제 삽입 시도."""


class InvalidCard(Exception):
    """스키마/어휘 검증 실패. errors 리스트를 담는다."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _goal_hash(goal: str) -> str:
    norm = normalize_goal(goal)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class BankDB:
    """design_bank.sqlite 핸들. 컨텍스트 매니저 또는 직접 close()."""

    def __init__(self, path: Path | str = DEFAULT_DB):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def __enter__(self) -> "BankDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def _next_task_id(self) -> str:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()
        return f"T-{row['n'] + 1:06d}"

    def _find_duplicate(self, goal: str, title: str) -> str | None:
        """중복이면 사유 문자열, 아니면 None."""
        gh = _goal_hash(goal)
        exact = self.conn.execute(
            "SELECT task_id FROM tasks WHERE goal_hash = ?", (gh,)
        ).fetchone()
        if exact:
            return f"goal duplicates {exact['task_id']}"
        norm_title = title.lower().strip()
        for row in self.conn.execute("SELECT task_id, title FROM tasks"):
            ratio = SequenceMatcher(
                None, norm_title, row["title"].lower().strip()
            ).ratio()
            if ratio >= TITLE_SIMILARITY_THRESHOLD:
                return (f"title ~{ratio:.2f} similar to {row['task_id']} "
                        f"({row['title']!r})")
        return None

    def insert_task(self, card: dict) -> str:
        """카드 검증 → 중복 확인 → 저장. task_id 반환.

        실패 시 InvalidCard / DuplicateTask. task_id·created_at·schema_version은
        여기서 채운다.
        """
        errors = validate_card(card)
        if errors:
            raise InvalidCard(errors)

        dup = self._find_duplicate(card["goal"], card["title"])
        if dup:
            raise DuplicateTask(dup)

        task_id = self._next_task_id()
        created_at = _now()
        stored = dict(card)
        stored["task_id"] = task_id
        stored["created_at"] = created_at
        stored["schema_version"] = SCHEMA_VERSION

        self.conn.execute(
            "INSERT INTO tasks (task_id, source_model, title, goal, goal_hash, "
            "difficulty_level, task_json, design_quality_score, created_at, "
            "schema_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (task_id, stored["source_model"], stored["title"], stored["goal"],
             _goal_hash(stored["goal"]), stored["difficulty_level"],
             json.dumps(stored, ensure_ascii=False),
             stored.get("design_quality_score"), created_at, SCHEMA_VERSION),
        )
        self.conn.executemany(
            "INSERT INTO task_tags (task_id, tag) VALUES (?,?)",
            [(task_id, t) for t in dict.fromkeys(stored["difficulty_tags"])],
        )
        self.conn.executemany(
            "INSERT INTO expected_failure_modes (task_id, failure_mode) "
            "VALUES (?,?)",
            [(task_id, m) for m in dict.fromkeys(stored["expected_failure_modes"])],
        )
        self.conn.commit()
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT task_json FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return json.loads(row["task_json"]) if row else None

    def list_tasks(self, difficulty_level: int | None = None) -> list[dict]:
        if difficulty_level is None:
            rows = self.conn.execute(
                "SELECT task_json FROM tasks ORDER BY task_id"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT task_json FROM tasks WHERE difficulty_level = ? "
                "ORDER BY task_id", (difficulty_level,)
            ).fetchall()
        return [json.loads(r["task_json"]) for r in rows]

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]

    def add_review(self, task_id: str, reviewer_model: str, review: dict,
                   revised_difficulty_level: int | None = None,
                   design_quality_score: float | None = None) -> int:
        """검수 기록 추가. review_id 반환. (B1/B4에서 사용)"""
        if self.get_task(task_id) is None:
            raise KeyError(f"no such task: {task_id}")
        cur = self.conn.execute(
            "INSERT INTO task_reviews (task_id, reviewer_model, review_json, "
            "revised_difficulty_level, design_quality_score, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (task_id, reviewer_model, json.dumps(review, ensure_ascii=False),
             revised_difficulty_level, design_quality_score, _now()),
        )
        self.conn.commit()
        return cur.lastrowid
