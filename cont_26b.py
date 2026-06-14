# 재측정 이어달리기: 깨끗한 새 설계(recheck)로 26B 코더/통짜 × cold/warm + 역할배정. 인프라 내성.
"""31B 재측정(recheck) 후속. 새 설계를 resume해 26B 아키텍처×cold/warm, 그다음 역할배정.

설계 고정(recheck의 31B fresh 설계) → 26B per-file/통짜 × cold/warm 비교 + 역할배정(fresh).
auto_campaign.run_phase(테스트됨) 재사용. 카드 4·5·6만.
"""

import json
import os
import sys

from config import PROJECT_ROOT, force_utf8_stdout
from auto_campaign import run_phase, _default_runner
from night_run import filter_warm_store

R31 = "gemma-4-31b-it"
R26 = "gemma-4-26b-a4b-it"
CARDS = ["T-000004", "T-000005", "T-000006"]


def recheck_design_dirs() -> dict[str, str]:
    """recheck의 31B fresh 설계 dir(basename) — resume용. _default_runner가 runs/ 붙임."""
    out: dict[str, str] = {}
    led = PROJECT_ROOT / "runs" / "recheck_ledger.jsonl"
    for l in led.read_text(encoding="utf-8").splitlines():
        d = json.loads(l)
        if d.get("phase") == "31b-perfile" and d.get("run_dir"):
            out[d["task_id"]] = os.path.basename(d["run_dir"].rstrip("/\\"))
    return out


def main() -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    dirs = recheck_design_dirs()
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in CARDS}
    print(f"[CONT] 26B 이어달리기 — 카드 {CARDS}, 설계 resume {dirs}")

    phases = [
        ("26coder-cold", {"GENERATOR_MODEL": R26}, ["--mode", "cold"], True),
        ("26whole-cold", {"GENERATOR_MODEL": R26}, ["--mode", "cold", "--whole"], True),
        ("__filter__", None, None, None),
        ("26coder-warm", {"GENERATOR_MODEL": R26}, ["--mode", "warm"], True),
        ("26whole-warm", {"GENERATOR_MODEL": R26}, ["--mode", "warm", "--whole"], True),
        ("role-26all-cold", {"GENERATOR_MODEL": R26, "CRITIC_MODEL": R26},
         ["--mode", "cold"], False),
        ("role-26head31hands-cold", {"GENERATOR_MODEL": R31, "CRITIC_MODEL": R26},
         ["--mode", "cold"], False),
    ]
    for name, env_models, extra, resume in phases:
        if name == "__filter__":
            print(f"[CONT] 노트 USE 필터: {filter_warm_store()}")
            continue
        print(f"[CONT] phase {name}")
        st = run_phase(name, env_models, extra, resume, dirs, cards,
                       _default_runner)
        print(f"[CONT] {name} -> {st}")
    print("[CONT] 완료. 장부: runs/auto_ledger.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
