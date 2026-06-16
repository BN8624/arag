# golem Phase4 자율 오라클 — 31B가 [주제+최소규격]으로 게임 오라클(규칙·레퍼런스·시나리오) 설계
"""사용: python golem/oracle_design.py [--theme "..."] [--slug snake-auto] [--tries 3]
31B(설계자)가 규칙+결정적 레퍼런스(JS)+시나리오 4개를 한 응답으로 낸다. 우리는 파싱→정적점검
(멀티파일·Math.random없음·node 실행·key:value 출력)→레퍼런스로 골든 생성→카드 적재.
이후 driver.py --card <slug> 로 독립 gemma 합의율을 재서 오라클 신뢰를 검증한다(★키 씀).
Claude는 메타규격(아래 META)만 주고 빠진다 — golem 목적(Claude 절감)."""

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import game_bank
import oracle
from driver import parse_files          # FILE 마커 멀티파일 파서 재사용
from grade import grade

MODEL_31 = "gemma-4-31b-it"

META = """\
You are the DESIGNER. Design ONE small DETERMINISTIC game and its ORACLE, to be implemented by other
programmers FROM YOUR RULES ALONE (they will NOT see your code). Output three sections, EXACT markers.

=== RULES ===
A complete, UNAMBIGUOUS English specification someone can implement without seeing your code. Pin down:
the full game state, how EACH input/step is processed in order, every edge case (collisions, growth,
bounds, ties), termination, and the EXACT OUTPUT CONTRACT. The output contract MUST be:
- runnable as `node main.js --scenario N` (N = 1..4);
- print ONLY lines of the form `key: value` (value = integer or short string), nothing else;
- fully deterministic; every numeric/edge rule explicit.
Also list the files to create (>=2).

=== SCENARIOS ===
A JSON object with EXACTLY 4 scenarios: {"1": <input>, "2": <input>, "3": <input>, "4": <input>}.
Each <input> is the hardcoded input for that scenario (e.g. board size, start state, fixed event list,
move sequence). Vary them to cover edge cases. This is what the implementers will be given.

=== FILE: <name> ===
Your reference implementation. Repeat this marker once per file. It MUST:
- use Node.js builtins only; be CommonJS multi-file (>=2 files that require each other); entry main.js;
- hardcode EXACTLY the 4 scenarios above; be runnable as `node main.js --scenario N`;
- print exactly the key:value OUTPUT CONTRACT; have NO Math.random (deterministic).

HARD CONSTRAINTS (for the game you design AND your reference):
- Node.js builtins only. No npm, network, filesystem, stdin/prompts. No Math.random.
- CommonJS multi-file (>=2 files requiring each other), entry main.js.
- Deterministic and bounded (no infinite loops; cap steps/turns).
- Output: only `key: value` lines, exact-match graded.
- RULES must match your reference EXACTLY: a programmer following RULES must reproduce your reference's
  output for every scenario. Ambiguity will cause independent implementers to disagree.
"""


def _section(text, start, end_markers):
    """'=== start ===' 다음부터 다음 마커 전까지 추출."""
    m = re.search(rf"^===\s*{re.escape(start)}\s*===\s*$", text, re.MULTILINE)
    if not m:
        return None
    rest = text[m.end():]
    cut = len(rest)
    for em in end_markers:
        mm = re.search(em, rest, re.MULTILINE)
        if mm and mm.start() < cut:
            cut = mm.start()
    return rest[:cut].strip()


def parse_oracle(text):
    rules = _section(text, "RULES", [r"^===\s*SCENARIOS\s*===", r"^===\s*FILE:"])
    scen_raw = _section(text, "SCENARIOS", [r"^===\s*FILE:"])
    files = parse_files(text)
    if not rules or not scen_raw or not files:
        return None, None, None, "missing section (rules/scenarios/files)"
    # SCENARIOS JSON 추출(코드펜스/잡텍스트 방어 — 첫 { ~ 마지막 })
    s = scen_raw.strip().strip("`")
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < 0:
        return None, None, None, "scenarios not JSON"
    try:
        scenarios_input = json.loads(s[a:b + 1])
    except json.JSONDecodeError as e:
        return None, None, None, f"scenarios JSON error: {e}"
    return rules, scenarios_input, files, None


def static_check(files, scenarios_input):
    if "main.js" not in files:
        return "no main.js"
    if len(files) < 2:
        return "single file (need >=2)"
    blob = "\n".join(files.values())
    if "Math.random" in blob:
        return "uses Math.random (not deterministic)"
    if not isinstance(scenarios_input, dict) or sorted(scenarios_input) != ["1", "2", "3", "4"]:
        return f"scenarios must be keys 1..4, got {list(scenarios_input)}"
    return None


def design_once(theme, key):
    from llm import LLMClient
    client = LLMClient(api_key=key)
    prompt = META + f"\n\nTHEME: {theme}\n"
    resp = client.generate("generator", prompt)
    cost = client.cost_usd().get("total", 0.0)
    return resp, cost


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="a deterministic Snake game on a grid")
    ap.add_argument("--slug", default="snake-auto")
    ap.add_argument("--tries", type=int, default=3)
    args = ap.parse_args(argv)

    import os
    from config import force_utf8_stdout, get_api_keys
    force_utf8_stdout()
    os.environ["GENERATOR_MODEL"] = MODEL_31
    keys = get_api_keys()

    print(f"[ORACLE] 설계자 31B — theme='{args.theme}', 최대 {args.tries}시도")
    chosen = None
    total_cost = 0.0
    for i in range(args.tries):
        key = keys[i % len(keys)]
        t0 = time.time()
        try:
            resp, cost = design_once(args.theme, key)
        except Exception as err:  # noqa: BLE001
            print(f"  시도 {i+1}: 생성 에러 {str(err)[:100]}")
            continue
        total_cost += cost
        rules, scen, files, perr = parse_oracle(resp)
        if perr:
            print(f"  시도 {i+1}: 파싱 실패 — {perr} ({time.time()-t0:.0f}s)")
            (HERE / f"_oracle_try{i+1}_raw.txt").write_text(resp, encoding="utf-8")
            continue
        serr = static_check(files, scen)
        if serr:
            print(f"  시도 {i+1}: 정적점검 실패 — {serr}")
            continue
        try:
            golden = oracle.golden_from_reference(files, ["1", "2", "3", "4"])
        except RuntimeError as err:
            print(f"  시도 {i+1}: 레퍼런스 실행 실패 — {str(err)[:120]}")
            continue
        print(f"  시도 {i+1}: OK — 파일 {list(files)}, 골든 생성됨 ({time.time()-t0:.0f}s)")
        chosen = (rules, scen, files, golden)
        break

    if not chosen:
        print(f"[ORACLE] 실패 — {args.tries}시도 모두 부적합. cost ~${total_cost:.3f}")
        return 1

    rules, scen, files, golden = chosen
    scenarios = {n: {"input": scen[n], "golden": golden[n]} for n in ("1", "2", "3", "4")}
    card = {
        "slug": args.slug,
        "title": f"[자율오라클] {args.theme}",
        "genre": "auto",
        "mechanics": "phase4-autonomous-oracle",
        "rules": rules,
        "scenarios": scenarios,
        "solution": {},
        "reference": files,
        "notes": f"Phase4 자율오라클: 31B 설계(theme={args.theme}). 검증=driver --card {args.slug}.",
    }
    game_bank.save_card(card)
    print(f"\n[적재] 카드 '{args.slug}' — 31B가 설계한 오라클. cost ~${total_cost:.3f}")
    for n in ("1", "2", "3", "4"):
        g = golden[n]
        keys_preview = ", ".join(f"{k}={v}" for k, v in list(g.items())[:6])
        print(f"  scenario {n}: {keys_preview}{' ...' if len(g) > 6 else ''}")
    print(f"\n다음(★키): python golem/driver.py --card {args.slug}  (독립 gemma 합의율 = 오라클 신뢰)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
