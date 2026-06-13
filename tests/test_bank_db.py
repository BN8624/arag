# bank_db 테스트: insert/get/list 왕복 + 검증·중복 거부 + 리뷰
import copy

import pytest

from bank_db import BankDB, DuplicateTask, InvalidCard
from test_bank_schema import EXAMPLE


@pytest.fixture
def db(tmp_path):
    d = BankDB(tmp_path / "test_bank.sqlite")
    yield d
    d.close()


def card(**overrides) -> dict:
    c = copy.deepcopy(EXAMPLE)
    c.update(overrides)
    return c


def test_insert_then_roundtrip(db):
    tid = db.insert_task(card())
    assert tid == "T-000001"
    got = db.get_task(tid)
    assert got["title"] == EXAMPLE["title"]
    assert got["task_id"] == tid
    assert got["created_at"] and got["schema_version"] == "task_card.v1"


def test_ids_increment(db):
    db.insert_task(card(title="alpha tool", goal="goal one"))
    second = db.insert_task(card(title="beta tool", goal="goal two"))
    assert second == "T-000002"
    assert db.count() == 2


def test_invalid_card_rejected(db):
    with pytest.raises(InvalidCard) as exc:
        db.insert_task(card(difficulty_tags=["bogus_tag"]))
    assert any("bogus_tag" in e for e in exc.value.errors)
    assert db.count() == 0


def test_exact_goal_duplicate_rejected(db):
    db.insert_task(card(title="first", goal="Read a CSV and summarize."))
    with pytest.raises(DuplicateTask, match="goal duplicates"):
        db.insert_task(card(title="totally different name here",
                            goal="read a csv  and summarize"))


def test_similar_title_duplicate_rejected(db):
    db.insert_task(card(title="CSV log summarizer with CLI options",
                        goal="unique goal alpha"))
    with pytest.raises(DuplicateTask, match="title"):
        db.insert_task(card(title="CSV log summarizer with CLI option",
                            goal="unique goal beta entirely"))


def test_list_filters_by_level(db):
    db.insert_task(card(title="lvl two tool", goal="g1", difficulty_level=2))
    db.insert_task(card(title="lvl four tool", goal="g2", difficulty_level=4))
    assert len(db.list_tasks()) == 2
    lvl4 = db.list_tasks(difficulty_level=4)
    assert len(lvl4) == 1 and lvl4[0]["difficulty_level"] == 4


def test_tags_and_modes_persisted(db):
    tid = db.insert_task(card())
    tags = [r["tag"] for r in db.conn.execute(
        "SELECT tag FROM task_tags WHERE task_id=?", (tid,))]
    modes = [r["failure_mode"] for r in db.conn.execute(
        "SELECT failure_mode FROM expected_failure_modes WHERE task_id=?", (tid,))]
    assert set(tags) == set(EXAMPLE["difficulty_tags"])
    assert set(modes) == set(EXAMPLE["expected_failure_modes"])


def test_add_review(db):
    tid = db.insert_task(card())
    rid = db.add_review(tid, "gemini-3.1-pro", {"verdict": "ok"},
                        revised_difficulty_level=3, design_quality_score=4.0)
    assert rid == 1
    with pytest.raises(KeyError):
        db.add_review("T-999999", "x", {})
