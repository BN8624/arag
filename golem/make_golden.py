# game/ 레퍼런스로 golem 채점용 골든(시나리오 파티 정의 + 정답 결과)을 생성·검증한다
"""사용: python golem/make_golden.py
T-000012 오라클(frozen/T-000012/workspace/test_acceptance.py)과 동일한 4 고정 시나리오를
game/ 레퍼런스(seed 53/3/0/45)로 재생성한다. 파티 정의 = JS 워커에게 줄 입력,
golden(winner/turns/final_hp) = 채점용 정답(워커엔 비노출). 박힌 골든과 일치해야 OK."""

import json
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent / "game"
sys.path.insert(0, str(GAME))

from main import build_party        # noqa: E402  (game/main.py)
from combat import run_battle       # noqa: E402  (game/combat.py)

# scenario → game seed (test_acceptance.py 주석: "seed 53/3/0/45")
SCENARIO_SEED = {1: 53, 2: 3, 3: 0, 4: 45}

# 손-박제 골든(검증용 — test_acceptance.py GOLDEN과 동일해야 한다)
EXPECT = {
    1: ("enemy", 23, {"hero1": 0, "hero2": 0, "enemy1": 0, "enemy2": 160, "enemy3": 11}),
    2: ("hero", 17, {"hero1": 23, "hero2": 140, "enemy1": 0, "enemy2": 0}),
    3: ("hero", 19, {"hero1": 90, "hero2": 100, "hero3": 20,
                     "enemy1": 0, "enemy2": 0, "enemy3": 0}),
    4: ("hero", 29, {"hero1": 18, "hero2": 0, "hero3": 0,
                     "enemy1": 0, "enemy2": 0, "enemy3": 0}),
}


def party_def(entities):
    return [{"id": e.id, "name": e.name, "team": e.team, "max_hp": e.max_hp,
             "atk": e.atk, "defense": e.defense, "spd": e.spd,
             "skills": list(e.skills)} for e in entities]


def main():
    out = {}
    ok = True
    for sc, seed in SCENARIO_SEED.items():
        heroes, enemies = build_party(seed)
        party = {"heroes": party_def(heroes), "enemies": party_def(enemies)}  # 전투 전 캡처
        result = run_battle(heroes, enemies, seed=seed)
        golden = {"winner": result["winner"], "turns": result["turns"],
                  "final_hp": result["final_hp"]}
        out[str(sc)] = {"seed": seed, "party": party, "golden": golden}

        ew, et, ehp = EXPECT[sc]
        match = (golden["winner"] == ew and golden["turns"] == et
                 and golden["final_hp"] == ehp)
        ok = ok and match
        print(f"[scenario {sc}] seed={seed} winner={golden['winner']} "
              f"turns={golden['turns']} match={'OK' if match else 'MISMATCH'}")
        if not match:
            print(f"   got hp={golden['final_hp']}")
            print(f"   exp hp={ehp}")

    gdir = Path(__file__).resolve().parent / "golden"
    gdir.mkdir(exist_ok=True)
    (gdir / "scenarios.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[{'ALL OK' if ok else 'FAIL'}] wrote {gdir / 'scenarios.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
