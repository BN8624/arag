# 무인 순차 캠페인: 통짜31B 완료 대기 → 26B 코더/통짜 × cold/warm → 역할배정. 인프라 내성.
"""사용자 부재 시 아키텍처×모델×cold/warm 실험을 순차로 자동 진행한다.

순서(전부 같은 설계 --resume = 설계 고정, 같은 oracle):
  0) 진행 중인 통짜31B(whole_ledger 6장) 완료 대기
  1) 26코더-cold   (26B 파일별, 노트 OFF)
  2) 26통짜-cold   (26B 한 콜, 노트 OFF)
  3) 노트 USE 필터 (warm 적재 전 1회)
  4) 26코더-warm   (26B 파일별, 노트 ON)
  5) 26통짜-warm   (26B 한 콜, 노트 ON)
  6) 역할배정(fresh, --resume 아님): 26B-단독 / 26머리+31손(swap)

인프라 내성: 런 실패해도 다음 카드로. 마스터 장부 auto_ledger.jsonl(phase별 증분).
병렬 금지 — 한 번에 하나. 26B는 빠르므로 전체 ~3시간.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout
from run_index import load_index

R31 = "gemma-4-31b-it"
R26 = "gemma-4-26b-a4b-it"
LEDGER = PROJECT_ROOT / "runs" / "auto_ledger.jsonl"
WHOLE_LEDGER = PROJECT_ROOT / "runs" / "whole_ledger.jsonl"


def design_dirs() -> dict[str, str]:
    """각 task_id의 첫 런(round-1, 설계 보유) dir. 시작 시 1회 고정."""
    seen: dict[str, str] = {}
    for e in load_index(PROJECT_ROOT / "runs"):
        t = e.get("task_id")
        if t and t not in seen and (PROJECT_ROOT / "runs" / e["run"]
                                    / "design.json").exists():
            seen[t] = e["run"]
    return seen


def _default_runner(idea, env_models, extra, resume_dir=None, task_id=None) -> int:
    env = dict(os.environ, **env_models)
    args = [sys.executable, "orchestrator.py", idea]
    if resume_dir:
        args += ["--resume", str(PROJECT_ROOT / "runs" / resume_dir), "--no-retry"]
    if task_id:
        args += ["--task-id", task_id]
    args += extra
    return subprocess.run(args, cwd=PROJECT_ROOT, env=env).returncode


def _log(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_phase(name, env_models, extra, resume, dirs, cards, runner) -> dict:
    """한 페이즈: 6장(또는 가용 카드)을 순차 실행. resume면 설계 고정, 아니면 fresh."""
    stats = {"ok": 0, "fail": 0}
    for tid in sorted(cards):
        idea = cards[tid]["goal"]
        rd = dirs.get(tid) if resume else None
        if resume and not rd:
            continue
        code = runner(idea, env_models, extra, rd, None if resume else tid)
        ok = code == 0
        stats["ok" if ok else "fail"] += 1
        _log({"t": datetime.now().isoformat(timespec="seconds"), "phase": name,
              "task_id": tid, "ok": ok, "exit_code": code})
    return stats


def wait_for_whole(target=6, now=time.monotonic, sleep=time.sleep,
                   max_wait=7200) -> bool:
    """통짜31B(whole_ledger target장) 완료 대기. True=완료, False=타임아웃."""
    start = now()
    while now() - start < max_wait:
        n = 0
        if WHOLE_LEDGER.exists():
            n = sum(1 for _ in open(WHOLE_LEDGER, encoding="utf-8"))
        if n >= target:
            return True
        sleep(30)
    return False


def main(argv=None) -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    dirs = design_dirs()
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in dirs}

    print(f"[AUTO] 설계 {len(dirs)}장 고정: {sorted(dirs)}")
    print("[AUTO] 통짜31B 완료 대기...")
    if not wait_for_whole():
        print("[AUTO] 통짜 완료 대기 타임아웃 - 그래도 진행")

    phases = [
        ("26coder-cold", {"GENERATOR_MODEL": R26}, ["--mode", "cold"], True),
        ("26whole-cold", {"GENERATOR_MODEL": R26}, ["--mode", "cold", "--whole"], True),
        ("__filter__", None, None, None),
        ("26coder-warm", {"GENERATOR_MODEL": R26}, ["--mode", "warm"], True),
        ("26whole-warm", {"GENERATOR_MODEL": R26}, ["--mode", "warm", "--whole"], True),
        # 역할배정 (fresh = 설계도 해당 구성으로 새로): 26B 단독 / 26머리+31손
        ("role-26all-cold", {"GENERATOR_MODEL": R26, "CRITIC_MODEL": R26},
         ["--mode", "cold"], False),
        ("role-26head31hands-cold", {"GENERATOR_MODEL": R31, "CRITIC_MODEL": R26},
         ["--mode", "cold"], False),
    ]
    for name, env_models, extra, resume in phases:
        if name == "__filter__":
            from night_run import filter_warm_store
            res = filter_warm_store()
            print(f"[AUTO] 노트 USE 필터: {res}")
            continue
        print(f"[AUTO] phase {name} 시작")
        st = run_phase(name, env_models, extra, resume, dirs, cards,
                       _default_runner)
        print(f"[AUTO] phase {name} 완료: {st}")
    print(f"[AUTO] 전체 완료. 장부: {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
