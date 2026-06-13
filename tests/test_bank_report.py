# bank_report 테스트: 합성 index ↔ bank 조인(콜 0) — 태그/레벨 집계
import copy
import json

import pytest

from bank_db import BankDB
from bank_report import join_runs, latest_per_card, per_level, per_tag, render
from test_bank_schema import EXAMPLE


@pytest.fixture
def setup(tmp_path):
    db = BankDB(tmp_path / "rep.sqlite")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    # 카드 2장: L2(cli_arg_surface...), L4(parser_logic...)
    c1 = copy.deepcopy(EXAMPLE)
    c1["title"], c1["goal"], c1["difficulty_level"] = "card one", "goal one", 2
    c1["difficulty_tags"] = ["cli_arg_surface", "parser_logic"]
    t1 = db.insert_task(c1)
    c2 = copy.deepcopy(EXAMPLE)
    c2["title"], c2["goal"], c2["difficulty_level"] = "card two", "goal two", 4
    c2["difficulty_tags"] = ["parser_logic", "stateful_io"]
    t2 = db.insert_task(c2)

    # index: t1 성공 런, t2 실패 런, + task_id 없는 런(조인 제외)
    index = [
        {"run": "r1", "status": "OK", "ok": True, "task_id": t1},
        {"run": "r2", "status": "ABORTED: gates", "ok": False, "task_id": t2},
        {"run": "r3", "status": "OK", "ok": True},  # task_id 없음
    ]
    (runs_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (runs_dir / "r2").mkdir()  # 실패 런 디렉토리(events 없음 → 분류만)
    yield db, runs_dir, t1, t2
    db.close()


def test_join_only_task_id_runs(setup):
    db, runs_dir, t1, t2 = setup
    rows = join_runs(db, runs_dir)
    assert len(rows) == 2  # task_id 없는 r3 제외
    by_tid = {r["task_id"]: r for r in rows}
    assert by_tid[t1]["ok"] is True and by_tid[t2]["ok"] is False
    assert by_tid[t1]["level"] == 2 and by_tid[t2]["level"] == 4


def test_per_level_aggregates(setup):
    db, runs_dir, t1, t2 = setup
    rep = per_level(join_runs(db, runs_dir))
    assert rep[2]["success_rate"] == 1.0
    assert rep[4]["success_rate"] == 0.0


def test_per_tag_counts_shared_tag(setup):
    db, runs_dir, t1, t2 = setup
    rep = per_tag(join_runs(db, runs_dir))
    # parser_logic는 두 카드 공유 → n=2, 성공 1
    assert rep["parser_logic"]["n"] == 2
    assert rep["parser_logic"]["ok"] == 1
    assert rep["cli_arg_surface"]["n"] == 1


def test_latest_per_card_dedupes_retry(setup):
    db, runs_dir, t1, t2 = setup
    # t2를 두 번 돈 것처럼: 실패 런 + 최신 성공 런
    import json
    idx = json.loads((runs_dir / "index.json").read_text(encoding="utf-8"))
    idx.append({"run": "r2b", "status": "OK", "ok": True, "task_id": t2})
    (runs_dir / "index.json").write_text(json.dumps(idx), encoding="utf-8")
    rows = join_runs(db, runs_dir)
    assert len(rows) == 3  # 런 단위
    carded = latest_per_card(rows)
    assert len(carded) == 2  # 카드 단위
    assert {r["task_id"]: r["ok"] for r in carded}[t2] is True  # 최신(성공) 반영


def test_render_runs(setup):
    db, runs_dir, t1, t2 = setup
    out = render(db, runs_dir)
    assert "레벨별" in out and "태그별" in out


def test_render_empty(tmp_path):
    db = BankDB(tmp_path / "e.sqlite")
    (tmp_path / "runs").mkdir()
    assert "조인된 런이 없다" in render(db, tmp_path / "runs")
    db.close()
