# 층2 오케스트레이션 바닥선: select-best(빔) — 약한 카드를 통과까지 반복, "몇 번에 깨지나" 측정
"""결정19 층2 진입점-a. 단일패스로 약한 카드(T-5·T-7·T-8)를 N번까지 fresh 재시도하고,
게이트를 통과하는 첫 빌드를 채택(select-best with early stop)한다.

측정: 카드별 "첫 통과까지 시도 수" + 통과 여부. = 오케스트레이션 바닥선(무식한 retry로
frontier가 얼마 비용에 뚫리나). 부수효과: 실패마다 lessons 축적 → 이후 warm 캠페인 밑밥.

구성: 31단독(GENERATOR=CRITIC=31B) cold --no-retry fresh. 통짜 아님(분할이 약간 우세였음).
장부: runs/select_ledger.jsonl
"""

import json
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout
from auto_campaign import run_phase, _default_runner, R31

CARDS = ["T-000005", "T-000007", "T-000008"]  # 50런에서 <60%였던 약한 칸
CAP = 8  # 카드당 최대 시도
LEDGER = PROJECT_ROOT / "runs" / "select_ledger.jsonl"


def _log(entry: dict) -> None:
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in CARDS}
    env = {"GENERATOR_MODEL": R31, "CRITIC_MODEL": R31}
    print(f"[SELECT] select-best(cap {CAP}) 31단독 cold — 약한칸 {CARDS}")
    for tid in CARDS:
        cracked_at = None
        for attempt in range(1, CAP + 1):
            print(f"[SELECT] {tid} 시도 {attempt}/{CAP}")
            st = run_phase(f"select-{tid}", env, ["--mode", "cold", "--no-retry"],
                           False, {}, {tid: cards[tid]}, _default_runner)
            if st["ok"]:
                cracked_at = attempt
                break
        _log({"t": datetime.now().isoformat(timespec="seconds"), "task_id": tid,
              "cracked_at": cracked_at, "cap": CAP})
        msg = f"{cracked_at}번 만에 통과" if cracked_at else f"{CAP}번 내 실패"
        print(f"[SELECT] {tid} -> {msg}")
    print("[SELECT] 완료. 장부: runs/select_ledger.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
