# 측정도구 수리 후 재측정: 카드 4·5·6을 31B per-file(fresh)→31B 통짜(resume)로. 31B통짜 후 정지(사람 확인).
"""하네스 수리(계약 메서드인식 + success_signal 리스트) 효과를 어려운 카드로 재측정.

옛 설계를 resume하면 깨진 success_signal을 물려받으므로 **31B가 새로 설계(fresh)** →
그 새 설계를 통짜에 resume(설계 고정, 아키텍처만 비교). 31B통짜까지만 하고 멈춘다 —
사용자 지시: "31B통짜 끝나면 확인해서 외부요인이면 멈춰". 26B 이어달리기는 별도 실행.

사용: python recheck_run.py
결과: runs/recheck_ledger.jsonl (phase·task_id·run_dir·ok)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, force_utf8_stdout

R31 = "gemma-4-31b-it"
CARDS = ["T-000004", "T-000005", "T-000006"]
LEDGER = PROJECT_ROOT / "runs" / "recheck_ledger.jsonl"


def _log(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run(args: list[str]) -> tuple[int, str]:
    env = dict(os.environ, GENERATOR_MODEL=R31)
    p = subprocess.run([sys.executable, "orchestrator.py", *args],
                       cwd=PROJECT_ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def _first_run_dir(out: str) -> str | None:
    m = re.search(r"run dir:\s*(.+)", out)
    return m.group(1).strip() if m else None


def main(argv=None) -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in CARDS}

    print(f"[RECHECK] 카드 {CARDS} — 31B per-file(fresh) → 31B 통짜(resume)")
    design_dir: dict[str, str] = {}

    print("[RECHECK] phase 31b-perfile (fresh, 새 설계)")
    for tid in CARDS:
        code, out = _run([cards[tid]["goal"], "--task-id", tid, "--mode", "cold"])
        rd = _first_run_dir(out)
        if rd:
            design_dir[tid] = rd
        _log({"t": datetime.now().isoformat(timespec="seconds"),
              "phase": "31b-perfile", "task_id": tid, "run_dir": rd,
              "ok": code == 0})
        print(f"  {tid} perfile ok={code == 0} dir={rd}")

    print("[RECHECK] phase 31b-whole (resume 새 설계)")
    for tid in CARDS:
        rd = design_dir.get(tid)
        if not rd or not (Path(rd) / "design.json").exists():
            print(f"  {tid} 설계 dir 없음 - 통짜 건너뜀")
            continue
        code, out = _run([cards[tid]["goal"], "--resume", rd, "--whole",
                          "--mode", "cold", "--no-retry"])
        _log({"t": datetime.now().isoformat(timespec="seconds"),
              "phase": "31b-whole", "task_id": tid, "resume_from": rd,
              "ok": code == 0})
        print(f"  {tid} whole ok={code == 0}")

    print(f"[RECHECK] 31B 단계 완료 — 정지. 사람 확인 후 26B 진행. 장부: {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
