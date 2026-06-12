"""배치 심장박동(batch_state.json) + 대시보드 배치/단계 표시 테스트."""

import json
import os
import subprocess
import sys

import batch
import dashboard


def _read_state(runs_dir):
    return json.loads((runs_dir / batch.BATCH_STATE_NAME)
                      .read_text(encoding="utf-8"))


# ---- batch.py: 상태 파일 쓰기 ------------------------------------------

def test_batch_writes_final_state(tmp_path):
    runs = tmp_path / "runs"
    result = batch.run_batch(
        2, runner=lambda args: 0,
        idea_gen=lambda: {"idea": "아이디어", "repo": "r", "level": 1},
        stop_file=tmp_path / "STOP", runs_dir=runs)
    assert result["done"] == 2
    state = _read_state(runs)
    assert state["active"] is False
    assert state["done"] == 2 and state["ok"] == 2
    assert state["pid"] == os.getpid()
    assert state["phase"] == "배치 종료"


def test_batch_state_updates_during_round(tmp_path):
    runs = tmp_path / "runs"
    seen = []

    def runner(args):
        seen.append(_read_state(runs))  # 회차 실행 중의 상태를 캡처
        return 0

    batch.run_batch(1, runner=runner,
                    idea_gen=lambda: {"idea": "CSV 도구", "repo": "r"},
                    stop_file=tmp_path / "STOP", runs_dir=runs)
    assert seen[0]["active"] is True
    assert seen[0]["round"] == 1
    assert "CSV 도구" in seen[0]["phase"]


def test_batch_stop_flag_still_writes_final_state(tmp_path):
    runs = tmp_path / "runs"
    (tmp_path / "STOP").write_text("x", encoding="utf-8")
    batch.run_batch(3, runner=lambda args: 0,
                    idea_gen=lambda: {"idea": "x", "repo": "r"},
                    stop_file=tmp_path / "STOP", runs_dir=runs)
    state = _read_state(runs)
    assert state["active"] is False
    assert state["stopped_by"] == "stop-flag"


# ---- dashboard.py: 배치 상태 읽기 + pid 생존 ---------------------------

def test_dashboard_sees_active_batch(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    (runs / batch.BATCH_STATE_NAME).write_text(json.dumps(
        {"active": True, "pid": os.getpid(), "round": 2, "requested": 5,
         "phase": "신규 생산 중"}), encoding="utf-8")
    s = dashboard.build_status(runs)
    assert s["batch"]["active"] is True
    assert s["batch"]["alive"] is True
    assert s["batch"]["crashed"] is False


def test_dashboard_flags_crashed_batch(tmp_path):
    # 이미 종료된 프로세스의 pid = active라고 적혀 있어도 죽은 배치
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    (runs / batch.BATCH_STATE_NAME).write_text(json.dumps(
        {"active": True, "pid": proc.pid,
         "round": 1, "requested": 3, "phase": "x"}), encoding="utf-8")
    s = dashboard.build_status(runs)
    assert s["batch"]["active"] is False
    assert s["batch"]["crashed"] is True


def test_dashboard_no_batch_file(tmp_path):
    s = dashboard.build_status(tmp_path / "runs")
    assert s["batch"] is None


def test_launch_blocked_while_batch_active(monkeypatch):
    monkeypatch.setattr(dashboard, "build_status",
                        lambda: {"live": None, "history": [],
                                 "stop_after": False,
                                 "batch": {"active": True, "round": 2,
                                           "requested": 5}})
    ok, msg = dashboard.launch_run("새 아이디어")
    assert ok is False
    assert "batch already running" in msg


# ---- dashboard.py: 라인 맵 단계 매핑 -----------------------------------

def test_stage_states_full_happy_path():
    events = [
        {"event": "phase", "name": "design"},
        {"event": "design-accepted", "files": ["a.py", "b.py"]},
        {"event": "phase", "name": "tests"},
        {"event": "tests-written"},
        {"event": "phase", "name": "implement"},
        {"event": "file-written", "file": "a.py"},
        {"event": "snapshot"},
        {"event": "phase", "name": "critique", "round": 1, "total": 2},
        {"event": "critique-lgtm"},
        {"event": "index-recorded"},
    ]
    stages = dashboard.stage_states(events)
    assert [s["status"] for s in stages] == ["done"] * 7
    assert stages[6]["note"] == "출하 완료"


def test_stage_states_exec_failure_marks_warn():
    events = [
        {"event": "phase", "name": "design"},
        {"event": "design-accepted", "files": []},
        {"event": "phase", "name": "implement"},
        {"event": "file-written", "file": "a.py"},
        {"event": "exec-issues", "target": "a.py"},
        {"event": "file-fixed", "file": "a.py"},
    ]
    stages = dashboard.stage_states(events)
    by = {s["key"]: s for s in stages}
    assert by["exec"]["status"] == "warn"      # 시운전에서 수리 중
    assert by["implement"]["status"] == "done"  # 지나간 단계는 통과 처리
    assert by["critique"]["status"] == "pending"
    assert by["ship"]["status"] == "pending"


def test_stage_states_abort_halts_current_stage():
    events = [
        {"event": "phase", "name": "design"},
        {"event": "aborted", "reason": "design failed"},
    ]
    stages = dashboard.stage_states(events)
    assert stages[0]["status"] == "halt"


def test_stage_states_halt_not_overridden_by_bookkeeping():
    # 사고로 멈춘 런도 장부 기록(index-recorded)은 남는다 —
    # 그 마무리 이벤트가 출하 램프를 초록으로 덮으면 안 된다 (실관측 버그)
    events = [
        {"event": "phase", "name": "design"},
        {"event": "design-accepted", "files": ["a.py"]},
        {"event": "phase", "name": "implement"},
        {"event": "file-written", "file": "a.py"},
        {"event": "static-issues", "issues": [1, 2]},
        {"event": "error", "reason": "API call failed"},
        {"event": "lesson-recorded"},
        {"event": "index-recorded"},
    ]
    stages = dashboard.stage_states(events)
    by = {s["key"]: s for s in stages}
    assert by["static"]["status"] == "halt"
    assert by["ship"]["status"] == "pending"


def test_file_states_from_design_and_events(tmp_path):
    run_dir = tmp_path / "r1"
    run_dir.mkdir()
    (run_dir / "design.json").write_text(json.dumps(
        {"files": [{"path": "main.py"}, {"path": "util.py"}]}),
        encoding="utf-8")
    events = [
        {"event": "file-written", "file": "main.py"},
        {"event": "file-fixed", "file": "util.py"},
    ]
    parts = dashboard.file_states(run_dir, events)
    assert parts == [{"name": "main.py", "state": "OK"},
                     {"name": "util.py", "state": "FIX"}]
