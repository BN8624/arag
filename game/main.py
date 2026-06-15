# 진입점 — seed로 파티 구성 → run_battle → 결정적 리포트/트레이스 출력 (골든 생성기 겸 게임 실행)
"""사용: python main.py --seed 3 [--max-turns 100] [--trace]
--trace면 전체 이벤트 로그를 JSON으로(골든 오라클 비교용)."""

import argparse
import json
import random

from entities import make_entity
from combat import run_battle

# (name, max_hp, atk, defense, spd, skills)
HERO_POOL = [
    ("Pyro", 90, 18, 4, 12, ["ignite", "detonate", "combo_strike"]),
    ("Frost", 100, 14, 6, 10, ["frost", "ignite", "combo_strike"]),
    ("Volt", 85, 16, 3, 15, ["shock_bolt", "venom", "combo_strike"]),
    ("Tank", 140, 12, 9, 7, ["charge", "combo_strike", "venom"]),
]
ENEMY_POOL = [
    ("Goblin", 70, 13, 3, 11, ["venom", "combo_strike"]),
    ("Orc", 120, 17, 6, 8, ["shock_bolt", "detonate", "combo_strike"]),
    ("Imp", 60, 15, 2, 14, ["ignite", "frost", "detonate"]),
    ("Golem", 160, 14, 11, 5, ["combo_strike", "charge", "frost"]),
]


def _build(pool, team, n, rng):
    picked = rng.sample(pool, n)
    out = []
    for i, (name, hp, atk, df, spd, skills) in enumerate(picked, 1):
        out.append(make_entity(f"{team}{i}", name, team, hp, atk, df, spd, skills))
    return out


def build_party(seed: int):
    rng = random.Random(seed)
    n_h = rng.choice([2, 3])
    n_e = rng.choice([2, 3])
    heroes = _build(HERO_POOL, "hero", n_h, rng)
    enemies = _build(ENEMY_POOL, "enemy", n_e, rng)
    return heroes, enemies


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-turns", type=int, default=100)
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args(argv)

    heroes, enemies = build_party(args.seed)
    result = run_battle(heroes, enemies, seed=args.seed, max_turns=args.max_turns)

    if args.trace:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"Winner: {result['winner']}")
    print(f"Turns: {result['turns']}")
    print("Final HP:")
    for eid, hp in result["final_hp"].items():
        print(f"  {eid}: {hp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
