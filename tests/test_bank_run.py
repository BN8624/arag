# bank_run 테스트: mock runner 주입(콜 0) — 카드 선택·순차 실행·연속실패 중단
import copy

import pytest

from bank_db import BankDB
from bank_run import run_cards, select_cards
from test_bank_schema import EXAMPLE


@pytest.fixture
def db(tmp_path):
    d = BankDB(tmp_path / "run.sqlite")
    # 레벨 1~4 두 장씩
    titles = iter(["alpha json", "beta csv", "gamma log", "delta diff",
                   "epsilon yaml", "zeta toml", "eta ini", "theta env"])
    for lv in (1, 1, 2, 2, 3, 3, 4, 4):
        c = copy.deepcopy(EXAMPLE)
        name = next(titles)
        c["title"], c["goal"], c["difficulty_level"] = name, f"goal {name}", lv
        d.insert_task(c)
    yield d
    d.close()


def test_select_spreads_across_levels(db):
    picked = select_cards(db, 4)
    levels = [db.get_task(t)["difficulty_level"] for t in picked]
    assert sorted(levels) == [1, 2, 3, 4]  # 라운드로빈으로 레벨 1장씩


def test_run_cards_counts_ok_and_fail(db):
    codes = iter([0, 1, 0])
    seen = []

    def runner(args):
        seen.append(args)
        return next(codes)

    stats = run_cards(db, 3, runner=runner)
    assert stats["selected"] == 3 and stats["ok"] == 2 and stats["failed"] == 1
    # 각 호출에 --task-id가 붙는다
    assert all("--task-id" in a for a in seen)


def test_consecutive_failures_stop(db):
    def runner(args):
        return 1  # 항상 실패

    stats = run_cards(db, 6, runner=runner)
    assert stats["stopped_by"] == "consecutive-failures"
    assert stats["failed"] == 2  # MAX_INFRA_STRIKES=2 에서 멈춤


def test_exclude_skips_already_run(db):
    picked_all = select_cards(db, 8)
    skip = picked_all[0]
    picked = select_cards(db, 8, exclude={skip})
    assert skip not in picked
    assert len(picked) == 7


def test_extra_args_passed(db):
    seen = []

    def runner(args):
        seen.append(args)
        return 0

    run_cards(db, 1, runner=runner, extra_args=["--skip-exec"])
    assert "--skip-exec" in seen[0]
