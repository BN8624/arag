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
import subprocess
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import PROJECT_ROOT, STOP_FILE, force_utf8_stdout
from run_index import load_index

RUNS_DIR = PROJECT_ROOT / "runs"
LIVE_THRESHOLD_SEC = 120  # events.jsonl이 이 안에 갱신됐으면 "진행 중"
EVENTS_TAIL = 20


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
        }

    history = list(reversed(load_index(RUNS_DIR)))
    total_cost = sum(e.get("cost_usd") or 0 for e in history)
    return {"live": live, "history": history,
            "total_cost_usd": round(total_cost, 4),
            "stop_after": STOP_FILE.exists()}


def toggle_stop() -> bool:
    """종료 예약 플래그 토글. 토글 후 상태(True=예약됨)를 반환."""
    if STOP_FILE.exists():
        STOP_FILE.unlink()
        return False
    STOP_FILE.write_text(datetime.now().isoformat(timespec="seconds"),
                         encoding="utf-8")
    return True


def launch_run(idea: str) -> tuple[bool, str]:
    """orchestrator를 백그라운드로 시작. (성공 여부, 메시지)."""
    idea = idea.strip()
    if not idea:
        return False, "idea is empty"
    status = build_status()
    if status["live"] and status["live"]["running"]:
        return False, f"already running: {status['live']['run']}"
    # 수동 시작은 명시적 의사 — 남아 있던 종료 예약은 해제
    if STOP_FILE.exists():
        STOP_FILE.unlink()
    RUNS_DIR.mkdir(exist_ok=True)
    log_path = RUNS_DIR / f"launch-{datetime.now():%Y%m%d-%H%M%S}.log"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.Popen([sys.executable, "orchestrator.py", idea],
                         cwd=PROJECT_ROOT, stdout=log,
                         stderr=subprocess.STDOUT, creationflags=flags)
    return True, f"started (console log: {log_path.name})"


PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>generator dashboard</title>
<style>
 body{background:#111;color:#ddd;font-family:ui-monospace,Consolas,monospace;
      margin:0;padding:12px;font-size:14px}
 h1{font-size:16px;color:#7c4} h2{font-size:14px;color:#9ab;margin:18px 0 6px}
 .badge{display:inline-block;padding:1px 8px;border-radius:8px;font-size:12px}
 .run{background:#274;color:#cfc}.idle{background:#333;color:#999}
 .ok{color:#7c4}.fail{color:#e66}
 pre{background:#1a1a1a;padding:8px;border-radius:6px;overflow-x:auto;
     white-space:pre-wrap;word-break:break-all;font-size:12px;line-height:1.5}
 table{border-collapse:collapse;width:100%;font-size:12px}
 td,th{padding:4px 6px;border-bottom:1px solid #2a2a2a;text-align:left;
       white-space:nowrap}
 .idea{max-width:40vw;overflow:hidden;text-overflow:ellipsis}
 a{color:#7ae}
</style></head><body>
<h1>generator <span id="badge" class="badge idle">-</span>
    <span id="cost" style="float:right;font-size:12px;color:#999"></span></h1>
<div style="margin:10px 0">
  <textarea id="idea" rows="3" placeholder="아이디어 한 줄..."
    style="width:100%;box-sizing:border-box;background:#1a1a1a;color:#ddd;
           border:1px solid #333;border-radius:6px;padding:8px;font:inherit"></textarea>
  <button id="start" onclick="startRun()"
    style="background:#274;color:#cfc;border:0;border-radius:6px;
           padding:8px 16px;font:inherit;margin-top:4px">작업 시작</button>
  <button id="stopbtn" onclick="toggleStop()"
    style="background:#333;color:#ddd;border:0;border-radius:6px;
           padding:8px 16px;font:inherit;margin-top:4px">종료 예약</button>
  <span id="msg" style="font-size:12px;color:#999;margin-left:8px"></span>
</div>
<div id="live"></div>
<h2>history</h2>
<div id="history"></div>
<script>
async function tick(){
  let r; try{ r = await (await fetch('/api/status')).json(); }catch(e){ return; }
  const b = document.getElementById('badge');
  const lv = r.live;
  if(lv && lv.running){ b.textContent='RUNNING'; b.className='badge run'; }
  else { b.textContent='idle'; b.className='badge idle'; }
  const sb = document.getElementById('stopbtn');
  if(r.stop_after){ sb.textContent='종료 예약됨 (해제)'; sb.style.background='#a52'; }
  else { sb.textContent='종료 예약'; sb.style.background='#333'; }
  document.getElementById('start').disabled = !!(lv && lv.running);
  document.getElementById('cost').textContent =
      'total $' + (r.total_cost_usd||0).toFixed(3);
  let h = '';
  if(lv){
    h += '<h2>'+lv.run+(lv.description?' &mdash; '+lv.description:'')+'</h2>';
    h += '<pre>'+lv.events_tail.join('\\n')+'</pre>';
    if(lv.has_report)
      h += '<a href="/api/report?run='+lv.run+'">REPORT.md</a>';
  }
  document.getElementById('live').innerHTML = h;
  let t = '<table><tr><th>run</th><th>ok</th><th>score</th><th>calls</th>'+
          '<th>fix</th><th>$</th><th>idea</th></tr>';
  for(const e of r.history){
    const sc = e.score && e.score.total ? e.score.passed+'/'+e.score.total : '-';
    const fx = e.fixes ? (e.fixes.static||0)+'+'+(e.fixes.exec||0) : '-';
    t += '<tr><td><a href="/api/report?run='+e.run+'">'+e.run+'</a></td>'+
         '<td class="'+(e.ok?'ok':'fail')+'">'+(e.ok?'OK':'FAIL')+'</td>'+
         '<td>'+sc+'</td><td>'+(e.calls??'-')+'</td><td>'+fx+'</td>'+
         '<td>'+(e.cost_usd!=null?e.cost_usd.toFixed(3):'-')+'</td>'+
         '<td class="idea">'+(e.idea||'')+'</td></tr>';
  }
  document.getElementById('history').innerHTML = t+'</table>';
}
async function startRun(){
  const idea = document.getElementById('idea').value;
  const res = await (await fetch('/api/start', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({idea})})).json();
  document.getElementById('msg').textContent = res.message;
  if(res.ok) document.getElementById('idea').value='';
  tick();
}
async function toggleStop(){
  const res = await (await fetch('/api/stop-toggle', {method:'POST'})).json();
  document.getElementById('msg').textContent =
      res.stop_after ? '이번 회차까지만 돌고 멈춥니다' : '종료 예약 해제됨';
  tick();
}
tick(); setInterval(tick, 5000);
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

    def do_POST(self):  # noqa: N802 - http.server 규약
        url = urlparse(self.path)
        if url.path == "/api/start":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(400, json.dumps({"ok": False,
                                            "message": "bad json"}),
                           "application/json")
                return
            ok, message = launch_run(str(body.get("idea", "")))
            self._send(200 if ok else 409,
                       json.dumps({"ok": ok, "message": message},
                                  ensure_ascii=False),
                       "application/json")
        elif url.path == "/api/stop-toggle":
            state = toggle_stop()
            self._send(200, json.dumps({"stop_after": state}),
                       "application/json")
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
