# golem Phase5 캠페인 — 주제 10개를 순차로: 31B 자율 오라클 설계 → 독립 합의 게이트 → 합의율 측정
"""사용: python golem/campaign.py [--tries 3] [--limit N]   (★대량 키 — 사용자 go로만)
각 주제마다 oracle_design(31B 설계)→ 성공 시 driver(독립 11개 합의 게이트). 합의율·설계 실패를
campaign_ledger.jsonl에 장부화. 측정축 = 주제별 설계 성공률 / 합의율 분포 / 자율 신뢰 통과율.
무료모델×자율오라클 한계 지도(시뮬·전략류는 창발적 통합이라 합의율이 갈릴 것으로 예상)."""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import oracle_design
import driver as driver_mod
from config import force_utf8_stdout

GOLEM_LEDGER = HERE / "golem_ledger.jsonl"
CAMP_LEDGER = HERE / "campaign_ledger.jsonl"

# (slug, 주제문구) — META가 결정성·멀티파일·평면출력을 강제하므로 주제는 핵심 메카닉만 준다.
THEMES = [
    ("auto-snake",
     "a deterministic Snake game on a grid"),
    ("auto-sims",
     "a deterministic life-simulation (The Sims-like): one Sim has needs (hunger, energy, mood) "
     "that change as it performs a fixed schedule of actions over discrete ticks"),
    ("auto-simcity",
     "a deterministic city-building simulation (SimCity-like): zones are placed on a grid via a "
     "fixed command sequence; population and budget update each tick by fixed rules"),
    ("auto-ck",
     "a deterministic dynasty-succession simulation (Crusader Kings-like): characters age and die "
     "over years and titles pass down by a fixed succession rule"),
    ("auto-sangokushi",
     "a deterministic territory-conquest strategy (Romance of the Three Kingdoms-like): factions "
     "with cities and troops process a fixed sequence of orders (attack/develop) over turns"),
    ("auto-footmgr",
     "a deterministic football league simulation (Football Manager-like): teams with ratings play "
     "a fixed fixture list; each match result is computed deterministically from ratings; output "
     "the final league table"),
    ("auto-idle",
     "a deterministic idle/incremental game: a resource accrues per tick at a rate that increases "
     "with a fixed sequence of upgrade purchases"),
    ("auto-autobattler",
     "a deterministic auto-battler: two fixed teams of units fight automatically until one side is "
     "wiped out"),
    ("auto-towerdef",
     "a deterministic tower-defense: enemies walk a fixed path in waves; towers at fixed positions "
     "deal damage each tick; output kills and leaks"),
    ("auto-cardbattle",
     "a deterministic deck-based card battle: two players play cards from fixed ordered decks; "
     "card effects resolve deterministically until someone loses"),
]


def _last_summary():
    """golem_ledger 마지막 summary 줄(방금 끝난 게이트 런)."""
    last = None
    with open(GOLEM_LEDGER, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("summary"):
                last = d
    return last


def _camp_log(entry):
    with open(CAMP_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tries", type=int, default=3, help="오라클 설계 최대 시도/주제")
    ap.add_argument("--limit", type=int, default=None, help="처음 N개 주제만(점검용)")
    ap.add_argument("--start", type=int, default=1,
                    help="N번 주제부터 이어서(1-based, resume용. 앞 N-1개 건너뜀)")
    args = ap.parse_args(argv)
    force_utf8_stdout()

    themes = THEMES[:args.limit] if args.limit else THEMES
    start = max(1, args.start)
    themes = themes[start - 1:]          # --start로 앞 주제 건너뛰기(resume)
    camp_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"[CAMPAIGN {camp_id}] 주제 {len(themes)}개"
          f"{f' (전체 {len(THEMES)}개 중 {start}번부터)' if start > 1 else ''}"
          f" — 자율 오라클 설계 + 독립 합의 게이트\n")

    results = []
    for i, (slug, theme) in enumerate(themes, start):
        print(f"\n===== [{i}/{len(THEMES)}] {slug} =====")
        t0 = time.time()
        # 1) 31B 자율 오라클 설계
        rc = oracle_design.main(["--theme", theme, "--slug", slug, "--tries", str(args.tries)])
        if rc != 0:
            row = {"camp": camp_id, "slug": slug, "design_ok": False,
                   "passed": None, "attempts": None, "sec": round(time.time() - t0)}
            _camp_log(row); results.append(row)
            print(f"  -> 설계 실패, 다음 주제로")
            continue
        # 2) 독립 합의 게이트
        driver_mod.main(["--card", slug])
        s = _last_summary() or {}
        row = {"camp": camp_id, "slug": slug, "design_ok": True,
               "passed": s.get("passed"), "attempts": s.get("attempts"),
               "cracked_at": s.get("cracked_at"), "cost": s.get("cost_usd_total"),
               "sec": round(time.time() - t0)}
        _camp_log(row); results.append(row)
        print(f"  -> 합의 {row['passed']}/{row['attempts']}")

    # 집계
    print(f"\n\n===== CAMPAIGN {camp_id} 결과 =====")
    designed = [r for r in results if r["design_ok"]]
    print(f"설계 성공: {len(designed)}/{len(results)}")
    print(f"{'slug':20} {'설계':5} {'합의':8}")
    for r in results:
        cons = f"{r['passed']}/{r['attempts']}" if r["design_ok"] and r["passed"] is not None else "-"
        print(f"{r['slug']:20} {'OK' if r['design_ok'] else 'FAIL':5} {cons:8}")
    print(f"\n장부: {CAMP_LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
