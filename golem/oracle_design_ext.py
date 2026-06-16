# 확장형 자율오라클 — 31B가 베이스(모듈 로그라이크) 위에 큰 레이어를 [규칙+시나리오+레퍼런스]로 자율 설계
"""gemma를 손이 아니라 머리로 쓴다. Claude는 베이스 + 설계 브리프(그릇 크기)만 주고 빠진다.
31B(설계자)가 ① UNAMBIGUOUS 규칙 ② 시나리오 4개 ③ 베이스를 확장한 레퍼런스 구현을 한 응답에 낸다.
레퍼런스를 베이스와 병합·실행해 골든을 만든다(= 자기 테스트). 이후 driver --card <slug> --base <base>로
독립 gemma 구현들의 합의율을 재 신뢰를 검증한다(self-bias 방어 = Phase4 합의 게이트 재사용).
사용: python golem/oracle_design_ext.py --base rogue-p4 --slug rogue-elem --tries 3"""

import argparse
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import game_bank
import oracle
from oracle_design import parse_oracle      # RULES/SCENARIOS/FILE 파서 재사용
from grade import grade

MODEL_31 = "gemma-4-31b-it"

# 그릇 크기(브리프) — gemma가 야심차게 설계하도록 큰 레이어를 명시. 세부 규칙은 gemma가 정한다.
BRIEF = """\
Design an ELEMENTAL ENVIRONMENT layer for the dungeon: new walkable cell types representing elements
(at least FIRE, WATER, OIL) that INTERACT with each other and with the player and the enemy, creating
emergent tactics (e.g. oil that ignites and spreads, water that quenches fire into steam, the player or
enemy taking damage / being affected when standing in or adjacent to certain elements). Be ambitious:
several interacting rules, propagation between cells, and effects on combat — but keep it FULLY
deterministic and exactly testable. You decide the precise rules; make them unambiguous."""

META = """\
You are the DESIGNER. You are EXTENDING an existing, working, MODULAR deterministic roguelike engine
(provided below) with a NEW LAYER. Other programmers will implement your layer FROM YOUR RULES ALONE
(they get the SAME base + your RULES + your SCENARIOS, but NOT your reference code). Output THREE
sections with these EXACT markers.

=== RULES ===
A complete, UNAMBIGUOUS English spec of your new layer on top of the base. Pin down: every new cell
type / state, the FULL turn order with your new systems woven into the base's player-then-enemy turn,
every interaction and edge case (propagation order, ties, what happens on death, bounds), and the
EXACT OUTPUT CONTRACT. The output contract MUST stay:
- runnable as `node main.js --scenario N` (N = 1..4);
- print ONLY lines of the form `key: value` (value = integer or short string), nothing else;
- a SUPERSET of the base's existing output lines (keep them) plus your new fields;
- fully deterministic (NO Math.random; if you need ordering, fix it explicitly, e.g. top-left to
  bottom-right). List which files you change or add.

=== SCENARIOS ===
A JSON object with EXACTLY 4 scenarios: {"1": <input>, "2": <input>, "3": <input>, "4": <input>}.
Each <input> is the hardcoded input for that scenario (grid with your element cells, start, enemy,
moves, hp/atk, and any new fields). DESIGN THEM TO TRIGGER THE EMERGENT INTERACTIONS (e.g. lure the
enemy onto oil then ignite it). This is exactly what the implementers will be given.

=== FILE: <name> ===
Your reference implementation, EXTENDING THE BASE. Output ONLY the files you change or add (unchanged
base files are kept). Repeat this marker once per file. It MUST: be CommonJS, Node builtins only, no
Math.random; hardcode EXACTLY the 4 scenarios above; run as `node main.js --scenario N`; print exactly
your OUTPUT CONTRACT.

HARD CONSTRAINTS:
- Reuse the base modules; do not rewrite what you don't need to change.
- RULES must match your reference EXACTLY: a programmer following RULES alone must reproduce your
  reference's output for every scenario. Ambiguity makes independent implementers disagree.
"""


def _base_block(base_files):
    lines = ["== BASE IMPLEMENTATION (modular; extend it) =="]
    for name, body in base_files.items():
        lines.append(f"--- {name} ---\n{body.rstrip()}")
    return "\n".join(lines)


def design_once(prompt, key):
    from llm import LLMClient
    client = LLMClient(api_key=key)
    resp = client.generate("generator", prompt)
    return resp, dict(client.tokens), client.cost_usd().get("total", 0.0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="rogue-p4")
    ap.add_argument("--slug", default="rogue-elem")
    ap.add_argument("--tries", type=int, default=3)
    args = ap.parse_args(argv)

    from config import force_utf8_stdout, get_api_keys
    force_utf8_stdout()
    os.environ["GENERATOR_MODEL"] = MODEL_31

    base_card = game_bank.get_card(args.base)
    if base_card is None or not base_card.get("solution"):
        print(f"[ERR] 베이스 '{args.base}'의 solution 없음")
        return 2
    base_files = base_card["solution"]
    keys = get_api_keys()
    prompt = META + "\n\n" + BRIEF + "\n\n" + _base_block(base_files)

    print(f"[ORACLE-EXT] 설계자 31B — base={args.base}, 최대 {args.tries}시도, 원소 레이어 자율설계\n")
    chosen = None
    total_cost = 0.0
    for i in range(args.tries):
        key = keys[i % len(keys)]
        t0 = time.time()
        try:
            resp, toks, cost = design_once(prompt, key)
        except Exception as err:  # noqa: BLE001
            print(f"  시도 {i+1}: 생성 에러 {str(err)[:100]}")
            continue
        total_cost += cost
        (HERE / f"_oracle_ext_try{i+1}_raw.txt").write_text(resp, encoding="utf-8")
        rules, scen, files, perr = parse_oracle(resp)
        if perr:
            print(f"  시도 {i+1}: 파싱 실패 — {perr} "
                  f"(out+think={toks['output']+toks['thinking']}, {time.time()-t0:.0f}s)")
            continue
        merged = {**base_files, **files}     # 베이스 + 설계자가 바꾼 파일
        if "main.js" not in merged:
            print(f"  시도 {i+1}: main.js 없음(병합 후)")
            continue
        if "Math.random" in "\n".join(files.values()):
            print(f"  시도 {i+1}: Math.random 사용(비결정적)")
            continue
        if sorted(scen) != ["1", "2", "3", "4"]:
            print(f"  시도 {i+1}: 시나리오 키가 1..4 아님 — {list(scen)}")
            continue
        import tempfile
        import static_gate
        with tempfile.TemporaryDirectory(prefix="golem_sg_") as td:
            for nm, bd in merged.items():
                (Path(td) / nm).write_text(bd, encoding="utf-8")
            sg = static_gate.check(td)
        if not sg["ok"]:
            print(f"  시도 {i+1}: 정적게이트 실패 — {sg['reason']}")
            continue
        try:
            golden = oracle.golden_from_reference(merged, ["1", "2", "3", "4"])
        except RuntimeError as err:
            print(f"  시도 {i+1}: 레퍼런스 실행 실패 — {str(err)[:140]}")
            continue
        print(f"  시도 {i+1}: OK — 바꾼 파일 {list(files)}, 골든 생성됨 "
              f"(out+think={toks['output']+toks['thinking']}/32k, {time.time()-t0:.0f}s)")
        chosen = (rules, scen, merged, files, golden)
        break

    if not chosen:
        print(f"\n[ORACLE-EXT] 실패 — {args.tries}시도 모두 부적합. cost ~${total_cost:.3f}")
        return 1

    rules, scen, merged, changed, golden = chosen
    scenarios = {n: {"input": scen[n], "golden": golden[n]} for n in ("1", "2", "3", "4")}
    card = {
        "slug": args.slug,
        "title": f"[자율설계-확장] 원소 레이어 (base={args.base})",
        "genre": "roguelike",
        "mechanics": "autonomous-design-ext,elements,emergent",
        "rules": rules,
        "scenarios": scenarios,
        "solution": {},
        "reference": merged,
        "notes": f"확장형 자율오라클: 31B가 {args.base} 위 원소 레이어 설계. 검증=driver --card {args.slug} --base {args.base}.",
    }
    game_bank.save_card(card)
    print(f"\n[적재] 카드 '{args.slug}' — 31B 자율설계(확장). cost ~${total_cost:.3f}")
    print(f"  출력 계약 키: {list(golden['1'].keys())}")
    for n in ("1", "2", "3", "4"):
        g = golden[n]
        preview = ", ".join(f"{k}={v}" for k, v in list(g.items()))
        print(f"  scenario {n}: {preview}")
    print(f"\n다음(★키): python golem/driver.py --card {args.slug} --base {args.base}  (독립 gemma 합의)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
