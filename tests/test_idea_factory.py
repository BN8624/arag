"""3층 테스트: 출제기(idea_factory) + 배치(batch) + 재발률(recurrence). 전부 콜 0."""

import json
import random

import pytest

import batch
import dashboard
import idea_factory as fac
import lessons
import run_index


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """auto_state.json·RUNS_DIR을 임시 경로로 격리."""
    monkeypatch.setattr(fac, "STATE_PATH", tmp_path / "auto_state.json")
    monkeypatch.setattr(fac, "RUNS_DIR", tmp_path / "runs")


# ------------------------------------------------------------ 중복제거

def test_jaccard():
    assert fac.jaccard(set(), set()) == 0.0
    assert fac.jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert fac.jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_too_similar():
    past = ["가계부 CSV 검증 도구: 거래 내역을 읽어 카테고리별 집계"]
    assert fac.too_similar("가계부 CSV 거래 내역 카테고리 집계 도구", past)
    assert not fac.too_similar("password vault encryption CLI", past)
    assert not fac.too_similar("anything", [])


# ------------------------------------------------------------ 상태·난이도

def test_state_roundtrip(tmp_path):
    state = fac.load_state()
    assert state["level"] == fac.DEFAULT_LEVEL
    state["level"] = 4
    state["used_repos"] = ["a/b"]
    fac.save_state(state)
    again = fac.load_state()
    assert again["level"] == 4
    assert again["used_repos"] == ["a/b"]


def test_state_corrupt_falls_back(tmp_path):
    fac.STATE_PATH.write_text("{broken", encoding="utf-8")
    assert fac.load_state()["level"] == fac.DEFAULT_LEVEL


def test_save_state_caps_used_repos():
    fac.save_state({"level": 2,
                    "used_repos": [f"r/{i}" for i in range(600)]})
    assert len(fac.load_state()["used_repos"]) == fac.MAX_USED_REPOS


def _entry(ok=True, static=0, exec_=0):
    return {"ok": ok, "fixes": {"static": static, "exec": exec_}}


def test_adjust_level_holds_with_few_runs():
    assert fac.adjust_level(3, [_entry(), _entry()]) == 3


def test_adjust_level_up_when_too_easy():
    entries = [_entry(ok=True, static=0, exec_=0)] * 5
    assert fac.adjust_level(2, entries) == 3
    assert fac.adjust_level(5, entries) == 5  # 상한


def test_adjust_level_down_when_too_hard():
    entries = [_entry(ok=False, static=3, exec_=2)] * 5
    assert fac.adjust_level(3, entries) == 2
    assert fac.adjust_level(1, entries) == 1  # 하한


def test_adjust_level_holds_in_target_band():
    # 전부 성공 + 평균 자가수정 1~2회 = 타깃 구간 → 유지
    entries = [_entry(ok=True, static=1, exec_=1)] * 5
    assert fac.adjust_level(3, entries) == 3


def test_axis_levels_clamped():
    rng = random.Random(7)
    for base in (1, 3, 5):
        for _ in range(20):
            axes = fac.axis_levels(base, rng)
            assert set(axes) == set(fac.AXIS_GUIDE)
            assert all(1 <= lv <= 5 for lv in axes.values())


# ------------------------------------------------------------ 후보 추첨

REPOS = [
    {"full_name": "a/used", "description": "already used repo",
     "topics": ["cli"], "stars": 500},
    {"full_name": "b/similar",
     "description": "가계부 CSV 거래 내역 카테고리 집계 검증 도구",
     "topics": ["finance"], "stars": 400},
    {"full_name": "c/fresh", "description": "terminal habit tracker",
     "topics": ["habit"], "stars": 300},
]


def test_pick_candidate_skips_used_and_similar():
    past = ["가계부 CSV 검증 도구: 거래 내역을 읽어 카테고리별 집계"]
    topic, repo = fac.pick_candidate(
        "", past, ["a/used"], random.Random(0),
        fetch=lambda topic, token: list(REPOS))
    assert repo["full_name"] == "c/fresh"


def test_pick_candidate_none_when_exhausted():
    assert fac.pick_candidate("", [], [], random.Random(0),
                              fetch=lambda topic, token: []) is None


# ------------------------------------------------------------ 출제 프롬프트·파싱

def test_idea_prompt_contains_axes_and_constraints():
    axes = {axis: 3 for axis in fac.AXIS_GUIDE}
    p = fac.idea_prompt(REPOS[2], "Track your habits in the terminal.", axes)
    assert "c/fresh" in p
    assert "Track your habits" in p
    for axis in fac.AXIS_GUIDE:
        assert fac.AXIS_GUIDE[axis][3] in p
    assert "stdin" in p
    assert "mock JSON" in p
    assert "KOREAN" in p


def test_parse_idea():
    good = json.dumps({"idea": "습관 추적 CLI", "keywords": ["Habit", " cli "]})
    out = fac._parse_idea(good)
    assert out == {"idea": "습관 추적 CLI", "keywords": ["habit", "cli"]}
    assert fac._parse_idea("no json here") is None
    assert fac._parse_idea(json.dumps({"idea": ""})) is None


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, role, prompt, temperature=None):
        assert role == "critic"  # 출제는 31B(머리)의 일
        self.calls += 1
        return self.replies.pop(0)


def _patch_network(monkeypatch):
    monkeypatch.setattr(fac, "github_token", lambda: "tok")
    monkeypatch.setattr(fac, "fetch_repo_candidates",
                        lambda topic, token: list(REPOS))
    monkeypatch.setattr(fac, "fetch_readme",
                        lambda full_name, token, max_chars=2500: "readme text")


def test_generate_idea_full_pipeline(monkeypatch):
    _patch_network(monkeypatch)
    llm = FakeLLM([json.dumps({"idea": "터미널 습관 추적 CLI 도구",
                               "keywords": ["habit", "cli"]})])
    out = fac.generate_idea(llm, rng=random.Random(0))
    assert out["idea"] == "터미널 습관 추적 CLI 도구"
    assert out["repo"] in {r["full_name"] for r in REPOS}
    assert out["level"] == fac.DEFAULT_LEVEL  # 런 이력 없음 → 기본 레벨
    assert set(out["axes"]) == set(fac.AXIS_GUIDE)
    # 사용한 저장소가 상태에 기록돼 다음 출제에서 제외된다
    assert out["repo"] in fac.load_state()["used_repos"]


def test_generate_idea_retries_bad_json_once(monkeypatch):
    _patch_network(monkeypatch)
    llm = FakeLLM(["not json at all",
                   json.dumps({"idea": "두 번째 응답", "keywords": []})])
    out = fac.generate_idea(llm, rng=random.Random(0))
    assert out["idea"] == "두 번째 응답"
    assert llm.calls == 2


def test_generate_idea_fails_after_two_bad_json(monkeypatch):
    _patch_network(monkeypatch)
    llm = FakeLLM(["nope", "still nope"])
    with pytest.raises(RuntimeError):
        fac.generate_idea(llm, rng=random.Random(0))


def test_generate_idea_no_candidate(monkeypatch):
    monkeypatch.setattr(fac, "github_token", lambda: "tok")
    monkeypatch.setattr(fac, "fetch_repo_candidates", lambda topic, token: [])
    with pytest.raises(RuntimeError):
        fac.generate_idea(FakeLLM([]), rng=random.Random(0))


# ------------------------------------------------------------ 배치 루프

def test_batch_runs_all_rounds(tmp_path):
    ideas = iter(["아이디어1", "아이디어2", "아이디어3"])
    ran = []
    result = batch.run_batch(
        3, runner=lambda idea: (ran.append(idea), 0)[1],
        idea_gen=lambda: {"idea": next(ideas), "repo": "r", "level": 2},
        stop_file=tmp_path / "STOP")
    assert result == {"requested": 3, "done": 3, "ok": 3, "stopped_by": None}
    assert ran == ["아이디어1", "아이디어2", "아이디어3"]


def test_batch_respects_stop_flag(tmp_path):
    stop = tmp_path / "STOP"
    calls = {"n": 0}

    def runner(idea):
        calls["n"] += 1
        stop.write_text("now", encoding="utf-8")  # 1회차 끝에 종료예약
        return 0

    result = batch.run_batch(
        5, runner=runner,
        idea_gen=lambda: {"idea": "아이디어", "repo": "r", "level": 2},
        stop_file=stop)
    assert calls["n"] == 1
    assert result["stopped_by"] == "stop-flag"


def test_batch_stops_after_consecutive_failures(tmp_path):
    result = batch.run_batch(
        10, runner=lambda idea: 1,
        idea_gen=lambda: {"idea": "아이디어", "repo": "r", "level": 2},
        stop_file=tmp_path / "STOP")
    assert result["done"] == batch.MAX_CONSECUTIVE_FAILURES
    assert result["ok"] == 0
    assert result["stopped_by"] == "consecutive-failures"


def test_batch_idea_gen_failure_counts(tmp_path):
    def bad_gen():
        raise RuntimeError("network down")

    result = batch.run_batch(10, runner=lambda idea: 0, idea_gen=bad_gen,
                             stop_file=tmp_path / "STOP")
    assert result["done"] == 0
    assert result["stopped_by"] == "consecutive-failures"


def test_batch_caps_rounds(tmp_path):
    result = batch.run_batch(
        999, runner=lambda idea: 0,
        idea_gen=lambda: {"idea": "아이디어", "repo": "r", "level": 2},
        stop_file=tmp_path / "STOP")
    assert result["requested"] == batch.MAX_RUNS


# ------------------------------------------------------------ 대시보드 자동 모드

def test_launch_batch_validates_count(monkeypatch):
    monkeypatch.setattr(dashboard, "build_status",
                        lambda: {"live": None, "history": []})
    ok, msg = dashboard.launch_batch("abc")
    assert not ok and "bad" in msg
    ok, msg = dashboard.launch_batch(0)
    assert not ok
    ok, msg = dashboard.launch_batch(21)
    assert not ok


def test_launch_batch_spawns(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "build_status",
                        lambda: {"live": None, "history": []})
    monkeypatch.setattr(dashboard, "STOP_FILE", tmp_path / "STOP")
    spawned = {}

    def fake_spawn(cmd):
        spawned["cmd"] = cmd
        return True, "started"

    monkeypatch.setattr(dashboard, "_spawn", fake_spawn)
    ok, _ = dashboard.launch_batch("5")
    assert ok
    assert spawned["cmd"][-2:] == ["--runs", "5"]
    assert "batch.py" in spawned["cmd"][1]


def test_launch_batch_blocked_while_running(monkeypatch):
    monkeypatch.setattr(
        dashboard, "build_status",
        lambda: {"live": {"running": True, "run": "20260611-1"}, "history": []})
    ok, msg = dashboard.launch_batch(3)
    assert not ok and "already running" in msg


# ------------------------------------------------------------ 재발률

def test_recurrence_stats_empty():
    assert run_index.recurrence_stats([]) == {
        "injected_runs": 0, "recurred": 0, "rate": None}


def test_recurrence_stats_counts_overlap():
    entries = [
        # 주입 + 실패 + keyword 겹침 = 재발
        {"ok": False, "lessons_injected": ["csv", "cli"],
         "failure_keywords": ["cli", "parsing"]},
        # 주입 + 성공 = 재발 아님
        {"ok": True, "lessons_injected": ["csv"], "failure_keywords": []},
        # 주입 + 실패지만 keyword 안 겹침 = 다른 유형 실패
        {"ok": False, "lessons_injected": ["csv"],
         "failure_keywords": ["docker"]},
        # 주입 없음 = 모수에서 제외
        {"ok": False, "failure_keywords": ["cli"]},
    ]
    stats = run_index.recurrence_stats(entries)
    assert stats == {"injected_runs": 3, "recurred": 1, "rate": 0.333}


def test_find_relevant_entries_returns_keywords(tmp_path):
    entries = [{"t": "2026-06-11", "idea": "csv 가계부 도구",
                "keywords": ["csv", "budget"], "lesson": "csv 헤더를 검증하라"}]
    found = lessons.find_relevant_entries("csv 거래 내역 검증 도구", entries)
    assert len(found) == 1
    assert found[0]["keywords"] == ["csv", "budget"]
    # 기존 find_relevant는 동일 결과의 텍스트만
    assert lessons.find_relevant("csv 거래 내역 검증 도구", entries) == [
        "csv 헤더를 검증하라"]


def test_orchestrator_records_injected_keywords(tmp_path, monkeypatch):
    from conftest import GOOD_CORE, GOOD_MAIN, make_design
    from test_orchestrator_mock import MockLLM, fenced
    import orchestrator as orch_mod

    monkeypatch.setattr(
        orch_mod, "find_relevant_entries",
        lambda idea: [{"lesson": "JSON 저장 시 인코딩을 명시하라",
                       "keywords": ["json", "encoding"]}])
    llm = MockLLM(critic=[json.dumps(make_design()), "LGTM"],
                  generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)])
    orch = orch_mod.Orchestrator(llm, tmp_path / "runs" / "run1",
                                 skip_exec=True)
    assert orch.run("tiny todo cli") is True
    entries = run_index.load_index(tmp_path / "runs")
    assert entries[0]["lessons_injected"] == ["encoding", "json"]
