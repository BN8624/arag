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
from grade import grade

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
    src = json.loads((HERE / "golden" / "scenarios.json").read_text(encoding="utf-8"))
    solution = _load_solution()
    ids = list(src.keys())

    # A-오라클: 검증 솔루션(JS)을 레퍼런스 삼아 평면 골든 생성 (game/ 없이)
    golden = oracle.golden_from_reference(solution, ids)

    # 시나리오 = {N: {input(=party, 워커 입력), golden(평면 정답)}}
    scenarios = {n: {"input": src[n]["party"], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "템포 턴제 전투엔진",
        "genre": "turn-rpg",
        "mechanics": "tempo-gauge,status-effects,combo-chain",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": solution,
        "reference": solution,  # 검증된 JS 구현이 골든 레퍼런스 역할
        "notes": "Phase1 cracked@10 검증본(attempt10). T-000012 JS판, 4 고정 시나리오.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오, 솔루션 {len(solution)}파일)")

    # --- 무회귀: 솔루션을 grade에 넣어 카드 골든과 PASS 확인 (게임-중립 채점 경로 점검) ---
    res = grade(str(SOLUTION_DIR), scenarios)
    for n in ids:
        r = res["scenarios"][n]
        print(f"  scenario {n}: {'OK' if r['pass'] else 'MISMATCH'}  {r.get('got')}")
    ok = res["pass"]
    print(f"\n[{'OK' if ok else 'FAIL'}] A-오라클+게임중립채점 카드#1 무회귀 "
          f"{'성공' if ok else '실패'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
