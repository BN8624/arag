# 통과한 런의 한 attempt 코드를 카드의 solution(확장 베이스)으로 승격하는 도구 — 부품 확장의 반복 손작업 자동화
"""사용: python golem/promote_solution.py --card <slug> --run <ts> [--attempt N]  (키 안 씀)
런 디렉토리 runs/golem/<ts>/attemptNN/의 .js 파일들을 카드 solution으로 저장한다.
--attempt 생략 시 golem_ledger에서 그 런의 첫 통과(ok=True) attempt를 자동 선택.
= 다음 부품을 driver --base <slug>로 얹기 위한 준비. 목표② 재사용 도구."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
try:
    from config import force_utf8_stdout
    force_utf8_stdout()
except Exception:  # noqa: BLE001
    pass

import game_bank

LEDGER = HERE / "golem_ledger.jsonl"
RUNS = HERE.parent / "runs" / "golem"


def _first_passing_attempt(run_id):
    """장부에서 해당 런의 ok=True 첫 attempt 번호를 찾는다(없으면 None)."""
    best = None
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("run") == run_id and d.get("ok") and "attempt" in d:
                n = d["attempt"]
                if best is None or n < best:
                    best = n
    return best


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True, help="solution을 채울 카드 slug")
    ap.add_argument("--run", required=True, help="런 타임스탬프(runs/golem/<ts>)")
    ap.add_argument("--attempt", type=int, default=None, help="승격할 attempt 번호(생략=첫 통과)")
    args = ap.parse_args(argv)

    card = game_bank.get_card(args.card)
    if card is None:
        print(f"[ERR] 카드 '{args.card}' 없음")
        return 2

    att = args.attempt if args.attempt is not None else _first_passing_attempt(args.run)
    if att is None:
        print(f"[ERR] 런 '{args.run}'에 통과(ok=True) attempt가 장부에 없음")
        return 2

    adir = RUNS / args.run / f"attempt{att:02d}"
    if not adir.is_dir():
        print(f"[ERR] 디렉토리 없음: {adir}")
        return 2
    files = {p.name: p.read_text(encoding="utf-8")
             for p in sorted(adir.glob("*.js"))}
    if "main.js" not in files:
        print(f"[ERR] {adir}에 main.js 없음 (파일: {list(files)})")
        return 2

    card["solution"] = files
    game_bank.save_card(card)
    print(f"[OK] '{args.card}'.solution <- {args.run}/attempt{att:02d} "
          f"({len(files)}파일: {', '.join(files)})")
    print(f"     확장 런: python golem/driver.py --card <다음부품> --base {args.card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
