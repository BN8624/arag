"""Docker 실행 게이트.

순서:
  1. compileall - 부팅(바이트컴파일) 확인
  2. 성공 신호 커맨드 1개 실행 - exit 0 + 기대 출력 포함 확인

가드레일: 건당 타임아웃(기본 30초), stdin 차단, 네트워크 차단(--network none,
stdlib-only 규격이라 가능), 컨테이너는 --rm으로 자동 정리.
"""

import re
import shlex
import subprocess
import sys
import threading
import uuid
from pathlib import Path

IMAGE = "python:3.12-slim"
EXEC_TIMEOUT_SEC = 30

# 동시 컨테이너 상한(병렬 인프라, 결정22). 도커 단계는 짧아 병목이 아니므로
# 보수적으로 2부터. 모든 워커가 공유하는 모듈 전역 세마포어 1개.
N_DOCKER = 2
_docker_sem = threading.Semaphore(N_DOCKER)


def set_docker_concurrency(n: int) -> None:
    """동시 컨테이너 상한을 바꾼다. 워커 시작 *전*에 한 번 호출(select_run에서 주입)."""
    global _docker_sem
    _docker_sem = threading.Semaphore(n)


def _hidden_console_kwargs() -> dict:
    """Windows에서 자식 docker 프로세스가 콘솔 창을 띄우지 않게 하는 인자.

    pythonw(대시보드 백그라운드)로 돌 때 docker.exe가 회차마다 검은 창을
    깜빡이는 것 방지. 다른 OS에서는 빈 dict (동작 동일).
    """
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": si}


def docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20,
            stdin=subprocess.DEVNULL, **_hidden_console_kwargs(),
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
            errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
            **_hidden_console_kwargs())
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
    rc, out = _run_in_docker(workdir, _as_argv(command), timeout, deps_dir)
    logs.append(f"$ {command}\n(exit {rc})\n{out}".rstrip())
    if rc == -1:
        issues.append(_exec_issue(
            f"success-signal command timed out after {timeout}s "
            "(infinite loop or waiting for stdin?)", out))
    elif rc != 0:
        issues.append(_exec_issue(f"success-signal command failed (exit {rc})", out))
    else:
        missing = _substr_missing(out, expect)
        if missing:
            issues.append(_exec_issue(
                "command ran but golden output mismatch — fix these values:\n"
                + _golden_diff(out, missing), out))
    return issues, "\n\n".join(logs)


def run_pytest(workdir: Path, timeout: int = 60,
               deps_dir: Path | None = None) -> tuple[list[dict], str]:
    """31B가 출제한 test_acceptance.py를 실행. (문제 목록, 로그) 반환."""
    workdir = Path(workdir).resolve()
    rc, out = _run_in_docker(workdir, ["python", "-m", "pytest", "-q",
                                       "--tb=short", "test_acceptance.py"],
                             timeout, deps_dir)
    log = f"$ python -m pytest -q test_acceptance.py\n(exit {rc})\n{out}".rstrip()
    issues: list[dict] = []
    if rc == -1:
        issues.append(_exec_issue(f"pytest timed out after {timeout}s", out))
    elif rc == 5:
        issues.append(_exec_issue("pytest collected no tests from "
                                  "test_acceptance.py", out))
    elif rc != 0:
        # 실패한 assert 본문이 보이도록 꼬리를 넉넉히 (15줄이면 요약에서 잘림)
        issues.append(_exec_issue(f"pytest failed (exit {rc})", out,
                                  tail_lines=40))
    return issues, log


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
        expect = chk.get("expect_substring", "")
        criterion = str(chk.get("criterion", "")) or command
        if not command:
            continue
        rc, out = _run_in_docker(workdir, _as_argv(command), timeout, deps_dir)
        expect_rc = chk.get("expect_exit_code", 0)
        missing = _substr_missing(out, expect)
        if rc == -1:
            passed, detail = False, f"timed out after {timeout}s"
        elif rc != expect_rc:
            passed, detail = False, f"command failed (exit {rc}, expected {expect_rc})"
        elif missing:
            passed, detail = False, f"expected output {missing!r} not found"
        else:
            passed, detail = True, "ok"
        tail = "\n".join(out.strip().splitlines()[-5:])
        results.append({"criterion": criterion, "command": command,
                        "passed": passed, "detail": detail, "output_tail": tail})
    return results


def _substr_missing(out: str, expect) -> list[str]:
    """기대 substring(들)이 출력에 있나 검사. 문자열이면 1개, 리스트면 전부 필요.

    리스트 허용으로 brittle한 라벨-연결 문자열("Winner: Turns:") 대신 토큰별
    검사("Winner:","Turns:")가 가능 — 실제 값이 끼어들어도 통과 (하네스 버그 수정).
    빈 기대값은 통과(빈 리스트 반환).
    """
    if expect is None or expect == "":
        return []
    tokens = expect if isinstance(expect, list) else [expect]
    return [str(t) for t in tokens if str(t) and str(t) not in out]


def _golden_diff(out: str, missing: list[str], max_lines: int = 12) -> str:
    """빠진 기대 토큰('key: value')별로 출력의 실제 값을 찾아 expected-vs-actual을
    국소화한다. '없는 substring' 통짜 대신 어느 값이 어긋났는지(예: turns 23↔25)를
    바로 보여줘 자가수정이 통합 수치버그를 좁혀 잡게 한다."""
    lines: list[str] = []
    for tok in missing[:max_lines]:
        m = re.match(r"^\s*(.+?)\s*:\s*(.+?)\s*$", tok)
        if not m:                                  # 'key: value' 모양이 아니면 그대로
            lines.append(f"  expected {tok!r} - not found in output")
            continue
        key, exp = m.group(1), m.group(2)
        got = list(dict.fromkeys(                  # 같은 key의 실제 값들(중복 제거)
            re.findall(rf"{re.escape(key)}\s*:\s*(\S+)", out)))
        if got:
            shown = got[0] if len(got) == 1 else got
            lines.append(f"  {key}: expected {exp!r}, got {shown!r}")
        else:
            lines.append(f"  {key!r} not present in output (expected {exp!r})")
    extra = len(missing) - max_lines
    if extra > 0:
        lines.append(f"  ... (+{extra} more mismatches)")
    return "\n".join(lines)


def _as_argv(command: str) -> list[str]:
    """설계 커맨드를 컨테이너 argv로. '&&' 체인은 sh -c로 위임."""
    if "&&" in command:
        return ["sh", "-c", command]
    return shlex.split(command)


def _exec_issue(message: str, output: str, tail_lines: int = 15) -> dict:
    tail = output.strip().splitlines()[-tail_lines:]
    return {"file": "(run)", "line": 0, "kind": "exec-fail",
            "message": message + ("\n--- output tail ---\n" + "\n".join(tail) if tail else "")}


def _run_in_docker(workdir: Path, argv: list[str], timeout: int,
                   deps_dir: Path | None = None) -> tuple[int, str]:
    """컨테이너에서 argv 실행. (returncode, 합쳐진 출력). 타임아웃이면 (-1, 출력)."""
    name = f"arag-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--memory", "512m", "--cpus", "1",  # 폭주 1개가 VM 독식 못 하게 (결정22)
        "-v", f"{workdir}:/app", "-w", "/app",
    ]
    if deps_dir is not None:
        # 설치는 install_packages가 미리 해뒀다. 실행은 네트워크 차단 유지.
        cmd += ["-v", f"{Path(deps_dir).resolve()}:/deps", "-e", "PYTHONPATH=/deps"]
    cmd += [
        # 컨테이너 안 coreutils timeout이 1차 방어선, subprocess timeout이 안전망
        IMAGE, "timeout", str(timeout), *argv,
    ]
    with _docker_sem:  # 동시 컨테이너 수 제한 (게이트 진입에서 막음)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout + 60,  # +60: 컨테이너 기동 여유
                stdin=subprocess.DEVNULL, **_hidden_console_kwargs(),
            )
            out = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 124:  # coreutils timeout의 시간 초과 코드
                return -1, out
            return result.returncode, out
        except subprocess.TimeoutExpired as err:
            subprocess.run(["docker", "kill", name], capture_output=True,
                           stdin=subprocess.DEVNULL, **_hidden_console_kwargs())
            partial = ""
            for chunk in (err.stdout, err.stderr):
                if chunk:
                    partial += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
            return -1, partial
