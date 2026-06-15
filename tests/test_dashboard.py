"""dashboard 테스트 (서버 없이 조회·토글 로직만)."""

import json
import time

import pytest

import dashboard
import run_index

LIVE_THRESHOLD_AGED = dashboard.LIVE_THRESHOLD_SEC + 60  # 라이브 임계 넘긴 '끝난' 런


@pytest.fixture(autouse=True)
def _isolate_stop_file(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "STOP_FILE", tmp_path / "STOP_AFTER_RUN")


def _mk_run(runs_dir, name, events=(), report=False, design=None):
    d = runs_dir / name
    d.mkdir(parents=True)
    if events:
        lines = [json.dumps(e) for e in events]
        (d / "events.jsonl").write_text("\n".join(lines), encoding="utf-8")
    if report:
        (d / "REPORT.md").write_text("# report", encoding="utf-8")
    if design:
        (d / "design.json").write_text(json.dumps(design), encoding="utf-8")
    return d


def test_empty_runs_dir(tmp_path):
    s = dashboard.build_status(tmp_path / "runs")
    assert s["live"] is None
    assert s["history"] == []
    assert s["total_cost_usd"] == 0


def test_live_run_detected(tmp_path):
    runs = tmp_path / "runs"
    _mk_run(runs, "20260611-1",
            events=[{"t": "2026-06-11T19:33:33", "event": "design-accepted",
                     "files": ["a.py", "b.py"]}],
            design={"description": "expense tool"})
    s = dashboard.build_status(runs)
    assert s["live"]["run"] == "20260611-1"
    assert s["live"]["running"] is True  # 방금 만든 파일 = LIVE_THRESHOLD 안
    assert s["live"]["description"] == "expense tool"
    assert s["live"]["last_event"] == "design-accepted"
    assert any("설계도 승인" in line and "2개" in line
               for line in s["live"]["events_tail"])


def test_latest_run_wins(tmp_path):
    runs = tmp_path / "runs"
    _mk_run(runs, "20260610-1", events=[{"t": "x", "event": "aborted"}])
    _mk_run(runs, "20260611-2", events=[{"t": "x", "event": "scoreboard",
                                         "passed": 3, "total": 4}])
    s = dashboard.build_status(runs)
    assert s["live"]["run"] == "20260611-2"


def test_run_state_derivation():
    assert dashboard._run_state([], running=True) == "run"
    assert dashboard._run_state(
        [{"event": "aborted"}], running=False) == "fail"
    assert dashboard._run_state(
        [{"event": "scoreboard", "passed": 4, "total": 4}],
        running=False) == "pass"
    assert dashboard._run_state(
        [{"event": "scoreboard", "passed": 2, "total": 4}],
        running=False) == "done"
    assert dashboard._run_state(
        [{"event": "critique-lgtm"}], running=False) == "pass"


def test_live_runs_grid(tmp_path, monkeypatch):
    """병렬 그리드: 윈도우 안 런들을 이름순 압축요약으로. 윈도우 밖은 제외."""
    runs = tmp_path / "runs"
    _mk_run(runs, "20260615-sel02",
            events=[{"t": "2026-06-15T20:00:00", "event": "scoreboard",
                     "passed": 4, "total": 4}])
    _mk_run(runs, "20260615-sel01",
            events=[{"t": "2026-06-15T20:00:00", "event": "aborted"}])
    old = _mk_run(runs, "20260615-sel99",
                  events=[{"t": "x", "event": "phase", "name": "design"}])
    import os
    # sel01/02는 끝난 상태(라이브 임계 넘김, 윈도우 안), sel99는 윈도우 밖
    done = time.time() - LIVE_THRESHOLD_AGED
    past = time.time() - dashboard.PARALLEL_WINDOW_SEC - 100
    for name in ("20260615-sel01", "20260615-sel02"):
        os.utime(runs / name / "events.jsonl", (done, done))
    os.utime(old / "events.jsonl", (past, past))

    rows = dashboard._live_runs(runs)
    attempts = [r["attempt"] for r in rows]
    assert attempts == ["sel01", "sel02"]          # 이름순, sel99 제외
    by = {r["attempt"]: r for r in rows}
    assert by["sel02"]["state"] == "pass"
    assert by["sel01"]["state"] == "fail"


def test_build_status_has_parallel_fields(tmp_path):
    s = dashboard.build_status(tmp_path / "runs")
    assert "live_runs" in s and isinstance(s["live_runs"], list)
    assert "rpd" in s and "rows" in s["rpd"]


def test_history_from_index(tmp_path):
    runs = tmp_path / "runs"
    d = _mk_run(runs, "20260611-1", events=[{"t": "x", "event": "aborted"}])
    run_index.record_run(d, {"run": "20260611-1", "ok": True,
                             "cost_usd": 0.031})
    run_index.record_run(d, {"run": "20260611-2", "ok": False,
                             "cost_usd": 0.052})
    s = dashboard.build_status(runs)
    assert [e["run"] for e in s["history"]] == ["20260611-2", "20260611-1"]
    assert s["total_cost_usd"] == 0.083


def test_stale_run_not_running(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    _mk_run(runs, "20260611-1", events=[{"t": "x", "event": "aborted"}])
    monkeypatch.setattr(time, "time",
                        lambda: time.mktime(time.localtime()) + 9999)
    s = dashboard.build_status(runs)
    assert s["live"]["running"] is False


def test_toggle_stop_roundtrip(tmp_path):
    assert dashboard.STOP_FILE.exists() is False
    assert dashboard.toggle_stop() is True
    assert dashboard.STOP_FILE.exists() is True
    assert dashboard.build_status(tmp_path / "runs")["stop_after"] is True
    assert dashboard.toggle_stop() is False
    assert dashboard.STOP_FILE.exists() is False


def test_launch_rejects_empty_idea():
    ok, msg = dashboard.launch_run("   ")
    assert ok is False
    assert "empty" in msg


def test_launch_rejects_while_running(monkeypatch):
    monkeypatch.setattr(dashboard, "build_status",
                        lambda: {"live": {"run": "r1", "running": True},
                                 "history": [], "stop_after": False})
    ok, msg = dashboard.launch_run("new idea")
    assert ok is False
    assert "already running" in msg


def test_launch_clears_stop_flag(tmp_path, monkeypatch):
    dashboard.STOP_FILE.write_text("x", encoding="utf-8")
    monkeypatch.setattr(dashboard, "build_status",
                        lambda: {"live": None, "history": [],
                                 "stop_after": True})
    launched = {}
    monkeypatch.setattr(dashboard.subprocess, "Popen",
                        lambda *a, **kw: launched.setdefault("args", a))
    monkeypatch.setattr(dashboard, "RUNS_DIR", tmp_path / "runs")
    ok, msg = dashboard.launch_run("new idea")
    assert ok is True
    assert dashboard.STOP_FILE.exists() is False  # 수동 시작 = 예약 해제
    assert "new idea" in launched["args"][0]


def test_humanize_korean_factory_lines():
    cases = [
        ({"t": "2026-06-11T19:00:01", "event": "phase", "name": "design"},
         "[31B] 설계 시작"),
        ({"t": "x", "event": "phase", "name": "critique", "round": 1, "total": 2},
         "품질심사 1/2라운드"),
        ({"t": "x", "event": "file-written", "file": "main.py"},
         "[26B] 부품 제작: main.py"),
        ({"t": "x", "event": "exec-issues", "target": "main.py"},
         "[26B] main.py 수리"),
        ({"t": "x", "event": "scoreboard", "passed": 4, "total": 5}, "4/5"),
        ({"t": "x", "event": "critique-lgtm"}, "LGTM"),
        ({"t": "x", "event": "aborted", "reason": "stuck"}, "라인 정지"),
    ]
    for event, expected in cases:
        assert expected in dashboard._humanize(event)


def test_humanize_unknown_event_falls_back_to_raw():
    assert "some-new-event" in dashboard._humanize(
        {"t": "x", "event": "some-new-event"})


def test_improvable_runs_filters_ok(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    d = _mk_run(runs, "20260611-1")
    run_index.record_run(d, {"run": "ok-run", "ok": True, "idea": "todo cli",
                             "score": {"passed": 4, "total": 5}})
    run_index.record_run(d, {"run": "fail-run", "ok": False, "idea": "broken"})
    monkeypatch.setattr(dashboard, "RUNS_DIR", runs)
    out = dashboard.improvable_runs()
    assert [e["run"] for e in out] == ["ok-run"]
    assert out[0]["score"] == {"passed": 4, "total": 5}
    # status에도 동일 목록이 실린다
    s = dashboard.build_status(runs)
    assert [e["run"] for e in s["improvable"]] == ["ok-run"]


def test_launch_improve_rejects_bad_run(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "RUNS_DIR", tmp_path / "runs")
    ok, msg = dashboard.launch_improve("../etc", "fix")
    assert ok is False and "bad run name" in msg
    ok, msg = dashboard.launch_improve("nope", "fix")
    assert ok is False and "not found" in msg


def test_launch_improve_spawns_with_args(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    d = _mk_run(runs, "good-run", report=True)
    run_index.record_run(d, {"run": "good-run", "ok": True,
                             "idea": "expense cli"})
    monkeypatch.setattr(dashboard, "RUNS_DIR", runs)
    monkeypatch.setattr(dashboard, "build_status",
                        lambda: {"live": None, "history": [],
                                 "stop_after": False, "improvable": []})
    captured = {}
    monkeypatch.setattr(dashboard.subprocess, "Popen",
                        lambda cmd, **kw: captured.setdefault("cmd", cmd))
    ok, msg = dashboard.launch_improve("good-run", "고쳐줘")
    assert ok is True
    cmd = captured["cmd"]
    assert "--improve" in cmd and "--feedback" in cmd
    assert "고쳐줘" in cmd
    assert "expense cli" in cmd  # 원래 아이디어가 positional로 전달


def test_corrupt_events_skipped(tmp_path):
    runs = tmp_path / "runs"
    d = runs / "20260611-1"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text(
        '{"t": "x", "event": "ok-line"}\n{broken json\n', encoding="utf-8")
    s = dashboard.build_status(runs)
    assert s["live"]["last_event"] == "ok-line"
