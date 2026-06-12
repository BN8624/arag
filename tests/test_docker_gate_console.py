"""docker_gate의 콘솔 창 숨김 헬퍼 테스트 (Docker 불필요, 콜 0).

pythonw(대시보드 백그라운드)로 돌 때 docker.exe가 회차마다 검은 콘솔 창을
깜빡이지 않도록, 모든 subprocess.run 호출에 숨김 인자가 들어가는지 확인.
"""

import subprocess
import sys
from types import SimpleNamespace

import docker_gate as dg


def test_hidden_console_kwargs_shape():
    kw = dg._hidden_console_kwargs()
    if sys.platform == "win32":
        assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert kw["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert kw["startupinfo"].wShowWindow == subprocess.SW_HIDE
    else:
        assert kw == {}  # 다른 OS에서는 동작 변화 없음


def _capture_run(calls):
    """subprocess.run 대역: (argv, kwargs)를 기록하고 성공을 흉내낸다."""
    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    return fake_run


def _assert_hidden(kwargs):
    if sys.platform == "win32":
        assert kwargs.get("creationflags") == subprocess.CREATE_NO_WINDOW
        assert kwargs.get("startupinfo") is not None
    else:
        assert "creationflags" not in kwargs


def test_docker_available_hides_console(monkeypatch):
    calls = []
    monkeypatch.setattr(dg.subprocess, "run", _capture_run(calls))
    assert dg.docker_available() is True
    assert calls[0][0][:2] == ["docker", "info"]
    _assert_hidden(calls[0][1])


def test_install_packages_hides_console(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dg.subprocess, "run", _capture_run(calls))
    ok, _ = dg.install_packages(tmp_path / "deps", ["click"])
    assert ok
    assert calls[0][0][:2] == ["docker", "run"]
    _assert_hidden(calls[0][1])


def test_run_in_docker_hides_console(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dg.subprocess, "run", _capture_run(calls))
    rc, out = dg._run_in_docker(tmp_path, ["python", "-V"], timeout=5)
    assert rc == 0 and out == "ok"
    _assert_hidden(calls[0][1])


def test_docker_kill_on_timeout_hides_console(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, timeout=5,
                                            output="partial", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(dg.subprocess, "run", fake_run)
    rc, out = dg._run_in_docker(tmp_path, ["python", "-V"], timeout=5)
    assert rc == -1 and "partial" in out
    kill_calls = [(c, kw) for c, kw in calls if c[:2] == ["docker", "kill"]]
    assert len(kill_calls) == 1
    _assert_hidden(kill_calls[0][1])
