# golem 게임 은행 — 검증된 게임 카드(규칙·시나리오·골든·솔루션)를 sqlite에 적재·조회
"""검증을 통과한 게임 엔진을 '카드'로 쌓는 라이브러리. 새 아이디어가 오면 가까운 카드를
베이스로 gemma가 확장하고, 통과하면 다시 카드로 적재한다(자가증식).

카드 한 장이 담는 것:
  slug       : 식별자(PK)
  title      : 사람용 제목
  genre      : 장르(turn-rpg / autobattler / card / sim / roguelike ...)
  mechanics  : 핵심 메카닉 태그(쉼표구분, 검색용)
  rules      : 워커에게 줄 규칙 스펙(worker_prompt의 §RULES 본문)
  scenarios  : {"1": {"party": {...}, "golden": {winner,turns,final_hp}}, ...}
               party=워커 입력(비밀 아님), golden=채점용 정답(워커 비노출)
  solution   : {filename: content} — 검증 통과한 구현(확장 베이스). 없으면 {}
  reference  : {filename: content} — 골든을 만든 레퍼런스 구현(재현용). 없으면 {}
  notes      : 자유 메모

코드 묶음(solution/reference)·scenarios는 JSON 텍스트로 저장(자족적·이식 쉬움).
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "game_bank.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    slug       TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    genre      TEXT NOT NULL DEFAULT '',
    mechanics  TEXT NOT NULL DEFAULT '',
    rules      TEXT NOT NULL,
    scenarios  TEXT NOT NULL,         -- JSON
    solution   TEXT NOT NULL DEFAULT '{}',  -- JSON {file: content}
    reference  TEXT NOT NULL DEFAULT '{}',  -- JSON {file: content}
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_JSON_COLS = ("scenarios", "solution", "reference")


def connect(db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_card(card, db_path=DB_PATH):
    """카드 dict를 적재(같은 slug면 덮어쓴다). scenarios/solution/reference는 dict로 받아 JSON 저장."""
    row = {
        "slug": card["slug"],
        "title": card["title"],
        "genre": card.get("genre", ""),
        "mechanics": card.get("mechanics", ""),
        "rules": card["rules"],
        "scenarios": json.dumps(card["scenarios"], ensure_ascii=False),
        "solution": json.dumps(card.get("solution", {}), ensure_ascii=False),
        "reference": json.dumps(card.get("reference", {}), ensure_ascii=False),
        "notes": card.get("notes", ""),
    }
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO cards (slug,title,genre,mechanics,rules,scenarios,solution,reference,notes)
               VALUES (:slug,:title,:genre,:mechanics,:rules,:scenarios,:solution,:reference,:notes)
               ON CONFLICT(slug) DO UPDATE SET
                 title=:title, genre=:genre, mechanics=:mechanics, rules=:rules,
                 scenarios=:scenarios, solution=:solution, reference=:reference, notes=:notes""",
            row)
    return card["slug"]


def get_card(slug, db_path=DB_PATH):
    """slug로 카드 dict 조회. JSON 컬럼은 dict로 복원. 없으면 None."""
    with connect(db_path) as conn:
        r = conn.execute("SELECT * FROM cards WHERE slug=?", (slug,)).fetchone()
    if r is None:
        return None
    card = dict(r)
    for c in _JSON_COLS:
        card[c] = json.loads(card[c])
    return card


def list_cards(db_path=DB_PATH):
    """카드 요약 목록(slug/title/genre/mechanics/시나리오수)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT slug,title,genre,mechanics,scenarios,created_at FROM cards ORDER BY created_at"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["n_scenarios"] = len(json.loads(d.pop("scenarios")))
        out.append(d)
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass
    for c in list_cards():
        print(f"- {c['slug']:18} [{c['genre']}] {c['title']} "
              f"({c['n_scenarios']} scenarios) :: {c['mechanics']}")
