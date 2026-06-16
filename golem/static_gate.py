# golem JS 정적 게이트(콜0) — node 실행 전에 구문·위장(고아 모듈)·npm·Math.random을 거른다
"""ARAG 정적 게이트의 JS·경량판. 모델 콜 0(node --check만 씀). driver가 채점(실행) 전에 호출해
명백한 결함을 빨리 떨군다. 검사:
  1) main.js 존재 + 멀티파일(.js >=2)
  2) 각 파일 구문 OK (node --check)
  3) require 그래프가 main.js에서 전부 도달 가능 (고아 모듈=멀티파일 위장 차단)
  4) require 대상이 상대경로('./') 또는 Node 빌트인만 (npm 금지)
  5) Math.random 없음 (비결정성 차단)
반환: {"ok": bool, "reason": str|None, "checks": {...}}."""

import re
import subprocess
from pathlib import Path

BUILTINS = {
    "assert", "buffer", "child_process", "cluster", "console", "crypto", "dgram", "dns",
    "events", "fs", "http", "http2", "https", "net", "os", "path", "perf_hooks", "process",
    "punycode", "querystring", "readline", "stream", "string_decoder", "timers", "tls",
    "tty", "url", "util", "v8", "vm", "worker_threads", "zlib",
}
_REQ = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")


def _requires(text):
    return _REQ.findall(text)


def _resolve(target, from_file, all_names):
    """상대 require 대상을 파일명으로 해소. 빌트인/npm은 None 반환(엣지만 만든다)."""
    if not target.startswith("."):
        return None
    base = target.split("/")[-1]
    for cand in (base, base + ".js"):
        if cand in all_names:
            return cand
    return base if base.endswith(".js") else base + ".js"


def check(cdir):
    cdir = Path(cdir)
    files = {p.name: p.read_text(encoding="utf-8", errors="replace")
             for p in sorted(cdir.glob("*.js"))}
    checks = {}

    if "main.js" not in files:
        return {"ok": False, "reason": "main.js 없음", "checks": checks}
    if len(files) < 2:
        return {"ok": False, "reason": f"단일파일(멀티파일 필요): {list(files)}", "checks": checks}
    checks["multifile"] = len(files)

    # 2) 구문 검사 (node --check)
    for name in files:
        r = subprocess.run(["node", "--check", name], cwd=str(cdir),
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return {"ok": False,
                    "reason": f"구문 오류 {name}: {r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else '?'}",
                    "checks": checks}
    checks["syntax"] = "ok"

    # 4) npm 금지 (require 대상 = 상대경로 or 빌트인만)
    for name, body in files.items():
        for t in _requires(body):
            builtin = t.split("/")[0].replace("node:", "")
            if not t.startswith(".") and builtin not in BUILTINS:
                return {"ok": False, "reason": f"비-빌트인 import '{t}' ({name}) — npm 금지", "checks": checks}
    checks["no_npm"] = "ok"

    # 5) Math.random 금지
    for name, body in files.items():
        if "Math.random" in body:
            return {"ok": False, "reason": f"Math.random 사용 ({name}) — 비결정적", "checks": checks}
    checks["deterministic"] = "ok"

    # 3) require 그래프 도달성 (고아 모듈 = 멀티파일 위장)
    names = set(files)
    graph = {n: {r for t in _requires(b) if (r := _resolve(t, n, names)) in names}
             for n, b in files.items()}
    seen, stack = set(), ["main.js"]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, ()))
    orphans = names - seen
    if orphans:
        return {"ok": False,
                "reason": f"고아 모듈 {sorted(orphans)} — main.js에서 require로 도달 불가(위장)",
                "checks": checks}
    checks["reachable"] = "ok"

    return {"ok": True, "reason": None, "checks": checks}


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass
    print(json.dumps(check(sys.argv[1]), ensure_ascii=False, indent=2))
