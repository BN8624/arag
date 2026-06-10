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


def install_packages(deps_dir: Path, packages: list[str],
                     timeout: int = 240) -> tuple[bool, str]:
    """화이트리스트 패키지를 deps 디렉토리에 설치 (이 단계만 네트워크 허용).

    설치 결과는 마커 파일로 캐시 — 같은 목록이면 재설치하지 않는다.
    """
    deps_dir = Path(deps_dir).resolve()
    deps_dir.mkdir(parents=True, exist_ok=True)
    marker = deps_dir / ".installed"
    want = "\n".join(sorted(packages))
    if marker.exists() and marker.read_text(encoding="utf-8") == want:
        return True, "(packages already installed)"
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{deps_dir}:/deps", IMAGE,
        "pip", "install", "--quiet", "--no-cache-dir",
        "--target", "/deps", *sorted(packages),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, f"pip install timed out after {timeout}s"
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return False, out
    marker.write_text(want, encoding="utf-8")
    return True, out


def run_exec_gate(workdir: Path, success_signal: dict,
                  timeout: int = EXEC_TIMEOUT_SEC,
                  deps_dir: Path | None = None) -> tuple[list[dict], str]:
    """(문제 목록, 실행 로그) 반환. 문제 목록이 비면 통과."""
    workdir = Path(workdir).resolve()
    logs: list[str] = []
    issues: list[dict] = []

    rc, out = _run_in_docker(workdir, ["python", "-m", "compileall", "-q", "."],
                             timeout, deps_dir)
    logs.append(f"$ python -m compileall -q .\n(exit {rc})\n{out}".rstrip())
    if rc == -1:
        issues.append(_exec_issue("compileall timed out", out))
        return issues, "\n\n".join(logs)
    if rc != 0:
        issues.append(_exec_issue(f"byte-compilation failed (exit {rc})", out))
        return issues, "\n\n".join(logs)

    command = success_signal["command"].strip()
    expect = success_signal["expect_substring"]
    rc, out = _run_in_docker(workdir, shlex.split(command), timeout, deps_dir)
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


def run_criteria_checks(workdir: Path, checks: list[dict],
                        timeout: int = EXEC_TIMEOUT_SEC,
                        deps_dir: Path | None = None) -> list[dict]:
    """수용기준 채점. 항목별 {criterion, command, passed, detail, output_tail}.

    실패해도 회차를 멈추지 않는다 — 결과는 비평가의 증거와 REPORT 점수표로 쓰인다.
    """
    workdir = Path(workdir).resolve()
    results: list[dict] = []
    for chk in checks:
        command = str(chk.get("command", "")).strip()
        expect = str(chk.get("expect_substring", ""))
        criterion = str(chk.get("criterion", "")) or command
        if not command:
            continue
        rc, out = _run_in_docker(workdir, shlex.split(command), timeout, deps_dir)
        if rc == -1:
            passed, detail = False, f"timed out after {timeout}s"
        elif rc != 0:
            passed, detail = False, f"command failed (exit {rc})"
        elif expect and expect not in out:
            passed, detail = False, f"expected output {expect!r} not found"
        else:
            passed, detail = True, "ok"
        tail = "\n".join(out.strip().splitlines()[-5:])
        results.append({"criterion": criterion, "command": command,
                        "passed": passed, "detail": detail, "output_tail": tail})
    return results


def _exec_issue(message: str, output: str) -> dict:
    tail = output.strip().splitlines()[-15:]
    return {"file": "(run)", "line": 0, "kind": "exec-fail",
            "message": message + ("\n--- output tail ---\n" + "\n".join(tail) if tail else "")}


def _run_in_docker(workdir: Path, argv: list[str], timeout: int,
                   deps_dir: Path | None = None) -> tuple[int, str]:
    """컨테이너에서 argv 실행. (returncode, 합쳐진 출력). 타임아웃이면 (-1, 출력)."""
    name = f"arag-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "-v", f"{workdir}:/app", "-w", "/app",
    ]
    if deps_dir is not None:
        # 설치는 install_packages가 미리 해뒀다. 실행은 네트워크 차단 유지.
        cmd += ["-v", f"{Path(deps_dir).resolve()}:/deps", "-e", "PYTHONPATH=/deps"]
    cmd += [
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
