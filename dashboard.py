"""생성기 대시보드 (콜 0, 읽기 전용).

runs/ 디렉토리의 events.jsonl(실시간)과 index.json(이력)을 읽어
폰에서 보기 좋은 단일 페이지로 보여준다. 생성기 코드와 완전 분리 —
런이 돌고 있는 중에 띄워도 안전하다.

사용법:
    python dashboard.py              # 0.0.0.0:8400 (Tailscale IP로 폰 접속)
    python dashboard.py --port 8500

API:
    GET /            -> HTML 대시보드 (5초 자동 갱신)
    GET /api/status  -> {"live": {...}, "history": [...]}
    GET /api/report?run=<name> -> 해당 런의 REPORT.md 텍스트
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import PROJECT_ROOT, STOP_FILE, force_utf8_stdout
from run_index import load_index, recurrence_stats

RUNS_DIR = PROJECT_ROOT / "runs"
LIVE_THRESHOLD_SEC = 120  # events.jsonl이 이 안에 갱신됐으면 "진행 중"
EVENTS_TAIL = 20
BATCH_STATE_NAME = "batch_state.json"  # batch.py가 쓰는 심장박동 파일


def _read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    events = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return events


# 정적 문구 (이벤트 -> 한 줄 한국어). 동적 값이 필요한 건 _humanize의 if가 처리.
_EVENT_TEXT = {
    "tests": "[31B] 검수 시험지 출제 중",
    "tests-written": "[31B] 검수 시험지 완성",
    "tests-skipped": "검수 시험지 생략 (실행 게이트 없음)",
    "tests-syntax-error": "[31B] 시험지에 오타 -> 다시 출제",
    "tests-regen": "시험지 자체가 불량 -> [31B] 재작성 요청",
    "tests-regen-written": "[31B] 시험지 수리 완료",
    "tests-regen-no-code": "[31B] 시험지 수리 실패 - 기존 시험지 유지",
    "tests-regen-syntax-error": "[31B] 수리본에 오타 - 기존 시험지 유지",
    "arbitration-unparseable": "[31B] 중재 판정문을 못 읽음 - 중재 무산",
    "critique-skipped-perfect": "검수 만점 - 품질심사 생략하고 바로 출하",
    "critique-lgtm": "[31B] 품질심사 합격(LGTM) - 조기 출하",
    "critique-unparseable": "[31B] 심사평을 못 읽음 - 현재 빌드 유지",
    "rollback": "수리하다 라인이 깨짐 -> 직전 합격품으로 복원",
    "score-regression": "수리 후 점수 하락 -> 직전 합격품으로 복원",
    "salvaged": "도중 중단 - 마지막 합격품으로 출하",
    "lesson-recorded": "오답노트에 실패 원인 기록",
    "pip-install-failed": "자재(패키지) 입고 실패",
    "no-progress": "같은 불량 반복 - 라인 정지",
    "budget-exhausted": "수리 한도 소진 - 라인 정지",
    "snapshot": "합격품 스냅샷 저장",
    "readme-written": "사용설명서(README) 작성 완료",
    "readme-skipped": "사용설명서 생략",
    "pyproject-written": "포장(pyproject.toml) 완료",
    "pyproject-skipped": "포장 생략",
    "index-recorded": "생산 장부에 기록",
    "design-resumed": "이전 설계도 재사용 (resume)",
    "tests-resumed": "이전 시험지 재사용 (resume)",
    "fix-no-code": "[26B] 수리 응답에 코드 없음",
    "revise-no-code": "[26B] 수정 응답에 코드 없음",
}

_PHASE_TEXT = {
    "design": "[31B] 설계 시작",
    "tests": "[31B] 검수 시험지 출제 시작",
    "implement": "[26B] 제작 시작",
}


def _humanize(e: dict) -> str:
    kind = e.get("event", "?")
    t = str(e.get("t", ""))[11:19]  # HH:MM:SS
    n = e.get("count", 0)
    if kind == "phase":
        name = e.get("name", "")
        if name == "critique":
            text = f"[31B] 품질심사 {e.get('round', '?')}/{e.get('total', '?')}라운드 시작"
        else:
            text = _PHASE_TEXT.get(name, f"단계 시작: {name}")
    elif kind == "design-accepted":
        text = f"[31B] 설계도 승인 - 부품 {len(e.get('files', []))}개"
    elif kind == "design-rejected":
        text = f"[31B] 설계도 반려 ({e.get('attempt', '?')}차) -> 재설계"
    elif kind == "file-written":
        text = f"[26B] 부품 제작: {e.get('file', '?')}"
    elif kind == "file-fixed":
        text = f"[26B] 부품 수리: {e.get('file', '?')}"
    elif kind == "file-revised":
        text = f"[26B] 심사 지적 반영: {e.get('file', '?')}"
    elif kind == "fixture-written":
        text = f"모의 자재 배치: {e.get('file', '?')}"
    elif kind == "static-issues":
        text = f"검수(도면 대조): 불량 {len(e.get('issues', []))}건 -> [26B] 수리"
    elif kind == "exec-issues":
        text = f"검수(시운전): 실패 -> [26B] {e.get('target', '?')} 수리"
    elif kind == "scoreboard":
        text = f"최종 검수 점수: {e.get('passed', '?')}/{e.get('total', '?')}"
    elif kind == "partial-pass":
        pct = round(float(e.get("rate", 0)) * 100)
        text = f"부분 합격 출하 ({pct}% 통과) - 남은 기준은 개선 대상으로"
    elif kind == "arbitration":
        text = ("[31B] 중재: 시험지가 과했다 -> 시험지 수정"
                if e.get("blame") == "test"
                else "[31B] 중재: 코드가 계약 위반 -> 표적 수리")
    elif kind == "packages-installed":
        text = "자재 입고: " + ", ".join(e.get("packages", []))
    elif kind == "lessons-injected":
        text = f"오답노트 {n}건 설계실에 전달"
    elif kind == "critique-notes-injected":
        text = f"비평노트 {n}건 작업대에 전달"
    elif kind == "critique-notes-recorded":
        text = f"비평노트 {n}건 수확"
    elif kind == "aborted":
        text = f"라인 정지: {str(e.get('reason', ''))[:60]}"
    elif kind == "error":
        text = f"공장 사고: {str(e.get('reason', ''))[:60]}"
    else:
        text = _EVENT_TEXT.get(kind, kind)
    return f"{t}  {text}"


def _latest_run_dir() -> Path | None:
    if not RUNS_DIR.exists():
        return None
    dirs = [d for d in RUNS_DIR.iterdir() if d.is_dir()]
    return max(dirs, key=lambda d: d.name) if dirs else None


def _pid_alive(pid) -> bool:
    """해당 pid의 프로세스가 살아 있는가 (배치 생존 확인)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                      False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_batch_state(runs_dir: Path) -> dict | None:
    """batch_state.json + pid 생존 확인 -> 배치 상태 dict.

    반환 필드: 파일 내용 그대로 + alive(프로세스 생존) + crashed(active라고
    적혀 있는데 프로세스가 죽음 = 비정상 종료).
    """
    path = Path(runs_dir) / BATCH_STATE_NAME
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(state, dict):
        return None
    raw_active = bool(state.get("active"))
    alive = _pid_alive(state.get("pid"))
    state["alive"] = alive
    state["active"] = raw_active and alive
    state["crashed"] = raw_active and not alive
    return state


# 라인 맵의 7개 기계: 이벤트 종류 -> (단계 인덱스, 상태)로 환산
STAGES = [("design", "설계"), ("tests", "기준"), ("implement", "조립"),
          ("static", "정적 검사"), ("exec", "시운전"),
          ("critique", "품질심사"), ("ship", "출하")]


def stage_states(events: list[dict]) -> list[dict]:
    """이벤트 흐름에서 단계별 램프 상태(pending/active/warn/done/halt)를 계산."""
    status = ["pending"] * len(STAGES)
    note = [""] * len(STAGES)
    cur = 0
    gate = 3  # 마지막으로 본 게이트 (3=정적, 4=시운전) - file-fixed 귀속용

    def mark(i: int, st: str, n: str = "") -> None:
        nonlocal cur
        cur = i
        status[i] = st
        if n:
            note[i] = n

    for e in events:
        kind = e.get("event", "")
        if kind == "phase":
            name = e.get("name", "")
            if name == "design":
                mark(0, "active")
            elif name == "tests":
                mark(1, "active")
            elif name == "implement":
                mark(2, "active")
            elif name == "critique":
                mark(5, "active",
                     f"{e.get('round', '?')}/{e.get('total', '?')}라운드")
        elif kind == "design-rejected":
            mark(0, "warn", "반려 -> 재설계")
        elif kind == "design-accepted":
            mark(0, "done", f"부품 {len(e.get('files', []))}개")
        elif kind.startswith("tests-regen") or kind == "tests-syntax-error":
            mark(1, "warn", "시험지 수리")
        elif kind in ("tests-written", "tests-skipped", "tests-resumed"):
            mark(1, "done")
        elif kind in ("file-written", "fixture-written"):
            mark(2, "active", str(e.get("file", "")))
        elif kind == "static-issues":
            mark(3, "warn", f"불량 {len(e.get('issues', []))}건")
            gate = 3
        elif kind == "exec-issues":
            mark(4, "warn", str(e.get("target", "")))
            gate = 4
        elif kind == "file-fixed":
            mark(gate, "warn", f"수리: {e.get('file', '')}")
        elif kind == "snapshot":
            mark(4, "done")
        elif kind == "file-revised":
            mark(5, "active", f"반영: {e.get('file', '')}")
        elif kind in ("critique-lgtm", "critique-skipped-perfect"):
            mark(5, "done", "합격")
        elif kind in ("rollback", "score-regression"):
            mark(5, "warn", "복원")
        elif kind == "scoreboard":
            note[5] = f"{e.get('passed', '?')}/{e.get('total', '?')}"
        elif kind in ("readme-written", "pyproject-written", "salvaged"):
            mark(6, "active")
        elif kind == "index-recorded":
            mark(6, "done", "출하 완료")
        elif kind in ("aborted", "error", "no-progress", "budget-exhausted"):
            status[cur] = "halt"
            note[cur] = str(e.get("reason", ""))[:40] or "라인 정지"
            break  # 사고 이후의 마무리 이벤트(장부 기록 등)가 램프를 덮지 않게
    for i in range(cur):
        if status[i] in ("pending", "active", "warn"):
            status[i] = "done"  # 라인이 지나갔다 = 그 단계는 결국 통과했다
    return [{"key": k, "label": label, "status": status[i], "note": note[i]}
            for i, (k, label) in enumerate(STAGES)]


def file_states(run_dir: Path, events: list[dict]) -> list[dict]:
    """부품 현황: 설계도의 파일 목록 + 이벤트로 본 파일별 마지막 상태."""
    order: list[str] = []
    state: dict[str, str] = {}
    design_path = run_dir / "design.json"
    if design_path.exists():
        try:
            design = json.loads(design_path.read_text(encoding="utf-8"))
            for f in design.get("files", []):
                name = f.get("path") if isinstance(f, dict) else str(f)
                if name:
                    order.append(str(name))
                    state[str(name)] = "WAIT"
        except (json.JSONDecodeError, OSError):
            pass
    tag = {"file-written": "OK", "file-fixed": "FIX", "file-revised": "REV"}
    for e in events:
        kind = e.get("event", "")
        name = str(e.get("file", "") or e.get("target", ""))
        if not name:
            continue
        if kind in tag:
            if name not in state:
                order.append(name)
            state[name] = tag[kind]
        elif kind == "exec-issues":
            if name not in state:
                order.append(name)
            state[name] = "FIX"
    return [{"name": n, "state": state[n]} for n in order]


def _count_json(path: Path) -> int:
    """축적 노트 파일의 항목 수 (없거나 깨졌으면 0)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    return len(data) if isinstance(data, (list, dict)) else 0


def build_status(runs_dir: Path | None = None) -> dict:
    """대시보드 한 화면 분량의 상태를 dict로. (테스트 가능한 순수 조회)"""
    global RUNS_DIR
    if runs_dir is not None:
        RUNS_DIR = Path(runs_dir)

    live: dict | None = None
    run_dir = _latest_run_dir()
    if run_dir is not None:
        events = _read_events(run_dir)
        events_path = run_dir / "events.jsonl"
        age = (time.time() - events_path.stat().st_mtime
               if events_path.exists() else None)
        desc = ""
        design_path = run_dir / "design.json"
        if design_path.exists():
            try:
                design = json.loads(design_path.read_text(encoding="utf-8"))
                desc = str(design.get("description", ""))
            except (json.JSONDecodeError, OSError):
                pass
        last_event = events[-1].get("event") if events else None
        live = {
            "run": run_dir.name,
            "description": desc,
            "running": age is not None and age < LIVE_THRESHOLD_SEC,
            "age_sec": round(age) if age is not None else None,
            "last_event": last_event,
            "has_report": (run_dir / "REPORT.md").exists(),
            "events_tail": [_humanize(e) for e in events[-EVENTS_TAIL:]],
            "stages": stage_states(events),
            "parts": file_states(run_dir, events),
        }

    history = list(reversed(load_index(RUNS_DIR)))
    total_cost = sum(e.get("cost_usd") or 0 for e in history)
    improvable = [{"run": e["run"], "idea": (e.get("idea") or "")[:60],
                   "score": e.get("score")}
                  for e in history if e.get("ok")]
    return {"live": live, "history": history,
            "total_cost_usd": round(total_cost, 4),
            "stop_after": STOP_FILE.exists(),
            "improvable": improvable,
            "recurrence": recurrence_stats(history),
            "batch": read_batch_state(RUNS_DIR),
            "knowledge": {
                "lessons": _count_json(PROJECT_ROOT / "lessons.json"),
                "critique_notes": _count_json(PROJECT_ROOT / "critique_notes.json"),
                "evaluator_notes": _count_json(
                    PROJECT_ROOT / "evaluator_mistakes.json"),
            },
            "now": datetime.now().isoformat(timespec="seconds")}


def toggle_stop() -> bool:
    """종료 예약 플래그 토글. 토글 후 상태(True=예약됨)를 반환."""
    if STOP_FILE.exists():
        STOP_FILE.unlink()
        return False
    STOP_FILE.write_text(datetime.now().isoformat(timespec="seconds"),
                         encoding="utf-8")
    return True


def _busy_reason(status: dict) -> str | None:
    """이미 뭔가 돌고 있으면 그 이유를, 아니면 None을 반환."""
    if status["live"] and status["live"]["running"]:
        return f"already running: {status['live']['run']}"
    batch = status.get("batch")
    if batch and batch.get("active"):
        return (f"batch already running "
                f"(round {batch.get('round')}/{batch.get('requested')})")
    return None


def launch_run(idea: str) -> tuple[bool, str]:
    """orchestrator를 백그라운드로 시작. (성공 여부, 메시지)."""
    idea = idea.strip()
    if not idea:
        return False, "idea is empty"
    busy = _busy_reason(build_status())
    if busy:
        return False, busy
    # 수동 시작은 명시적 의사 — 남아 있던 종료 예약은 해제
    if STOP_FILE.exists():
        STOP_FILE.unlink()
    return _spawn([sys.executable, "orchestrator.py", idea])


def improvable_runs() -> list[dict]:
    """개선 가능한 런(성공 = ok) 목록. 최신순. 드롭다운 소스."""
    out = []
    for e in reversed(load_index(RUNS_DIR)):
        if e.get("ok"):
            out.append({"run": e["run"],
                        "idea": (e.get("idea") or "")[:60],
                        "score": e.get("score")})
    return out


def launch_improve(run: str, feedback: str) -> tuple[bool, str]:
    """기존 성공 런을 개선 모드로 시작."""
    run = (run or "").strip()
    if not run or "/" in run or "\\" in run or ".." in run:
        return False, "bad run name"
    run_dir = RUNS_DIR / run
    if not run_dir.exists():
        return False, f"run not found: {run}"
    busy = _busy_reason(build_status())
    if busy:
        return False, busy
    if STOP_FILE.exists():
        STOP_FILE.unlink()
    # 개선 대상의 원래 아이디어를 그대로 넘긴다 (리포트·맥락용)
    idea = next((e.get("idea", "") for e in load_index(RUNS_DIR)
                 if e.get("run") == run), run)
    cmd = [sys.executable, "orchestrator.py",
           "--improve", str(run_dir), "--feedback", feedback or "", idea]
    return _spawn(cmd)


def launch_batch(runs) -> tuple[bool, str]:
    """자동(배치) 모드 시작: 출제기 + orchestrator 연속 생산."""
    try:
        runs = int(runs)
    except (TypeError, ValueError):
        return False, "bad runs count"
    if not 1 <= runs <= 20:
        return False, "runs must be 1-20"
    busy = _busy_reason(build_status())
    if busy:
        return False, busy
    if STOP_FILE.exists():
        STOP_FILE.unlink()
    return _spawn([sys.executable, "batch.py", "--runs", str(runs)])


def _spawn(cmd: list[str]) -> tuple[bool, str]:
    RUNS_DIR.mkdir(exist_ok=True)
    log_path = RUNS_DIR / f"launch-{datetime.now():%Y%m%d-%H%M%S}.log"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.Popen(cmd, cwd=PROJECT_ROOT, stdout=log,
                         stderr=subprocess.STDOUT, creationflags=flags)
    return True, f"started (log: {log_path.name})"


PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>generator factory</title>
<style>
:root{--bg:#14110d;--text:#ece3d0;--muted:#9b8e74;--copper:#d9822b;
 --yellow:#f1bf3a;--green:#7ed457;--red:#e0584d;--blue:#6fa8e8;--iron:#aab2b8}
*{box-sizing:border-box}
body{margin:0;color:var(--text);font-size:14px;
 font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
 background:linear-gradient(90deg,rgba(241,191,58,.03) 1px,transparent 1px),
  linear-gradient(0deg,rgba(241,191,58,.03) 1px,transparent 1px),
  radial-gradient(circle at 80% -5%,rgba(217,130,43,.14),transparent 38%),
  var(--bg);
 background-size:26px 26px,26px 26px,auto,auto}
.shell{max-width:520px;min-height:100vh;margin:0 auto;
 border-left:1px solid #241e15;border-right:1px solid #241e15}
h1,h2,h3,p{margin:0}
a{color:#e8b96a}
header{position:sticky;top:0;z-index:10;padding:10px;
 border-bottom:2px solid #3a3022;background:rgba(20,17,13,.97)}
.top{display:flex;align-items:center;justify-content:space-between;gap:8px;
 margin-bottom:8px;flex-wrap:wrap}
h1{font-size:15px;color:#f7efdd}
.conn{font-size:11px;color:var(--muted)}
.conn.bad{color:var(--red);font-weight:700}
.badge{padding:3px 8px;border:1px solid #7a6a2c;background:#332b10;
 color:#ffe69a;font-size:12px;white-space:nowrap}
.badge.on{animation:blink 2.4s infinite}
.badge.off{border-color:#4a4337;background:#241f16;color:#9b8e74;animation:none}
.badge.bad{border-color:#8f4438;background:#3a1410;color:#ffb3a8;animation:none}
@keyframes blink{0%,100%{box-shadow:0 0 0 0 rgba(241,191,58,0)}
 50%{box-shadow:0 0 10px 1px rgba(241,191,58,.35)}}
.modes{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.mode{min-height:34px;padding:4px 12px;border:1px solid #4a3d2a;
 background:#211b12;color:var(--muted);font:inherit;font-size:12px}
.mode.sel{border-color:#e8a14b;background:#4c2d0d;color:#ffe9c7;font-weight:700}
.mode.stop{margin-left:auto}
.mode.stop.armed{border-color:#8f4438;background:#3a1410;color:#ffb3a8}
textarea,select,input{width:100%;border:1px solid #4a3d2a;background:#181410;
 color:var(--text);padding:8px;font:inherit;line-height:1.35}
textarea{min-height:44px;max-height:120px;resize:vertical}
select{margin-bottom:6px}
.gorow{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;
 align-items:center;margin-top:8px}
#go{min-height:44px;border:1px solid #e8a14b;
 background:linear-gradient(180deg,#7a4a16,#4c2d0d);color:#ffe9c7;font:inherit;
 font-weight:700;text-shadow:0 1px 0 rgba(0,0,0,.5)}
#go:disabled{opacity:.45}
#msg{font-size:11px;color:var(--muted);line-height:1.35;word-break:break-all}
.resources{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;
 padding:8px 10px;border-bottom:1px solid #2c251a;background:#191510}
.res{min-height:46px;padding:6px;border:1px solid #3a3022;text-align:center;
 background:linear-gradient(180deg,#262017,#1b1610)}
.res span{display:block;font-size:10px;color:var(--muted);margin-bottom:3px}
.res strong{font-size:13px;color:#ffd97e}
.hero{padding:10px}
.strip{display:none;margin-bottom:8px;padding:8px 9px;font-size:12px;
 line-height:1.45;border:1px solid #7a6a2c;background:#2b240f;color:#ffe69a}
.strip.crashed{border-color:#8f4438;background:#3a1410;color:#ffb3a8}
.strip.finished{border-color:#4a4337;background:#201b13;color:var(--muted)}
.factory-card{border:1px solid #4a3d2a;overflow:hidden;
 background:linear-gradient(90deg,rgba(241,191,58,.04) 1px,transparent 1px),
  linear-gradient(0deg,rgba(241,191,58,.04) 1px,transparent 1px),#1a1610;
 background-size:22px 22px}
.factory-head{display:flex;align-items:center;justify-content:space-between;
 gap:8px;padding:8px 9px;border-bottom:1px solid #342b1d;
 background:rgba(30,25,17,.94)}
.factory-head h2{font-size:12px;color:#f0e6cf;white-space:nowrap;flex-shrink:0}
.factory-head span{color:var(--muted);font-size:11px;overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.map{position:relative;height:332px;overflow:hidden}
.belt{position:absolute;height:18px;border-top:1px solid #5d5138;
 border-bottom:1px solid #5d5138;
 background:repeating-linear-gradient(90deg,#4f4631 0 9px,#2a241a 9px 16px);
 animation:beltx 1.1s linear infinite}
.belt.rev{animation-direction:reverse}
.belt.vertical{width:18px;height:auto;border:0;border-left:1px solid #5d5138;
 border-right:1px solid #5d5138;
 background:repeating-linear-gradient(180deg,#4f4631 0 9px,#2a241a 9px 16px);
 animation:belty 1.1s linear infinite}
@keyframes beltx{to{background-position-x:16px}}
@keyframes belty{to{background-position-y:16px}}
.map.paused .belt{animation-play-state:paused;opacity:.55}
.map.paused .item{display:none}
.b1{left:16px;right:48px;top:52px}.b2{right:48px;top:52px;height:120px}
.b3{left:52px;right:48px;top:172px}.b4{left:52px;top:172px;height:92px}
.b5{left:52px;right:110px;top:246px}
.item{position:absolute;width:12px;height:12px;z-index:1;
 border:1px solid rgba(0,0,0,.55);background:var(--copper);
 box-shadow:0 0 7px rgba(217,130,43,.4)}
.i1{top:55px;left:20px;animation:f1 4s linear infinite}
.i2{top:55px;left:20px;animation:f1 4s linear infinite 1.3s;
 background:var(--blue)}
.i3{top:55px;right:51px;animation:f2 3.2s linear infinite .6s;
 background:var(--yellow)}
.i4{top:175px;right:60px;animation:f3 3.6s linear infinite;
 background:var(--green)}
.i5{top:175px;left:55px;animation:f4 3.4s linear infinite .8s}
@keyframes f1{0%{transform:translateX(0);opacity:0}8%,92%{opacity:1}
 100%{transform:translateX(262px);opacity:0}}
@keyframes f2{0%{transform:translateY(0);opacity:0}10%,90%{opacity:1}
 100%{transform:translateY(116px);opacity:0}}
@keyframes f3{0%{transform:translateX(0);opacity:0}10%,90%{opacity:1}
 100%{transform:translateX(-242px);opacity:0}}
@keyframes f4{0%{transform:translateY(0);opacity:0}10%,60%{opacity:1}
 80%{transform:translateY(72px) translateX(0);opacity:1}
 100%{transform:translateY(72px) translateX(40px);opacity:0}}
.machine{position:absolute;z-index:2;width:100px;min-height:58px;
 padding:6px 7px;border:1px solid #5d5138;
 background:linear-gradient(180deg,#2e2719,#1c1710);
 box-shadow:0 6px 14px rgba(0,0,0,.35)}
.machine strong{display:block;margin-bottom:3px;padding-right:18px;
 font-size:12px;color:#f5ecd6}
.machine .mnote{display:block;font-size:10px;color:var(--muted);
 line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.machine::before{content:"";position:absolute;width:14px;height:14px;right:6px;
 top:6px;border-radius:50%;border:2px solid #6d6147;background:#241e14}
.machine.pending{opacity:.55}
.machine.done{border-color:#5d7b3c}
.machine.done::before{background:var(--green);border-color:#c9f0ae}
.machine.active{border-color:var(--copper);opacity:1;
 box-shadow:0 0 0 1px rgba(217,130,43,.35),0 0 20px rgba(217,130,43,.25)}
.machine.active::before{background:var(--yellow);border-color:#ffe9a8;
 animation:lamp 1s infinite}
@keyframes lamp{0%,100%{transform:scale(1)}50%{transform:scale(1.25)}}
.machine.warn,.machine.halt{border-color:#8f4438;opacity:1}
.machine.warn::before,.machine.halt::before{background:var(--red);
 border-color:#ffb3a8}
.machine.warn::before{animation:lamp 1s infinite}
.craft{display:none;height:7px;margin-top:5px;border:1px solid #4a3d2a;
 background:#191510;overflow:hidden}
.craft>div{height:100%;width:40%;
 background:linear-gradient(90deg,var(--copper),var(--yellow));
 animation:crafting 2.6s ease-in-out infinite}
.machine.active .craft,.machine.warn .craft{display:block}
@keyframes crafting{0%{width:6%}70%{width:96%}100%{width:6%}}
.hazard{display:none;position:absolute;left:0;right:0;bottom:0;height:5px;
 background:repeating-linear-gradient(45deg,var(--yellow) 0 7px,#18130c 7px 14px);
 opacity:.85}
.machine.warn .hazard,.machine.halt .hazard{display:block}
.m-design{left:12px;top:12px}
.m-tests{left:50%;top:12px;transform:translateX(-50%)}
.m-build{right:10px;top:12px}
.m-static{right:10px;top:128px}
.m-exec{left:50%;top:128px;transform:translateX(-50%)}
.m-crit{left:12px;top:128px}
.m-ship{right:10px;top:226px;width:116px}
.crates{position:absolute;left:14px;bottom:10px;display:flex;
 align-items:flex-end;gap:4px;z-index:2}
.crate{width:16px;height:16px;border:1px solid #211a10;
 background:linear-gradient(45deg,transparent 45%,rgba(0,0,0,.45) 45% 55%,transparent 55%),
 linear-gradient(-45deg,transparent 45%,rgba(0,0,0,.45) 45% 55%,transparent 55%),#b98a3e}
.crate.tall{height:24px}
.crates b{margin-left:5px;font-size:12px;color:#ffd97e}
.map-callout{padding:8px 9px;border-top:1px solid #5a482c;background:#261d0f;
 color:#f0d8a0;font-size:12px;line-height:1.45;min-height:34px}
section{margin:0 10px 10px;border:1px solid #3a3022;
 background:rgba(31,26,18,.94)}
.section-head{display:flex;justify-content:space-between;align-items:center;
 gap:8px;padding:9px 10px;border-bottom:1px solid #342b1d}
.section-head h2{font-size:13px}
.section-head span{color:var(--muted);font-size:11px}
.feed{padding:7px 10px}
.event{display:grid;grid-template-columns:60px minmax(0,1fr);gap:8px;
 padding:7px 0;border-bottom:1px solid #2c251a;line-height:1.35;font-size:13px}
.event:last-child{border-bottom:0}
.time{color:#7d7158;font-size:11px}
.parts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;
 padding:10px}
.part{min-height:48px;padding:8px;border:1px solid #3a3022;background:#191510}
.part strong{display:block;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap;font-size:12px;margin-bottom:5px}
.part span{display:inline-block;padding:2px 6px;background:var(--iron);
 color:#14110d;font-size:11px}
.part .OK{background:var(--green)}.part .FIX{background:var(--yellow)}
.part .REV{background:var(--blue)}.part .WAIT{background:#6b6256;color:#1a1610}
.upgrades{padding:10px;display:grid;gap:8px}
.upg{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;
 align-items:center;padding:8px;border:1px solid #3a3022;background:#191510}
.upg strong{display:block;font-size:12px}
.upg small{display:block;font-size:10px;color:var(--muted);margin-top:2px}
.upg .lv{font-size:12px;color:#ffd97e;white-space:nowrap}
.runs{display:grid;gap:8px;padding:10px}
.runrow{padding:9px;border:1px solid #3a3022;background:#191510}
.runrow strong{display:block;margin-bottom:5px;font-size:12px;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.runrow .ok{color:var(--green)}.runrow .fail{color:var(--red)}
.runrow p{color:var(--muted);font-size:12px;line-height:1.45;
 word-break:break-all}
@media (max-width:390px){
 .machine{width:94px}.m-ship{width:110px}
 .resources{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body>
<div class="shell">
<header>
  <div class="top">
    <h1>generator factory</h1>
    <span class="conn" id="conn">접속 중...</span>
    <span class="badge off" id="badge">-</span>
  </div>
  <div class="modes">
    <button class="mode sel" id="m-single" onclick="setMode('single')">단일</button>
    <button class="mode" id="m-improve" onclick="setMode('improve')">개선</button>
    <button class="mode" id="m-auto" onclick="setMode('auto')">자동</button>
    <button class="mode stop" id="stopbtn" onclick="toggleStop()">종료 예약</button>
  </div>
  <div id="panel-single">
    <textarea id="idea" rows="2" placeholder="아이디어 한 줄..."></textarea>
  </div>
  <div id="panel-improve" style="display:none">
    <select id="imp-run"></select>
    <textarea id="imp-fb" rows="2"
      placeholder="개선점 (무엇을 고치거나 추가할지)..."></textarea>
  </div>
  <div id="panel-auto" style="display:none">
    <p style="font-size:11px;color:var(--muted);margin-bottom:6px">
      자동(배치) — 주제를 출제해 연속 생산. 회차 사이마다 종료예약 확인.</p>
    <label style="font-size:12px;color:var(--muted)">회차 수 (1~20):
      <input id="auto-runs" type="number" min="1" max="20" value="3"
             style="width:80px"></label>
  </div>
  <div class="gorow">
    <button id="go" onclick="go()">투입</button>
    <span id="msg"></span>
  </div>
</header>

<div class="resources">
  <div class="res"><span>출하품</span><strong id="r-ship">-</strong></div>
  <div class="res"><span>조립 매뉴얼</span><strong id="r-lessons">-</strong></div>
  <div class="res"><span>노트(비평+검수)</span><strong id="r-notes">-</strong></div>
  <div class="res"><span>누적 비용</span><strong id="r-cost">-</strong></div>
</div>

<div class="hero">
  <div class="strip" id="batchstrip"></div>
  <div class="factory-card">
    <div class="factory-head">
      <h2>라인 맵</h2><span id="runname">-</span>
    </div>
    <div class="map paused" id="map">
      <div class="belt b1"></div><div class="belt vertical b2"></div>
      <div class="belt rev b3"></div><div class="belt vertical b4"></div>
      <div class="belt b5"></div>
      <div class="item i1"></div><div class="item i2"></div>
      <div class="item i3"></div><div class="item i4"></div>
      <div class="item i5"></div>
      <div class="machine pending m-design" id="st-design" data-pos="m-design">
        <strong>설계</strong><span class="mnote">31B</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="machine pending m-tests" id="st-tests" data-pos="m-tests">
        <strong>기준</strong><span class="mnote">31B 출제</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="machine pending m-build" id="st-build" data-pos="m-build">
        <strong>조립</strong><span class="mnote">26B</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="machine pending m-static" id="st-static" data-pos="m-static">
        <strong>정적</strong><span class="mnote">AST 검사</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="machine pending m-exec" id="st-exec" data-pos="m-exec">
        <strong>시운전</strong><span class="mnote">Docker</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="machine pending m-crit" id="st-crit" data-pos="m-crit">
        <strong>품질심사</strong><span class="mnote">31B</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="machine pending m-ship" id="st-ship" data-pos="m-ship">
        <strong>출하</strong><span class="mnote">REPORT.md</span>
        <div class="craft"><div></div></div><i class="hazard"></i></div>
      <div class="crates"><span class="crate"></span>
        <span class="crate tall"></span><span class="crate"></span>
        <b id="crates-n">x0</b></div>
    </div>
    <div class="map-callout" id="callout">-</div>
  </div>
</div>

<section>
  <div class="section-head"><h2>이벤트 피드</h2><span id="feed-note"></span></div>
  <div class="feed" id="feed"></div>
</section>

<section>
  <div class="section-head"><h2>부품 현황</h2><span>파일별</span></div>
  <div class="parts" id="parts"></div>
</section>

<section>
  <div class="section-head"><h2>공장 업그레이드</h2><span id="recur"></span></div>
  <div class="upgrades">
    <div class="upg"><div><strong>조립 매뉴얼</strong>
      <small>26B가 같은 실수를 반복하지 않게 설계에 주입</small></div>
      <span class="lv" id="u-lessons">-</span></div>
    <div class="upg"><div><strong>개선 노트</strong>
      <small>출하품을 더 좋게 만드는 비평 패턴 축적</small></div>
      <span class="lv" id="u-cnotes">-</span></div>
    <div class="upg"><div><strong>검수 노트</strong>
      <small>31B 감독관의 채점 실수 교정 자료</small></div>
      <span class="lv" id="u-enotes">-</span></div>
  </div>
</section>

<section>
  <div class="section-head"><h2>생산 기록</h2><span id="hist-note"></span></div>
  <div class="runs" id="history"></div>
</section>
</div>
<script>
let lastOk = 0;
let liveBadge = {text:'-', cls:'badge off'};

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

function renderConn(){
  const c = document.getElementById('conn');
  const b = document.getElementById('badge');
  if(!lastOk){ c.textContent='접속 중...'; return; }
  const age = Math.round((Date.now()-lastOk)/1000);
  if(age > 12){
    c.textContent = age+'초째 응답 없음'; c.className='conn bad';
    b.textContent='연결 끊김'; b.className='badge bad';
  } else {
    c.textContent = '갱신 '+age+'초 전'; c.className='conn';
    b.textContent = liveBadge.text; b.className = liveBadge.cls;
  }
}

async function tick(){
  let r;
  try{ r = await (await fetch('/api/status')).json(); }
  catch(e){ renderConn(); return; }
  lastOk = Date.now();
  render(r);
  renderConn();
}

function render(r){
  const lv = r.live, bt = r.batch;
  const batchOn = !!(bt && bt.active);
  const runOn = !!(lv && lv.running);
  // 배지: 무엇이 돌고 있는지 (배치 > 단일 런 > 대기)
  if(batchOn){
    liveBadge = {text:'배치 가동 '+(bt.round||0)+'/'+(bt.requested||'?'),
                 cls:'badge on'};
  } else if(runOn){
    liveBadge = {text:'가동 중', cls:'badge on'};
  } else if(bt && bt.crashed){
    liveBadge = {text:'배치 사고', cls:'badge bad'};
  } else {
    liveBadge = {text:'대기', cls:'badge off'};
  }
  // 배치 띠
  const strip = document.getElementById('batchstrip');
  if(bt && (batchOn || bt.crashed || bt.finished)){
    let cls='strip', html='';
    const upd = bt.updated ? ' · 갱신 '+esc(String(bt.updated).slice(11,16)) : '';
    if(batchOn){
      html = '배치 '+(bt.round||0)+'/'+(bt.requested||'?')+'회차 — '
           + esc(bt.phase||'')+upd;
      const st = batchStats(r.history, bt.started);
      if(st.n) html += '<br>이번 배치: '+st.ok+'/'+st.n+' 출하 · $'
                     + st.cost.toFixed(3);
    } else if(bt.crashed){
      cls += ' crashed';
      html = '[사고] 배치가 비정상 종료됨 — 마지막 작업: '+esc(bt.phase||'?')
           + ' ('+(bt.round||0)+'/'+(bt.requested||'?')+'회차)'+upd;
    } else {
      cls += ' finished';
      html = '지난 배치: '+(bt.ok||0)+'/'+(bt.done||0)+' 출하'
           + (bt.stopped_by ? ' · 중단: '+esc(bt.stopped_by) : ' · 정상 종료')
           + (bt.finished ? ' · '+esc(String(bt.finished).slice(5,16)) : '');
    }
    strip.innerHTML = html; strip.className = cls;
    strip.style.display = 'block';
  } else strip.style.display = 'none';
  // 종료 예약 버튼
  const sb = document.getElementById('stopbtn');
  sb.textContent = r.stop_after ? '종료 예약됨' : '종료 예약';
  sb.classList.toggle('armed', !!r.stop_after);
  document.getElementById('go').disabled = batchOn || runOn;
  // 자원 카운터
  const shipped = (r.history||[]).filter(function(e){return e.ok;}).length;
  document.getElementById('r-ship').textContent = shipped;
  document.getElementById('crates-n').textContent = 'x'+shipped;
  const kn = r.knowledge||{};
  document.getElementById('r-lessons').textContent = (kn.lessons||0)+'장';
  document.getElementById('r-notes').textContent =
    ((kn.critique_notes||0)+(kn.evaluator_notes||0))+'장';
  document.getElementById('r-cost').textContent =
    '$'+(r.total_cost_usd||0).toFixed(3);
  document.getElementById('u-lessons').textContent = (kn.lessons||0)+'장';
  document.getElementById('u-cnotes').textContent = (kn.critique_notes||0)+'장';
  document.getElementById('u-enotes').textContent = (kn.evaluator_notes||0)+'장';
  const rec = r.recurrence;
  document.getElementById('recur').textContent =
    rec && rec.injected_runs ? '재발 '+rec.recurred+'/'+rec.injected_runs : '';
  // 라인 맵
  document.getElementById('map').classList.toggle('paused', !runOn && !batchOn);
  document.getElementById('runname').textContent =
    lv ? lv.run+(lv.description?' — '+lv.description:'') : '-';
  const stmap = {design:'st-design',tests:'st-tests',implement:'st-build',
                 static:'st-static',exec:'st-exec',critique:'st-crit',
                 ship:'st-ship'};
  for(const s of (lv&&lv.stages)||[]){
    const el = document.getElementById(stmap[s.key]);
    if(!el) continue;
    el.className = 'machine '+el.dataset.pos+' '+s.status;
    if(s.note) el.querySelector('.mnote').textContent = s.note;
  }
  // 콜아웃: 라인이 멈췄는데 배치가 살아 있으면 배치 단계를 보여준다
  let co = '';
  if(lv && lv.events_tail && lv.events_tail.length && runOn){
    co = esc(lv.events_tail[lv.events_tail.length-1]);
  } else if(batchOn){
    co = '회차 준비 중 — '+esc(bt.phase||'');
  } else if(lv && lv.events_tail && lv.events_tail.length){
    co = '(정지) '+esc(lv.events_tail[lv.events_tail.length-1]);
  }
  if(lv && lv.has_report)
    co += ' &nbsp;<a href="/api/report?run='+esc(lv.run)+'">REPORT.md</a>';
  document.getElementById('callout').innerHTML = co || '-';
  // 이벤트 피드 (최신 위)
  const tail = (lv&&lv.events_tail)||[];
  document.getElementById('feed-note').textContent =
    lv && lv.age_sec!=null ? '마지막 기록 '+fmtAge(lv.age_sec)+' 전' : '';
  document.getElementById('feed').innerHTML = tail.slice().reverse()
    .map(function(line){
      return '<div class="event"><span class="time">'+esc(line.slice(0,8))
           + '</span><span>'+esc(line.slice(10))+'</span></div>';
    }).join('') || '<div class="event"><span class="time">-</span>'
                 + '<span>기록 없음</span></div>';
  // 부품 현황
  document.getElementById('parts').innerHTML = ((lv&&lv.parts)||[])
    .map(function(p){
      return '<div class="part"><strong>'+esc(p.name)+'</strong><span class="'
           + esc(p.state)+'">'+esc(p.state)+'</span></div>';
    }).join('') || '<div class="part"><strong>-</strong></div>';
  // 개선 드롭다운 (선택값 보존)
  const sel = document.getElementById('imp-run');
  const keep = sel.value;
  sel.innerHTML = (r.improvable||[]).map(function(e){
    const sc = e.score&&e.score.total
      ? ' ('+e.score.passed+'/'+e.score.total+')' : '';
    return '<option value="'+esc(e.run)+'">'+esc(e.run)+sc+' — '
         + esc(e.idea)+'</option>';
  }).join('') || '<option value="">(개선 가능한 성공 런 없음)</option>';
  if(keep) sel.value = keep;
  // 생산 기록
  document.getElementById('hist-note').textContent =
    (r.history||[]).length+'건';
  document.getElementById('history').innerHTML = (r.history||[])
    .map(function(e){
      const sc = e.score&&e.score.total
        ? e.score.passed+'/'+e.score.total : '-';
      const fx = e.fixes ? (e.fixes.static||0)+'+'+(e.fixes.exec||0) : '-';
      const cost = e.cost_usd!=null ? '$'+e.cost_usd.toFixed(3) : '-';
      return '<div class="runrow"><strong><span class="'
        + (e.ok?'ok':'fail')+'">'+(e.ok?'[OK]':'[FAIL]')+'</span> '
        + esc(e.idea||e.run)+'</strong>'
        + '<p>score '+sc+' · calls '+(e.calls!=null?e.calls:'-')+' · fix '+fx
        + ' · '+cost
        + ' · <a href="/api/report?run='+esc(e.run)+'">REPORT</a>'
        + (e.ok ? ' · <a href="#" onclick="return pickImprove(\\''
                + esc(e.run)+'\\')">개선</a>' : '')
        + '</p></div>';
    }).join('') || '<div class="runrow"><p>아직 출하품 없음</p></div>';
}

function batchStats(history, since){
  let n=0, ok=0, cost=0;
  for(const e of history||[]){
    if(since && String(e.t||'') < since) continue;
    n++; if(e.ok) ok++; cost += e.cost_usd||0;
  }
  return {n:n, ok:ok, cost:cost};
}

function fmtAge(s){
  if(s < 90) return s+'초';
  if(s < 5400) return Math.round(s/60)+'분';
  return Math.round(s/3600)+'시간';
}

function pickImprove(run){
  setMode('improve');
  const sel = document.getElementById('imp-run');
  sel.value = run;
  window.scrollTo({top:0, behavior:'smooth'});
  return false;
}

let MODE = 'single';
function setMode(m){
  MODE = m;
  for(const x of ['single','improve','auto']){
    document.getElementById('m-'+x).classList.toggle('sel', x===m);
    document.getElementById('panel-'+x).style.display = x===m?'block':'none';
  }
}

async function post(path, body){
  return (await fetch(path, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body||{})})).json();
}

async function go(){
  let res;
  if(MODE==='single'){
    res = await post('/api/start', {idea: document.getElementById('idea').value});
    if(res.ok) document.getElementById('idea').value='';
  } else if(MODE==='improve'){
    res = await post('/api/improve', {
      run: document.getElementById('imp-run').value,
      feedback: document.getElementById('imp-fb').value});
    if(res.ok) document.getElementById('imp-fb').value='';
  } else {
    res = await post('/api/auto',
      {runs: document.getElementById('auto-runs').value});
  }
  document.getElementById('msg').textContent = res.message;
  tick();
}

async function toggleStop(){
  const res = await (await fetch('/api/stop-toggle', {method:'POST'})).json();
  document.getElementById('msg').textContent =
      res.stop_after ? '이번 회차까지만 돌고 멈춥니다' : '종료 예약 해제됨';
  tick();
}

tick();
setInterval(tick, 5000);
setInterval(renderConn, 1000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 콘솔 소음 제거
        pass

    def _send(self, code: int, body: str, ctype: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - http.server 규약
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, PAGE, "text/html")
        elif url.path == "/api/status":
            self._send(200, json.dumps(build_status(), ensure_ascii=False),
                       "application/json")
        elif url.path == "/api/report":
            run = parse_qs(url.query).get("run", [""])[0]
            # 경로 탈출 방지: runs/ 바로 아래 디렉토리 이름만 허용
            if not run or "/" in run or "\\" in run or ".." in run:
                self._send(400, "bad run name", "text/plain")
                return
            path = RUNS_DIR / run / "REPORT.md"
            if not path.exists():
                self._send(404, "no report", "text/plain")
                return
            self._send(200, path.read_text(encoding="utf-8"), "text/plain")
        else:
            self._send(404, "not found", "text/plain")

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def _send_result(self, ok: bool, message: str) -> None:
        self._send(200 if ok else 409,
                   json.dumps({"ok": ok, "message": message},
                              ensure_ascii=False),
                   "application/json")

    def do_POST(self):  # noqa: N802 - http.server 규약
        url = urlparse(self.path)
        if url.path == "/api/stop-toggle":
            state = toggle_stop()
            self._send(200, json.dumps({"stop_after": state}),
                       "application/json")
            return
        body = self._read_body()
        if body is None:
            self._send_result(False, "bad json")
            return
        if url.path == "/api/start":
            self._send_result(*launch_run(str(body.get("idea", ""))))
        elif url.path == "/api/improve":
            self._send_result(*launch_improve(str(body.get("run", "")),
                                              str(body.get("feedback", ""))))
        elif url.path == "/api/auto":
            self._send_result(*launch_batch(body.get("runs", 3)))
        else:
            self._send(404, "not found", "text/plain")


def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="generator dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8400)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[OK] dashboard on http://{args.host}:{args.port} "
          f"(Tailscale IP로 폰에서 접속)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
