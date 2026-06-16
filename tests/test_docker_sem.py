# 병렬 인프라 3: 도커 세마포어 + 메모리캡 테스트 (결정22, 콜 0, 도커 미실행)
"""checklist 3 검증: _run_in_docker가 --memory/--cpus 캡을 붙이는지 / 세마포어가
동시 컨테이너 수를 N으로 제한하는지. subprocess.run을 가짜로 대체해 실제 도커는 안 띄움.
"""

import threading
import time
import types
from pathlib import Path

import docker_gate


def _fake_ok(*a, **k):
    return types.SimpleNamespace(returncode=0, stdout="", stderr="")


def _ws(tmp_path):
    """작은 워크스페이스(원본 통째 복사를 피하려 tmp_path 사용 — 격리는 복사본을 마운트)."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("print('hi')\n", encoding="utf-8")
    return ws


def test_run_in_docker_includes_memory_cap(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _fake_ok()

    monkeypatch.setattr(docker_gate.subprocess, "run", fake_run)
    rc, out = docker_gate._run_in_docker(_ws(tmp_path), ["python", "main.py"], 5)
    assert rc == 0
    cmd = captured["cmd"]
    assert "--memory" in cmd and "512m" in cmd
    assert "--cpus" in cmd and "1" in cmd


def test_semaphore_limits_concurrency(monkeypatch, tmp_path):
    docker_gate.set_docker_concurrency(2)
    ws = _ws(tmp_path)
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def fake_run(cmd, **kw):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.03)             # 겹칠 시간을 준다
        with lock:
            state["now"] -= 1
        return _fake_ok()

    monkeypatch.setattr(docker_gate.subprocess, "run", fake_run)
    threads = [threading.Thread(
        target=lambda: docker_gate._run_in_docker(ws, ["python", "main.py"], 5))
        for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["max"] <= 2         # 동시 컨테이너 2개로 제한됨
    docker_gate.set_docker_concurrency(docker_gate.N_DOCKER)  # 원복


def test_workspace_isolation_original_untouched(monkeypatch, tmp_path):
    """리뷰 #1: 실행 중 컨테이너가 /app(=복사본)을 고쳐도 원본 워크스페이스는 안 바뀐다.

    fake_run이 마운트된 복사본 경로를 cmd에서 파싱해 거기에 쓰고 test_acceptance.py를
    덮는다(생성코드의 오염 시뮬). _run_in_docker가 끝난 뒤 원본은 그대로여야 한다.
    """
    ws = _ws(tmp_path)
    (ws / "test_acceptance.py").write_text("GOLDEN\n", encoding="utf-8")

    def fake_run(cmd, **kw):
        # cmd에서 '-v <run_root>:/app' 의 run_root를 뽑는다
        mount = cmd[cmd.index("-v") + 1]
        run_root = Path(mount.split(":/app")[0])
        (run_root / "test_acceptance.py").write_text("HACKED\n", encoding="utf-8")
        (run_root / "evil.txt").write_text("x", encoding="utf-8")
        return _fake_ok()

    monkeypatch.setattr(docker_gate.subprocess, "run", fake_run)
    docker_gate._run_in_docker(ws, ["python", "main.py"], 5)

    assert (ws / "test_acceptance.py").read_text(encoding="utf-8") == "GOLDEN\n"
    assert not (ws / "evil.txt").exists()            # 원본 오염 없음
    # 임시 복사본은 폐기됨 (원본 부모에 .sbx- 잔재 없음)
    assert not list(tmp_path.glob(".sbx-*"))
