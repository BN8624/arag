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


def test_run_in_docker_includes_memory_cap(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _fake_ok()

    monkeypatch.setattr(docker_gate.subprocess, "run", fake_run)
    rc, out = docker_gate._run_in_docker(Path("."), ["python", "-c", "pass"], 5)
    assert rc == 0
    cmd = captured["cmd"]
    assert "--memory" in cmd and "512m" in cmd
    assert "--cpus" in cmd and "1" in cmd


def test_semaphore_limits_concurrency(monkeypatch):
    docker_gate.set_docker_concurrency(2)
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
        target=lambda: docker_gate._run_in_docker(Path("."), ["x"], 5))
        for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["max"] <= 2         # 동시 컨테이너 2개로 제한됨
    docker_gate.set_docker_concurrency(docker_gate.N_DOCKER)  # 원복
