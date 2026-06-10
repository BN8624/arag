"""Docker 실행 게이트.

순서:
  1. compileall - 부팅(바이트컴파일) 확인
  2. 성공 신호 커맨드 1개 실행 - exit 0 + 기대 출력 포함 확인

가드레일: 건당 타임아웃(기본 30초), stdin 차단, 네트워크 차단(--network none,
stdlib-only 규격이라 가능), 컨테이너는 --rm으로 자동 정리.
"""

import shlex
import subprocess
import uuid
from pathlib import Path

IMAGE = "python:3.12-slim"
EXEC_TIMEOUT_SEC = 30


def docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_exec_gate(workdir: Path, success_signal: dict,
                  timeout: int = EXEC_TIMEOUT_SEC) -> tuple[list[dict], str]:
    """(문제 목록, 실행 로그) 반환. 문제 목록이 비면 통과."""
    workdir = Path(workdir).resolve()
    logs: list[str] = []
    issues: list[dict] = []

    rc, out = _run_in_docker(workdir, ["python", "-m", "compileall", "-q", "."], timeout)
    logs.append(f"$ python -m compileall -q .\n(exit {rc})\n{out}".rstrip())
    if rc == -1:
        issues.append(_exec_issue("compileall timed out", out))
        return issues, "\n\n".join(logs)
    if rc != 0:
        issues.append(_exec_issue(f"byte-compilation failed (exit {rc})", out))
        return issues, "\n\n".join(logs)

    command = success_signal["command"].strip()
    expect = success_signal["expect_substring"]
    rc, out = _run_in_docker(workdir, shlex.split(command), timeout)
    logs.append(f"$ {command}\n(exit {rc})\n{out}".rstrip())
    if rc == -1:
        issues.append(_exec_issue(
            f"success-signal command timed out after {timeout}s "
            "(infinite loop or waiting for stdin?)", out))
    elif rc != 0:
        issues.append(_exec_issue(f"success-signal command failed (exit {rc})", out))
    elif expect not in out:
        issues.append(_exec_issue(
            f"command succeeded but expected output {expect!r} "
            "was not found in stdout/stderr", out))
    return issues, "\n\n".join(logs)


def _exec_issue(message: str, output: str) -> dict:
    tail = output.strip().splitlines()[-15:]
    return {"file": "(run)", "line": 0, "kind": "exec-fail",
            "message": message + ("\n--- output tail ---\n" + "\n".join(tail) if tail else "")}


def _run_in_docker(workdir: Path, argv: list[str], timeout: int) -> tuple[int, str]:
    """컨테이너에서 argv 실행. (returncode, 합쳐진 출력). 타임아웃이면 (-1, 출력)."""
    name = f"arag-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "-v", f"{workdir}:/app", "-w", "/app",
        # 컨테이너 안 coreutils timeout이 1차 방어선, subprocess timeout이 안전망
        IMAGE, "timeout", str(timeout), *argv,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout + 60,  # +60: 컨테이너 기동 여유
            stdin=subprocess.DEVNULL,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 124:  # coreutils timeout의 시간 초과 코드
            return -1, out
        return result.returncode, out
    except subprocess.TimeoutExpired as err:
        subprocess.run(["docker", "kill", name], capture_output=True,
                       stdin=subprocess.DEVNULL)
        partial = ""
        for chunk in (err.stdout, err.stderr):
            if chunk:
                partial += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
        return -1, partial
