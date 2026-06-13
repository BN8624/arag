# 통짜 비교 런: 각 카드의 round-1 설계를 --resume --whole로 31B 재구현 (파일별 분해 vs 통짜)
"""아키텍처 실험 ②: 같은 설계를 통짜(한 콜 전체)로 재구현해 파일별 분해와 비교한다.

설계 고정(--resume) + 같은 oracle → "아키텍처"만 격리. 31B 단독(generator도 31B).
인프라 내성: 실패해도 다음 카드로. 결과는 whole_ledger.jsonl + index에 mode/whole 기록.

사용: python whole_run.py   (index에서 각 카드 round-1 설계 dir을 찾아 통짜로 재구현)
"""

import json
import os
import subprocess
import sys
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout
from run_index import load_index

GEN_31B = "gemma-4-31b-it"
LEDGER = PROJECT_ROOT / "runs" / "whole_ledger.jsonl"


def round1_dirs() -> dict[str, str]:
    """index에서 각 task_id의 첫 런(round-1, 설계 보유) dir을 고른다."""
    seen: dict[str, str] = {}
    for e in load_index(PROJECT_ROOT / "runs"):
        t = e.get("task_id")
        if t and t not in seen and (PROJECT_ROOT / "runs" / e["run"]
                                    / "design.json").exists():
            seen[t] = e["run"]
    return seen


def run_whole(idea: str, resume_dir: str) -> int:
    env = dict(os.environ, GENERATOR_MODEL=GEN_31B)
    proc = subprocess.run(
        [sys.executable, "orchestrator.py", idea,
         "--resume", str(PROJECT_ROOT / "runs" / resume_dir),
         "--whole", "--mode", "cold", "--no-retry"],
        cwd=PROJECT_ROOT, env=env)
    return proc.returncode


def main() -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    dirs = round1_dirs()
    print(f"[WHOLE] 통짜 재구현 대상 {len(dirs)}장: {sorted(dirs)}")
    with BankDB() as db:
        for tid in sorted(dirs):
            card = db.get_task(tid)
            if not card:
                continue
            code = run_whole(card["goal"], dirs[tid])
            entry = {"t": datetime.now().isoformat(timespec="seconds"),
                     "task_id": tid, "resume_from": dirs[tid],
                     "arch": "whole", "exit_code": code, "ok": code == 0}
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with open(LEDGER, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"  {tid} whole ok={code == 0}")
    print(f"[DONE] 장부: {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
