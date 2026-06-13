# 야간 무인 캠페인: 31B 단독으로 카드×{cold,warm}×반복을 6시간 예산 안에서 돌린다 (인프라 내성)
"""6시간 무인 가동용. 31B 단독(generator도 31B)으로 안정성 확보, 느린 만큼 반복으로 채운다.

- 카드 전체 × cold 반복(예산 전반) → 노트 수확·USE 필터·warm 적재 → × warm 반복(후반).
- 인프라 내성: 런 하나 실패해도 건너뛰고 계속(조기 종료 없음). orchestrator가 콜 간격·
  백오프를 내장. bank_run의 2-strike 중단을 쓰지 않는다(6h를 살리려고).
- 시간 예산 도달 즉시 새 런 안 띄우고 종료. 매 런을 장부(jsonl)에 증분 기록.
- cold/warm은 같은 카드 재시도(self-reference, 셰이크다운 한정). mode·round 장부 기록.

사용: python night_run.py [hours] [count]   (기본 6시간, 카드 전체)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, force_utf8_stdout

GEN_31B = "gemma-4-31b-it"
LEDGER = PROJECT_ROOT / "runs" / "night_ledger.jsonl"


def _runner(args: list[str]) -> int:
    """orchestrator를 31B 단독(generator도 31B)으로 1회 완주. exit code 반환."""
    env = dict(os.environ, GENERATOR_MODEL=GEN_31B)
    proc = subprocess.run([sys.executable, "orchestrator.py", *args],
                          cwd=PROJECT_ROOT, env=env)
    return proc.returncode


def filter_warm_store(root: Path = PROJECT_ROOT) -> dict:
    """cold 수확 노트를 USE만 남기고 정리(warm 적재). 비-USE는 버려 warm 오염 방지.

    실패해도 캠페인을 막지 않는다. (kept, dropped) 카운트 반환.
    """
    from plan2_notes import classify_note
    result = {}
    for fname, textkey in (("lessons.json", "lesson"),
                           ("critique_notes.json", "issue")):
        p = root / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            kept = [e for e in data
                    if classify_note(str(e.get(textkey, ""))) == "USE"]
            p.write_text(json.dumps(kept, ensure_ascii=False, indent=2),
                         encoding="utf-8")
            result[fname] = {"kept": len(kept), "dropped": len(data) - len(kept)}
        except Exception:  # noqa: BLE001 - 필터 실패가 캠페인을 막으면 안 됨
            pass
    return result


def _log(entry: dict, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _phase(cards, mode, deadline, runner, now, ledger_path, stats):
    """deadline까지 cards를 mode로 반복 실행. round를 증가시키며 장부 기록."""
    rnd = 0
    while now() < deadline:
        rnd += 1
        for card in cards:
            if now() >= deadline:
                return
            code = runner([card["goal"], "--task-id", card["task_id"],
                           "--mode", mode])
            ok = code == 0
            stats["ok" if ok else "fail"] += 1
            _log({"t": datetime.now().isoformat(timespec="seconds"),
                  "task_id": card["task_id"], "mode": mode, "round": rnd,
                  "exit_code": code, "ok": ok}, ledger_path)


def campaign(db, count: int, budget_sec: float, runner=_runner,
             now=time.monotonic, ledger_path: Path = LEDGER,
             filter_fn=filter_warm_store, cold_fraction: float = 0.5) -> dict:
    """카드 count장을 cold(전반 예산)→필터→warm(후반)으로 무인 반복. 통계 반환."""
    task_ids = [t["task_id"] for t in db.list_tasks()][:count]
    cards = [db.get_task(t) for t in task_ids]
    start = now()
    stats = {"cold": {"ok": 0, "fail": 0}, "warm": {"ok": 0, "fail": 0},
             "filtered": None, "cards": len(cards)}

    _phase(cards, "cold", start + budget_sec * cold_fraction,
           runner, now, ledger_path, stats["cold"])
    try:
        stats["filtered"] = filter_fn()
    except Exception:  # noqa: BLE001
        pass
    _phase(cards, "warm", start + budget_sec,
           runner, now, ledger_path, stats["warm"])
    return stats


def main(argv=None) -> int:
    force_utf8_stdout()  # Windows cp949 콘솔에서 유니코드 출력 크래시 방지
    args = list(argv if argv is not None else sys.argv[1:])
    hours = float(args[0]) if args else 6.0
    count = int(args[1]) if len(args) > 1 else 9999
    from bank_db import BankDB
    print(f"[NIGHT] 31B 단독 cold/warm 캠페인 시작 - 예산 {hours}h")
    with BankDB() as db:
        if db.count() == 0:
            print("[ERROR] design_bank.sqlite 비어있음")
            return 1
        stats = campaign(db, count, hours * 3600)
    print(f"[DONE] cold {stats['cold']} / warm {stats['warm']} "
          f"/ filtered {stats['filtered']}")
    print(f"       장부: {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
