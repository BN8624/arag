# golem 은행 초기화 — 검증된 전투엔진을 카드 #1로 적재하고 A-오라클로 무회귀 검증 (키 안 씀)
"""카드 #1 'tempo-combat' = 지금까지 검증된 템포 턴제 전투엔진.
  규칙   = worker_prompt.RULES
  시나리오 = golden/scenarios.json (party + golden)
  솔루션  = 통과본(attempt10) JS 파일
적재 후, A-오라클(oracle.golden_from_reference)이 솔루션에서 골든을 재생성해
저장된 골든과 일치하는지 확인한다 — game/ 없이도 골든이 나옴을 증명(A경로 골격)."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # arag 루트(config)

import game_bank
import oracle
from worker_prompt import RULES

try:
    from config import force_utf8_stdout
    force_utf8_stdout()
except Exception:  # noqa: BLE001 - config 없으면 콘솔 인코딩만 영향
    pass

SOLUTION_DIR = HERE.parent / "runs" / "golem" / "20260616-130305" / "attempt10"
SOLUTION_FILES = ("models.js", "skills.js", "engine.js", "main.js")
SLUG = "tempo-combat"


def _load_solution():
    files = {}
    for name in SOLUTION_FILES:
        p = SOLUTION_DIR / name
        if not p.exists():
            raise FileNotFoundError(f"솔루션 파일 없음: {p}")
        files[name] = p.read_text(encoding="utf-8")
    return files


def main():
    scenarios = json.loads((HERE / "golden" / "scenarios.json").read_text(encoding="utf-8"))
    solution = _load_solution()

    card = {
        "slug": SLUG,
        "title": "템포 턴제 전투엔진",
        "genre": "turn-rpg",
        "mechanics": "tempo-gauge,status-effects,combo-chain",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": solution,
        "reference": {},  # 골든 최초 출처는 game/(파이썬). 지금은 solution이 JS 레퍼런스 역할.
        "notes": "Phase1 cracked@10 검증본(attempt10). T-000012 JS판, 4 고정 시나리오.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' 저장 ({len(scenarios)} 시나리오, 솔루션 {len(solution)}파일)")

    # --- A-오라클 무회귀: 솔루션에서 골든 재생성 → 저장 골든과 대조 ---
    ids = list(scenarios.keys())
    regen = oracle.golden_from_reference(solution, ids)
    ok = True
    for n in ids:
        exp = scenarios[n]["golden"]
        got = regen[n]
        match = (got["winner"] == exp["winner"] and got["turns"] == exp["turns"]
                 and got["final_hp"] == exp["final_hp"])
        print(f"  scenario {n}: {'OK' if match else 'MISMATCH'}  "
              f"{got['winner']}/{got['turns']}")
        if not match:
            ok = False
            print(f"     got={got}\n     exp={exp}")

    print(f"\n[{'OK' if ok else 'FAIL'}] A-오라클이 game/ 없이 골든 재현 "
          f"{'성공' if ok else '실패'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
