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
import re
import subprocess
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import observability
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
        score = None
        for e in events:
            if e.get("event") == "scoreboard":
                score = {"passed": e.get("passed"), "total": e.get("total")}
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
            "score": score,
            "fixes": {"static": sum(1 for e in events
                                    if e.get("event") == "static-issues"),
                      "exec": sum(1 for e in events
                                  if e.get("event") == "exec-issues")},
        }

    # 현재 캠페인(31단독 = 50런 obs)만. 옛 오염런 + 오늘 다른 구성(26all L4 등) 제외해
    # 카운트·지표가 지금 도는 것과 일치하게. (결정18 index 정리 전 임시 필터.)
    history = [e for e in reversed(load_index(RUNS_DIR))
               if e.get("generator_model") == "gemma-4-31b-it"
               and e.get("critic_model") == "gemma-4-31b-it"]
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


def _md_to_html(md: str) -> str:
    """REPORT.md를 폰에서 읽기 좋은 최소 HTML로 (외부 의존성 없음, script 없음)."""
    import html as html_mod
    out: list[str] = []
    in_code = False
    in_list = False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html_mod.escape(line))
            continue
        esc = html_mod.escape(line)
        # **굵게** 와 `코드` 만 지원 (정본은 어디까지나 REPORT.md)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        stripped = line.strip()
        if stripped.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc.strip()[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if stripped.startswith("### "):
            out.append(f"<h3>{esc.strip()[4:]}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{esc.strip()[3:]}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{esc.strip()[2:]}</h1>")
        elif stripped:
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


REPORT_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>REPORT</title><style>
body{margin:0;background:#101214;color:#eceff2;font-size:16px;line-height:1.6;
 font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",
 "Malgun Gothic",sans-serif}
main{max-width:680px;margin:0 auto;padding:18px 16px 50px}
h1{font-size:21px;margin:10px 0}h2{font-size:18px;margin:22px 0 8px;
 color:#9adfbd}h3{font-size:16px;margin:16px 0 6px}
p{margin:6px 0}ul{margin:6px 0;padding-left:22px}li{margin:3px 0}
pre{background:#1a1d21;border:1px solid #2e343b;border-radius:10px;
 padding:12px;overflow-x:auto;font-size:12.5px;line-height:1.5;
 font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
 white-space:pre-wrap;word-break:break-all}
code{background:#22262b;border-radius:5px;padding:1px 5px;font-size:.88em;
 font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
a{color:#60a5fa}.top{font-size:14px}</style></head>
<body><main><p class="top"><a href="/">&larr; 대시보드</a></p>
__BODY__
</main></body></html>"""


_OBS_CACHE: dict = {"t": 0.0, "data": None}


def obs_summary_cached(ttl: float = 60.0) -> dict:
    """관측 요약 (60초 캐시 — 런 디렉토리 전수 읽기를 폴링마다 안 하게)."""
    now = time.time()
    if _OBS_CACHE["data"] is None or now - _OBS_CACHE["t"] > ttl:
        rows = observability.classify_all(RUNS_DIR)
        _OBS_CACHE["data"] = observability.summary(rows)
        _OBS_CACHE["t"] = now
    return _OBS_CACHE["data"]


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
<title>generator</title>
<style>
:root{--bg:#101214;--card:#1a1d21;--card2:#22262b;--line:#2e343b;
 --text:#eceff2;--muted:#9aa4ae;--green:#4ade80;--amber:#fbbf24;
 --red:#f87171;--blue:#60a5fa;--accent:#34d399}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font-size:16px;
 line-height:1.5;-webkit-font-smoothing:antialiased;overflow:hidden;
 font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",
 "Malgun Gothic",sans-serif}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.85em}
.shell{max-width:520px;margin:0 auto;height:100vh;height:100dvh;
 display:flex;flex-direction:column;overflow:hidden}
#view-now{flex:1;min-height:0;display:flex;flex-direction:column;
 overflow:hidden}
#view-hist{flex:1;min-height:0;flex-direction:column;overflow:hidden}
#view-stats{flex:1;min-height:0;overflow-y:auto;
 -webkit-overflow-scrolling:touch;padding-bottom:10px}
.feedsec{flex:1;min-height:0;display:flex;flex-direction:column;
 margin-bottom:12px}
.feedsec .feed{flex:1;min-height:0;overflow-y:auto;
 -webkit-overflow-scrolling:touch}
.histsec{flex:1;min-height:0;display:flex;flex-direction:column;
 margin-bottom:12px}
.histsec .runs{flex:1;min-height:0;overflow-y:auto;
 -webkit-overflow-scrolling:touch}
#view-stats section{margin:8px 12px 0}
#view-stats .sec-head{padding:9px 12px 0}
#view-stats .statwrap{padding:2px 8px 8px}
#view-stats table.stats{font-size:12.5px}
#view-stats .kchips{padding:8px 12px 10px}
#view-stats .kchip{padding:5px 9px;font-size:12px}
h1,h2,p{margin:0}
a{color:var(--blue);text-decoration:none}
header{position:sticky;top:0;z-index:10;padding:14px 16px 12px;
 background:rgba(16,18,20,.96);backdrop-filter:blur(12px);
 border-bottom:1px solid var(--line)}
.status-row{display:flex;align-items:center;gap:10px}
.dot{width:12px;height:12px;border-radius:50%;background:#566069;flex-shrink:0}
.dot.on{background:var(--green);animation:pulse 2s infinite}
.dot.bad{background:var(--red)}
@keyframes pulse{0%,100%{box-shadow:0 0 0 3px rgba(74,222,128,.12)}
 50%{box-shadow:0 0 0 7px rgba(74,222,128,.22)}}
.status-row h1{font-size:19px;font-weight:700}
.conn{margin-left:auto;font-size:12px;color:var(--muted);white-space:nowrap}
.conn.bad{color:var(--red);font-weight:700}
.now-line{margin-top:6px;font-size:15px;color:var(--muted);overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.now-line b{color:var(--text);font-weight:600}
.round-bar{display:flex;gap:3px;margin-top:10px}
.round-bar i{flex:1;height:5px;border-radius:3px;background:var(--line)}
.round-bar i.done{background:var(--green)}
.round-bar i.cur{background:var(--amber);animation:blink 1.2s infinite}
@keyframes blink{50%{opacity:.45}}
.round-label{margin-top:5px;font-size:12px;color:var(--muted);
 display:flex;justify-content:space-between;gap:8px}
.round-label .warn{color:#ffb4b4}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;
 padding:10px 16px 0}
.tab{padding:10px 0;text-align:center;font-size:15px;font-weight:600;
 color:var(--muted);background:var(--card);border:1px solid var(--line);
 border-radius:10px;cursor:pointer}
.tab.sel{color:#06281a;background:var(--accent);border-color:var(--accent)}
.panel{padding:10px 0 4px}
.panel label{font-size:13px;color:var(--muted)}
.panel input{width:90px;margin-left:6px}
.gobtn{min-height:44px;width:96px;border:0;border-radius:12px;
 background:var(--accent);color:#06281a;font:inherit;font-size:15.5px;
 font-weight:800}
.gobtn:disabled{opacity:.4}
#msg{font-size:12px;color:var(--muted);padding:4px 0 0;word-break:break-all}
section{margin:12px 16px 0;background:var(--card);border:1px solid var(--line);
 border-radius:14px;overflow:hidden}
.sec-head{display:flex;justify-content:space-between;align-items:baseline;
 padding:13px 16px 0;gap:8px}
.sec-head h2{font-size:16px;font-weight:700;white-space:nowrap}
.sec-head span{font-size:12px;color:var(--muted);overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.nowstrip{display:flex;align-items:center;gap:11px;padding:10px 14px 12px}
.actor{width:42px;height:42px;border-radius:12px;display:grid;
 place-items:center;font-weight:800;font-size:13.5px;flex-shrink:0;
 background:#2c3138;color:var(--muted)}
.actor.on{background:var(--amber);color:#2a1c02;animation:working 1.4s infinite}
@keyframes working{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)}}
.ns-text{flex:1;min-width:0;font-size:15.5px;font-weight:700;line-height:1.4;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
 overflow:hidden}
.loopchip{padding:6px 10px;border-radius:10px;flex-shrink:0;
 background:rgba(251,191,36,.16);color:var(--amber);font-size:13px;
 font-weight:800;white-space:nowrap;text-align:center;line-height:1.3}
.loopchip small{display:block;font-size:10.5px;font-weight:600;opacity:.85}
.gates{display:flex;gap:4px;padding:0 12px 10px;flex-wrap:wrap}
.gate{display:inline-flex;align-items:center;gap:5px;padding:6px 8px;
 border-radius:9px;border:1px solid var(--line);background:var(--card2)}
.gate .ic{width:16px;height:16px;border-radius:50%;display:grid;
 place-items:center;font-size:10px;font-weight:900}
.gate b{font-size:12.5px;font-weight:700;white-space:nowrap}
.gsec{font-size:11px;color:#ffd98a;font-weight:800;margin-left:1px;
 font-variant-numeric:tabular-nums;white-space:nowrap}
.gate.pass .ic{background:rgba(74,222,128,.16);color:var(--green)}
.gate.busy{border-color:rgba(251,191,36,.5)}
.gate.busy .ic{background:var(--amber);color:#2a1c02;animation:blink 1.2s infinite}
.gate.busy small{color:#ffd98a}
.gate.fail .ic{background:rgba(248,113,113,.18);color:var(--red)}
.gate.fail{border-color:rgba(248,113,113,.45)}
.gate.wait{opacity:.5}
.gate.wait .ic{background:var(--card);color:#566069}
.meta-strip{display:grid;grid-template-columns:repeat(3,1fr);
 border-top:1px solid var(--line)}
.meta-strip div{padding:7px 0 9px;text-align:center}
.meta-strip div+div{border-left:1px solid var(--line)}
.meta-strip span{display:block;font-size:11px;color:var(--muted)}
.meta-strip b{font-size:14px;font-weight:700}
.feed{padding:6px 16px 12px}
.ev{display:grid;grid-template-columns:60px minmax(0,1fr);gap:10px;
 padding:10px 0;border-top:1px solid var(--line);font-size:16px;
 line-height:1.45}
.feed .ev:first-child{border-top:0}
.ev .t{font-size:12px;color:var(--muted);padding-top:4px;
 font-variant-numeric:tabular-nums}
.ev.hot{color:#ffd98a;font-weight:700}
.ev.hot .t{color:var(--amber)}
.elapsed{color:var(--amber);font-weight:800;white-space:nowrap}
.runs{padding:6px 0 4px}
.runrow{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;
 padding:12px 16px;border-top:1px solid var(--line);align-items:start}
.runs .runrow:first-child{border-top:0}
.score{min-width:50px;padding:5px 4px;border-radius:9px;text-align:center;
 font-weight:800;font-size:13.5px;white-space:nowrap}
.score.ok{background:rgba(74,222,128,.15);color:var(--green)}
.score.part{background:rgba(251,191,36,.15);color:var(--amber)}
.score.bad{background:rgba(248,113,113,.15);color:var(--red)}
.score.infra{background:rgba(96,165,250,.15);color:var(--blue)}
.runrow .idea{font-size:15px;font-weight:500;display:-webkit-box;
 -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.runrow .meta{grid-column:2;font-size:12.5px;color:var(--muted)}
table.stats{width:100%;border-collapse:collapse;font-size:13.5px}
table.stats th{font-size:11.5px;color:var(--muted);font-weight:600;
 text-align:left;padding:8px 6px 4px}
table.stats td{padding:7px 6px;border-top:1px solid var(--line);
 font-variant-numeric:tabular-nums}
table.stats td:first-child{max-width:130px;overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.statwrap{padding:4px 12px 12px;overflow-x:auto}
.kchips{display:flex;gap:8px;flex-wrap:wrap;padding:12px 16px 14px}
.kchip{padding:7px 12px;border-radius:10px;background:var(--card2);
 border:1px solid var(--line);font-size:13px}
.kchip b{color:#ffd97e}
.modes{display:flex;gap:6px;margin-top:10px}
.mode{flex:1;min-height:38px;border:1px solid var(--line);border-radius:10px;
 background:var(--card);color:var(--muted);font:inherit;font-size:14px;
 font-weight:600}
.mode.sel{background:var(--accent);border-color:var(--accent);color:#06281a}
.mode.stop{flex:0 0 auto;padding:0 12px}
.mode.stop.armed{border-color:rgba(248,113,113,.6);background:rgba(248,113,113,.12);
 color:#ffb4b4}
textarea,select,input{width:100%;border:1px solid var(--line);border-radius:10px;
 background:var(--bg);color:var(--text);padding:10px;font:inherit;font-size:15px}
textarea{min-height:52px;max-height:130px;resize:vertical}
select{margin-bottom:8px}
.gorow{display:grid;grid-template-columns:96px minmax(0,1fr);gap:10px;
 align-items:center;margin-top:8px}
.empty{padding:16px;color:var(--muted);font-size:14px}
</style></head><body>
<div class="shell">
<header>
  <div class="status-row">
    <span class="dot" id="dot"></span>
    <h1 id="title">접속 중…</h1>
    <span class="conn" id="conn"></span>
  </div>
  <p class="now-line" id="nowline">-</p>
  <div class="round-bar" id="roundbar" style="display:none"></div>
  <div class="round-label" id="roundlabel" style="display:none"></div>
  <div class="modes">
    <button class="mode" id="m-single" onclick="toggleMode('single')">단일</button>
    <button class="mode" id="m-improve" onclick="toggleMode('improve')">개선</button>
    <button class="mode" id="m-auto" onclick="toggleMode('auto')">자동</button>
    <button class="mode stop" id="stopbtn" onclick="confirmStop()">종료예약</button>
  </div>
  <div class="panel" id="panel-single" style="display:none">
    <textarea id="idea" rows="2" placeholder="아이디어 한 줄…"></textarea>
    <div class="gorow"><button class="gobtn" onclick="go('single')">투입</button></div>
  </div>
  <div class="panel" id="panel-improve" style="display:none">
    <select id="imp-run"></select>
    <textarea id="imp-fb" rows="2" placeholder="개선점 (무엇을 고치거나 추가할지)…"></textarea>
    <div class="gorow"><button class="gobtn" onclick="go('improve')">투입</button></div>
  </div>
  <div class="panel" id="panel-auto" style="display:none">
    <label>회차 수 (1~20):
      <input id="auto-runs" type="number" min="1" max="20" value="20"></label>
    <div class="gorow"><button class="gobtn" onclick="go('auto')">투입</button></div>
  </div>
  <div id="msg"></div>
</header>

<div class="tabs">
  <div class="tab sel" id="tab-now" onclick="setTab('now')">현황</div>
  <div class="tab" id="tab-hist" onclick="setTab('hist')">기록</div>
  <div class="tab" id="tab-stats" onclick="setTab('stats')">지표</div>
</div>

<div id="view-now">
  <section>
    <div class="sec-head"><h2>지금</h2><span id="now-run" class="mono">-</span></div>
    <div class="nowstrip">
      <span class="actor" id="ns-actor">—</span>
      <span class="ns-text" id="ns-text">대기</span>
      <span class="loopchip" id="ns-chip" style="display:none"></span>
    </div>
    <div class="gates" id="gates"></div>
    <div class="meta-strip">
      <div><span>검수 점수</span><b id="m-score">-</b></div>
      <div><span>수리</span><b id="m-fix">-</b></div>
      <div><span>마지막 기록</span><b id="m-age">-</b></div>
    </div>
  </section>

  <section class="feedsec">
    <div class="sec-head"><h2>방금 일어난 일</h2><span id="feed-note"></span></div>
    <div class="feed" id="feed"></div>
  </section>
</div>

<div id="view-hist" style="display:none">
  <section class="histsec">
    <div class="sec-head"><h2>생산 기록</h2><span id="hist-note"></span></div>
    <div class="runs" id="history"></div>
  </section>
</div>

<div id="view-stats" style="display:none">
  <section>
    <div class="sec-head"><h2>실패 관측</h2><span>limit_type · 부산물 점수</span></div>
    <div class="kchips" id="st-obs">-</div>
  </section>
  <section>
    <div class="sec-head"><h2>프롬프트 버전별</h2><span>실험 전후 비교</span></div>
    <div class="statwrap"><table class="stats" id="st-version"></table></div>
  </section>
  <section>
    <div class="sec-head"><h2>난이도(level)별</h2><span>성공률 해석 보정용</span></div>
    <div class="statwrap"><table class="stats" id="st-level"></table></div>
  </section>
  <section>
    <div class="sec-head"><h2>관찰: 카드×아키텍처 통과율</h2><span id="st-var-note"></span></div>
    <div class="statwrap"><table class="stats" id="st-variance"></table></div>
  </section>
  <section>
    <div class="sec-head"><h2>개선(improve) 판정</h2><span id="st-imp-note"></span></div>
    <div class="kchips" id="st-improve"></div>
  </section>
  <section>
    <div class="sec-head"><h2>실패 분해 · 자산</h2><span>인프라 ≠ 모델 실력</span></div>
    <div class="kchips" id="st-misc"></div>
  </section>
</div>
</div>

<script>
let lastOk = 0;
let headState = {title:'-', dot:'dot'};
let liveTicking = false;   // 진행 중 작업 경과시간 갱신 여부
let lastEvEpoch = null;    // 마지막 이벤트 시각 (클라이언트 epoch ms)

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

function fmtAge(s){
  if(s==null) return '-';
  if(s < 90) return s+'초 전';
  if(s < 5400) return Math.round(s/60)+'분 전';
  return Math.round(s/3600)+'시간 전';
}

function renderConn(){
  const c = document.getElementById('conn');
  if(!lastOk){ c.textContent='접속 중…'; return; }
  const age = Math.round((Date.now()-lastOk)/1000);
  const t = document.getElementById('title');
  const d = document.getElementById('dot');
  if(age > 12){
    c.textContent = age+'초째 응답 없음'; c.className='conn bad';
    t.textContent = '연결 끊김'; d.className = 'dot bad';
  } else {
    c.textContent = '갱신 '+age+'초 전'; c.className='conn';
    t.textContent = headState.title; d.className = headState.dot;
  }
  // 진행 중인 작업 경과시간 (피드 첫 줄 + 현재 단계 칩, 매초 갱신)
  if(liveTicking && lastEvEpoch){
    const sec = (Date.now()-lastEvEpoch)/1000;
    const el = document.getElementById('ev-elapsed');
    if(el) el.textContent = '('+fmtDur(sec)+')';
    const ge = document.getElementById('gate-elapsed');
    if(ge) ge.textContent = fmtDur(sec);
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
  // ── 헤더
  if(batchOn) headState = {title:'배치 가동 중', dot:'dot on'};
  else if(runOn) headState = {title:'가동 중', dot:'dot on'};
  else if(bt && bt.crashed) headState = {title:'배치 사고', dot:'dot bad'};
  else headState = {title:'대기', dot:'dot'};
  let nl = '';
  if(batchOn){
    nl = (bt.round||0)+'/'+(bt.requested||'?')+'회차 — <b>'+esc(bt.phase||'')+'</b>';
  } else if(runOn && lv){
    nl = '<b>단일 런:</b> '+esc(lv.description||lv.run);
  } else if(bt && bt.finished){
    nl = '지난 배치: '+(bt.ok||0)+'/'+(bt.done||0)+' 출하'
       + (bt.stopped_by ? ' · 중단: '+esc(bt.stopped_by) : ' · 정상 종료');
  } else if(lv){
    nl = '마지막 런: '+esc(lv.description||lv.run);
  }
  document.getElementById('nowline').innerHTML = nl || '-';
  // 회차 진행바
  const rb = document.getElementById('roundbar');
  const rl = document.getElementById('roundlabel');
  if(batchOn && bt.requested){
    let h = '';
    for(let i=1;i<=bt.requested;i++){
      h += '<i class="'+(i<bt.round?'done':i===bt.round?'cur':'')+'"></i>';
    }
    rb.innerHTML = h; rb.style.display='flex';
    const st = batchStats(r.history, bt.started);
    rl.innerHTML = '<span>'+st.ok+' 출하 · $'+st.cost.toFixed(3)+'</span>'
      + (r.stop_after?'<span class="warn">종료예약됨 — 이번 회차까지</span>':'');
    rl.style.display='flex';
  } else {
    rb.style.display='none';
    if(r.stop_after){
      rl.innerHTML='<span></span><span class="warn">종료예약됨</span>';
      rl.style.display='flex';
    } else rl.style.display='none';
  }
  // ── 지금 카드
  document.getElementById('now-run').textContent =
    lv ? lv.run + (lv.age_sec!=null?' · '+fmtAge(lv.age_sec):'') : '-';
  const tail = (lv&&lv.events_tail)||[];
  const last = tail.length ? tail[tail.length-1] : '';
  let actor = null;
  if(runOn){
    if(last.indexOf('[26B]')>=0) actor='26';
    else if(last.indexOf('[31B]')>=0) actor='31';
    else actor='sys';
  }
  const text = last.replace(/^\\S+\\s+/,'').replace('[26B] ','').replace('[31B] ','');
  let nsActor = null, nsText = '대기';
  if(runOn){
    nsActor = actor==='26' ? '26' : actor==='31' ? '31' : null;
    nsText = text || '진행 중';
  } else if(batchOn){
    nsActor = '31';
    nsText = '회차 준비 중 — '+(bt.phase||'');
  } else if(last){
    nsText = '대기 — 마지막: '+text;
  }
  setNow(nsActor, nsText, lv, runOn||batchOn);
  // 진행 중인 작업의 경과시간 기준점 (renderConn이 매초 갱신)
  liveTicking = runOn;
  lastEvEpoch = null;
  if(runOn && last && r.now){
    const sNow = new Date(r.now.replace(' ','T'));
    const ev = new Date(r.now.slice(0,10)+'T'+last.slice(0,8));
    let diff = (sNow - ev) / 1000;
    if(diff < -60) diff += 86400;  // 자정 넘김 보정
    if(diff >= 0) lastEvEpoch = Date.now() - diff*1000;
  }
  // ── 게이트 점검표
  const labels = {design:'설계',tests:'기준',implement:'조립',
                  static:'정적',exec:'시운전',critique:'심사',ship:'출하'};
  const cls = {done:'pass',active:'busy',warn:'fail',halt:'fail',pending:'wait'};
  const ic = {done:'\\u2713',active:'\\u25CF',warn:'!',halt:'\\u2715',pending:'\\u25CB'};
  // 지금 지나는 단계 = active, 없으면 마지막 warn (수리 중인 게이트)
  const stages = (lv&&lv.stages)||[];
  let curKey = null;
  for(const s of stages){ if(s.status==='active') curKey = s.key; }
  if(!curKey){ for(const s of stages){ if(s.status==='warn') curKey = s.key; } }
  document.getElementById('gates').innerHTML = stages
    .map(function(s){
      const isCur = runOn && s.key === curKey;
      return '<div class="gate '+(cls[s.status]||'wait')+'" title="'
        + esc(s.note||'')+'">'
        + '<span class="ic">'+ic[s.status]+'</span><b>'+labels[s.key]+'</b>'
        + (isCur ? '<span class="gsec" id="gate-elapsed"></span>' : '')
        + '</div>';
    }).join('') || '<div class="empty">기록 없음</div>';
  const sc = lv && lv.score;
  document.getElementById('m-score').textContent =
    sc && sc.total!=null ? sc.passed+'/'+sc.total : '-';
  const fx = (lv&&lv.fixes)||{};
  document.getElementById('m-fix').textContent =
    (fx.static||0)+' + '+(fx.exec||0)+'회';
  document.getElementById('m-age').textContent =
    lv && lv.age_sec!=null ? fmtAge(lv.age_sec) : '-';
  // ── 피드
  document.getElementById('feed-note').textContent =
    lv && lv.has_report ? '' : '';
  let feedHtml = tail.slice().reverse().map(function(line,i){
    const hot = i===0 && runOn;
    return '<div class="ev'+(hot?' hot':'')+'"><span class="t">'
      + esc(line.slice(0,8))+'</span><span>'
      + esc(line.slice(10).replace('[26B] ','26B가 ').replace('[31B] ','31B가 '))
      + (hot ? ' <b class="elapsed" id="ev-elapsed"></b>' : '')
      + '</span></div>';
  }).join('');
  if(lv && lv.has_report)
    feedHtml += '<div class="ev"><span class="t"></span><span>'
      + '<a href="/api/report?run='+esc(lv.run)+'&html=1">이 런의 REPORT 보기</a>'
      + '</span></div>';
  document.getElementById('feed').innerHTML =
    feedHtml || '<div class="empty">기록 없음</div>';
  // ── 종료예약 버튼 / 투입 버튼들
  const sb = document.getElementById('stopbtn');
  sb.textContent = r.stop_after ? '예약됨' : '종료예약';
  sb.classList.toggle('armed', !!r.stop_after);
  const busy = batchOn || runOn;
  document.querySelectorAll('.gobtn').forEach(function(b){ b.disabled = busy; });
  // ── 개선 드롭다운
  const sel = document.getElementById('imp-run');
  const keep = sel.value;
  sel.innerHTML = (r.improvable||[]).map(function(e){
    const s = e.score&&e.score.total?' ('+e.score.passed+'/'+e.score.total+')':'';
    return '<option value="'+esc(e.run)+'">'+esc(e.run)+s+' — '+esc(e.idea)
      +'</option>';
  }).join('') || '<option value="">(개선 가능한 성공 런 없음)</option>';
  if(keep) sel.value = keep;
  // ── 기록 탭
  document.getElementById('hist-note').textContent =
    (r.history||[]).length+'건 · 합계 $'+(r.total_cost_usd||0).toFixed(3);
  document.getElementById('history').innerHTML = (r.history||[])
    .map(rowHtml).join('') || '<div class="empty">아직 출하품 없음</div>';
  // ── 지표 탭
  renderStats(r);
}

function setNow(actor, text, lv, on){
  const a = document.getElementById('ns-actor');
  a.textContent = actor ? actor+'B' : '—';
  a.className = 'actor'+(on?' on':'');
  document.getElementById('ns-text').textContent = text;
  const chip = document.getElementById('ns-chip');
  const fx = (lv&&lv.fixes)||{};
  const n = (fx.static||0)+(fx.exec||0);
  if(on && n>0){
    chip.innerHTML = '수리<small>'+n+'회</small>'; chip.style.display='block';
  } else chip.style.display='none';
}

function fmtDur(s){
  if(s < 90) return Math.round(s)+'초';
  if(s < 5400) return Math.round(s/60)+'분';
  return (s/3600).toFixed(1)+'시간';
}

const LVL = {'T-000001':1,'T-000002':2,'T-000003':2,'T-000004':2,
             'T-000005':2,'T-000006':3,'T-000007':4,'T-000008':5};

function rowHtml(e){
  const sc = e.score||{};
  const lvb = (e.task_id && LVL[e.task_id])
    ? '<span style="color:#9adfbd;font-weight:600;margin-right:5px">L'
      + LVL[e.task_id] + '</span>' : '';
  const infra = /API call failed|INTERNAL|네트워크/.test(String(e.status||''));
  let pill, pcls;
  if(sc.total!=null && sc.passed!=null){
    pill = sc.passed+'/'+sc.total;
    pcls = !e.ok ? 'bad' : (sc.passed===sc.total ? 'ok' : 'part');
  } else if(e.ok){ pill='OK'; pcls='ok'; }
  else if(infra){ pill='인프라'; pcls='infra'; }
  else { pill='중단'; pcls='bad'; }
  const fx = e.fixes ? (e.fixes.static||0)+'+'+(e.fixes.exec||0) : '-';
  const cost = e.cost_usd!=null ? '$'+e.cost_usd.toFixed(3) : '-';
  const tag = e.improved_from ? ' <span style="color:var(--blue)">개선판</span>' : '';
  return '<div class="runrow"><span class="score '+pcls+'">'+pill+'</span>'
    + '<span class="idea">'+lvb+esc(e.idea||e.run)+tag+'</span>'
    + '<span class="meta mono">'+esc(String(e.t||'').slice(5,16))
    + ' · '+cost+' · 수리 '+fx
    + ' · <a href="/api/report?run='+esc(e.run)+'&html=1">REPORT</a>'
    + (e.ok ? ' · <a href="#" onclick="return pickImprove(\\''+esc(e.run)
            + '\\')">개선</a>' : '')
    + '</span></div>';
}

function renderStats(r){
  const hist = r.history||[];
  // 프롬프트 버전별
  const byV = {};
  for(const e of hist){
    const v = e.prompt_version || '(버전 기록 전)';
    const b = byV[v] = byV[v]||{n:0,ok:0,sp:0,st:0,cost:0,infra:0};
    b.n++; if(e.ok) b.ok++;
    if(e.score&&e.score.total){ b.sp+=e.score.passed; b.st+=e.score.total; }
    b.cost += e.cost_usd||0;
    if(/API call failed|INTERNAL/.test(String(e.status||''))) b.infra++;
  }
  let h = '<tr><th>버전</th><th>n</th><th>OK</th><th>점수</th><th>$</th></tr>';
  for(const v of Object.keys(byV)){
    const b = byV[v];
    h += '<tr><td title="'+esc(v)+'">'+esc(v)+'</td><td>'+b.n+'</td>'
      + '<td>'+Math.round(100*b.ok/b.n)+'%</td>'
      + '<td>'+(b.st?Math.round(100*b.sp/b.st)+'%':'-')+'</td>'
      + '<td>'+b.cost.toFixed(2)+'</td></tr>';
  }
  document.getElementById('st-version').innerHTML = h;
  // level별
  const byL = {};
  for(const e of hist){
    const l = e.level!=null ? 'L'+e.level : '(없음)';
    const b = byL[l] = byL[l]||{n:0,ok:0};
    b.n++; if(e.ok) b.ok++;
  }
  let h2 = '<tr><th>난이도</th><th>n</th><th>OK</th></tr>';
  for(const l of Object.keys(byL).sort()){
    h2 += '<tr><td>'+l+'</td><td>'+byL[l].n+'</td>'
       + '<td>'+Math.round(100*byL[l].ok/byL[l].n)+'%</td></tr>';
  }
  document.getElementById('st-level').innerHTML = h2;
  // 관찰: 카드×아키텍처 통과율 (분할 vs 통짜) — 결정17 frontier 관찰
  const byCard = {}; let cardN=0, cardOk=0;
  for(const e of hist){
    if(!e.task_id) continue;
    // 현재 31단독 관찰 캠페인만 (오늘 26all L4 등 다른 구성과 안 섞이게)
    if(e.generator_model!=='gemma-4-31b-it'||e.critic_model!=='gemma-4-31b-it') continue;
    cardN++; if(e.ok) cardOk++;
    const c = byCard[e.task_id] = byCard[e.task_id]||{pf:{p:0,n:0},wh:{p:0,n:0}};
    const slot = e.whole ? c.wh : c.pf;
    slot.n++; if(e.ok) slot.p++;
  }
  const cell = s => s.n ? (s.p+'/'+s.n+' '+Math.round(100*s.p/s.n)+'%') : '-';
  let hv = '<tr><th>카드</th><th>분할</th><th>통짜</th></tr>';
  for(const c of Object.keys(byCard).sort()){
    const b = byCard[c];
    hv += '<tr><td>'+esc(c.slice(-2))+'</td><td>'+cell(b.pf)+'</td>'
       + '<td>'+cell(b.wh)+'</td></tr>';
  }
  document.getElementById('st-variance').innerHTML = hv;
  document.getElementById('st-var-note').textContent =
    cardN+'런 · 전체 '+(cardN?Math.round(100*cardOk/cardN):0)+'%';
  // improve 판정
  const iv = {IMPROVED:0,'NO-GAIN':0,REGRESSED:0};
  let impTotal = 0;
  for(const e of hist){
    const s = String(e.improvement||'');
    for(const k of Object.keys(iv)) if(s.indexOf(k)===0){ iv[k]++; impTotal++; }
  }
  document.getElementById('st-imp-note').textContent = impTotal+'건';
  document.getElementById('st-improve').innerHTML =
    '<span class="kchip">개선 성공 <b>'+iv.IMPROVED+'</b></span>'
    + '<span class="kchip">무이득 <b>'+iv['NO-GAIN']+'</b></span>'
    + '<span class="kchip">회귀 <b>'+iv.REGRESSED+'</b></span>';
  // 실패 분해 + 자산
  let infra=0, abort=0;
  for(const e of hist){
    if(e.ok) continue;
    if(/API call failed|INTERNAL/.test(String(e.status||''))) infra++;
    else abort++;
  }
  const kn = r.knowledge||{};
  const rec = r.recurrence||{};
  document.getElementById('st-misc').innerHTML =
    '<span class="kchip">인프라 실패 <b>'+infra+'</b></span>'
    + '<span class="kchip">능력 실패 <b>'+abort+'</b></span>'
    + (rec.injected_runs?'<span class="kchip">오답 재발 <b>'+rec.recurred+'/'
       +rec.injected_runs+'</b></span>':'')
    + '<span class="kchip">조립 매뉴얼 <b>'+(kn.lessons||0)+'장</b></span>'
    + '<span class="kchip">개선 노트 <b>'+(kn.critique_notes||0)+'장</b></span>'
    + '<span class="kchip">검수 노트 <b>'+(kn.evaluator_notes||0)+'장</b></span>';
}

function batchStats(history, since){
  let n=0, ok=0, cost=0;
  for(const e of history||[]){
    if(since && String(e.t||'') < since) continue;
    n++; if(e.ok) ok++; cost += e.cost_usd||0;
  }
  return {n:n, ok:ok, cost:cost};
}

let TAB = 'now';
function setTab(t){
  TAB = t;
  for(const x of ['now','hist','stats']){
    document.getElementById('tab-'+x).classList.toggle('sel', x===t);
    document.getElementById('view-'+x).style.display =
      x!==t ? 'none' : (x==='stats' ? 'block' : 'flex');
  }
  if(t==='stats') loadObs();
}

async function loadObs(){
  let o;
  try{ o = await (await fetch('/api/obs')).json(); }catch(e){ return; }
  const L = {MODEL_LIMIT:'모델 한계',LOOP_LIMIT:'루프 한계',
             SPEC_LIMIT:'스펙 한계',INFRA_LIMIT:'인프라',UNKNOWN:'미분류'};
  let h = '';
  for(const k of Object.keys(L)){
    const n = (o.by_limit||{})[k]||0;
    if(n) h += '<span class="kchip">'+L[k]+' <b>'+n+'</b></span>';
  }
  const q = o.by_quality||{};
  h += '<span class="kchip">좋은 실패 <b>'+(q.good||0)+'</b></span>'
    + '<span class="kchip">junk <b>'+(q.junk||0)+'</b>'
    + (o.junk_rate!=null?' ('+Math.round(o.junk_rate*100)+'%)':'')+'</span>'
    + (o.avg_artifact_score!=null
       ? '<span class="kchip">부산물 점수 <b>'+o.avg_artifact_score+'</b></span>' : '')
    + (o.cost_per_useful_artifact!=null
       ? '<span class="kchip">유용 부산물당 <b>$'+o.cost_per_useful_artifact
         +'</b></span>' : '');
  document.getElementById('st-obs').innerHTML = h || '-';
}

let OPEN = null;  // 열려 있는 투입 패널 (단일/개선/자동 중 하나)
function toggleMode(m){
  OPEN = (OPEN === m) ? null : m;
  for(const x of ['single','improve','auto']){
    document.getElementById('m-'+x).classList.toggle('sel', x===OPEN);
    document.getElementById('panel-'+x).style.display =
      x===OPEN ? 'block' : 'none';
  }
  if(!OPEN) document.getElementById('msg').textContent = '';
}

function pickImprove(run){
  setTab('now');
  if(OPEN !== 'improve') toggleMode('improve');
  document.getElementById('imp-run').value = run;
  return false;
}

async function confirmStop(){
  const armed = document.getElementById('stopbtn').classList.contains('armed');
  const q = armed ? '종료 예약을 해제할까요?'
                  : '정말 종료하시겠습니까?\\n진행 중인 회차까지만 돌고 멈춥니다.';
  if(!confirm(q)) return;
  toggleStop();
}

async function post(path, body){
  return (await fetch(path, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body||{})})).json();
}

async function go(mode){
  let res;
  if(mode==='single'){
    res = await post('/api/start', {idea: document.getElementById('idea').value});
    if(res.ok) document.getElementById('idea').value='';
  } else if(mode==='improve'){
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

if(location.hash==='#hist'||location.hash==='#stats') setTab(location.hash.slice(1));
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
        elif url.path == "/api/obs":
            self._send(200, json.dumps(obs_summary_cached(),
                                       ensure_ascii=False),
                       "application/json")
        elif url.path == "/api/report":
            qs = parse_qs(url.query)
            run = qs.get("run", [""])[0]
            # 경로 탈출 방지: runs/ 바로 아래 디렉토리 이름만 허용
            if not run or "/" in run or "\\" in run or ".." in run:
                self._send(400, "bad run name", "text/plain")
                return
            path = RUNS_DIR / run / "REPORT.md"
            if not path.exists():
                self._send(404, "no report", "text/plain")
                return
            md = path.read_text(encoding="utf-8")
            if qs.get("html", [""])[0]:
                self._send(200, REPORT_PAGE.replace("__BODY__", _md_to_html(md)),
                           "text/html")
            else:
                self._send(200, md, "text/plain")
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
