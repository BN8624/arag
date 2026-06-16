# golem 채점기 — 후보 JS(node main.js --scenario N) 출력을 골든과 정확일치 비교, 첫 불일치 보고
"""사용: python golem/grade.py <candidate_dir>
golden/scenarios.json의 4 시나리오마다 node main.js --scenario N 실행 →
winner/turns/엔티티별 hp 파싱 → 골든과 비교. 전부 일치해야 PASS.
first_divergence(첫 불일치 한 줄)는 드라이버가 자가수정 프롬프트에 넣는다."""

import json
import subprocess
import sys
from pathlib import Path

GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "golden" / "scenarios.json").read_text(encoding="utf-8"))
TIMEOUT = 30


def _run_scenario(cdir, n):
    try:
        r = subprocess.run(["node", "main.js", "--scenario", str(n)],
                           cwd=cdir, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, None, None, f"scenario {n}: TIMEOUT ({TIMEOUT}s)"
    except FileNotFoundError as e:
        return None, None, None, f"scenario {n}: run error {e}"
    if r.returncode != 0:
        return None, None, None, f"scenario {n}: node exit {r.returncode}: {r.stderr.strip()[-300:]}"
    winner = turns = None
    hp = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "winner":
            winner = v
        elif k == "turns":
            try:
                turns = int(v)
            except ValueError:
                return None, None, None, f"scenario {n}: bad turns '{v}'"
        else:
            try:
                hp[k] = int(v)
            except ValueError:
                pass
    return winner, turns, hp, None


def _diff_msg(sc, g, winner, turns, hp):
    if winner != g["winner"]:
        return f"scenario {sc}: winner {winner} != {g['winner']}"
    if turns != g["turns"]:
        return f"scenario {sc}: turns {turns} != {g['turns']}"
    for k, v in g["final_hp"].items():
        if hp.get(k) != v:
            return f"scenario {sc}: {k} hp {hp.get(k)} != {v}"
    return f"scenario {sc}: hp mismatch got={hp} exp={g['final_hp']}"


def grade(cdir):
    results = {}
    first = None
    allpass = True
    for sc in ("1", "2", "3", "4"):
        g = GOLDEN[sc]["golden"]
        winner, turns, hp, err = _run_scenario(cdir, sc)
        if err:
            allpass = False
            results[sc] = {"pass": False, "error": err}
            if first is None:
                first = err
            continue
        ok = (winner == g["winner"] and turns == g["turns"] and hp == g["final_hp"])
        results[sc] = {"pass": ok, "got": {"winner": winner, "turns": turns, "hp": hp}}
        if not ok:
            allpass = False
            if first is None:
                first = _diff_msg(sc, g, winner, turns, hp)
    return {"pass": allpass, "scenarios": results, "first_divergence": first}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python golem/grade.py <candidate_dir>")
        raise SystemExit(2)
    res = grade(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    raise SystemExit(0 if res["pass"] else 1)
