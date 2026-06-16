# T-000012 고정 골든 오라클 — main.py --scenario N 출력을 박힌 골든과 정확일치 검수(손-박제)
"""설계·구현과 무관한 블랙박스 오라클. 모델이 쓰지 않고 손으로 고정한다.
골든은 game/ 레퍼런스(seed 53/3/0/45)로 검증된 값(2026-06-15). 4 시나리오 모두
winner + turns + 엔티티별 final hp가 정확히 일치해야 통과. 틀리면 AssertionError(=구현 책임)
이므로 하네스가 '시험지 불량'으로 오인해 재생성하지 않는다.
"""

import subprocess
import sys

import pytest

GOLDEN = {
    1: {"winner": "enemy", "turns": 23,
        "hp": {"hero1": 0, "hero2": 0, "enemy1": 0, "enemy2": 160, "enemy3": 11}},
    2: {"winner": "hero", "turns": 17,
        "hp": {"hero1": 23, "hero2": 140, "enemy1": 0, "enemy2": 0}},
    3: {"winner": "hero", "turns": 19,
        "hp": {"hero1": 90, "hero2": 100, "hero3": 20,
               "enemy1": 0, "enemy2": 0, "enemy3": 0}},
    4: {"winner": "hero", "turns": 29,
        "hp": {"hero1": 18, "hero2": 0, "hero3": 0,
               "enemy1": 0, "enemy2": 0, "enemy3": 0}},
}


def _run(n: int):
    r = subprocess.run([sys.executable, "main.py", "--scenario", str(n)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"scenario {n} exit {r.returncode}: {r.stderr[-500:]}"
    winner = turns = None
    hp = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key == "winner":
            winner = val
        elif key == "turns":
            turns = int(val)
        else:
            hp[key] = int(val)
    return winner, turns, hp


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_scenario_matches_golden(n):
    g = GOLDEN[n]
    winner, turns, hp = _run(n)
    assert winner == g["winner"], f"s{n} winner {winner} != {g['winner']}"
    assert turns == g["turns"], f"s{n} turns {turns} != {g['turns']}"
    assert hp == g["hp"], f"s{n} hp {hp} != {g['hp']}"
