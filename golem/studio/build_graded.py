# Golem Studio Step 5 Build(v1) — design 4모듈 manifest + Spec QA 시나리오로 빌드, 합의 채점(§13 Step5)
"""Build v0(스파이크)와 달리 (1) Planning 2파일 통짜가 아니라 Design의 분해 manifest를 목표로 주고,
(2) Spec QA의 구체 시나리오를 scenarios.json으로 공통 제공해 모든 빌드가 같은 입력을 받게 하고,
(3) 정답을 특권 golden이 아니라 **빌드들의 다수합의**로 잰다(사용자 산출물축소 우려 반영 — 오라클을
'우리'가 아니라 '자'로만 쓴다). 오라클위험(float 등)으로 표시된 시나리오는 채점에서 제외한다.

게이트(빌드별): static_gate + contract_validator(design manifest 정합) + 스모크.
채점: 게이트 통과 빌드들이 채점가능 시나리오에서 같은 출력에 모이나(시나리오별 다수합의 + 일치율).

사용:
  python golem/studio/build_graded.py [--cap 11]   # ★키
"""

import argparse
import json
import subprocess
import sys
import threading
from collections import Counter
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

import contract_validator                       # noqa: E402
import static_gate                              # noqa: E402
from driver import parse_files, write_candidate  # noqa: E402

MODEL_31 = "gemma-4-31b-it"

_PROMPT = """You are the BUILD engineer. Implement this design EXACTLY. Deterministic Node.js, CommonJS,
stdlib only, NO Math.random. Use named exports only (`exports.X` or `module.exports = {{ X }}`).

CONCEPT:
{concept}

RULES:
{rules}

MODULE DESIGN (responsibilities — split the logic this way, do NOT collapse into fewer files):
{system_design}

FILES YOU MUST CREATE (exact paths/exports/imports):
{files}

INPUT CONTRACT (FIXED — `scenarios.json` is a JSON array; scenario N is element N-1, 1-based):
Each scenario is an object with optional `constants`, optional `initialState`, and required `actions`.
- constants: {{ "<genId>": {{ "baseCost": int, "costMultiplier": int, "power": int }} }} (e.g. "gen1").
- initialState: any of {{ "turn": int, "energy": int, "levels": {{ "<genId>": int }}, "gameStatus": str }}.
  ANY absent field uses the canonical default: turn=0, energy=0, levels={{}} (every generator level 0),
  gameStatus="PLAYING". productionRate is NEVER taken from input — always derive it via RULE-04.
- actions: an ARRAY of action objects, applied in order. Each action object is EXACTLY one of:
    {{ "action": "WAIT" }}                         -> apply RULE-01
    {{ "action": "UPGRADE", "id": "<genId>" }}     -> apply RULE-02 on generator `id`
  The verb field is named `action` (NOT `type`); the generator field is named `id` (NOT `generatorId`).
`node main.js --scenario N` MUST read scenarios.json, start from the canonical defaults merged with the
scenario's constants/initialState, apply every action in `actions` in order, then print the final state.

OUTPUT CONTRACT (FIXED — print EXACTLY these four lines, this order, nothing else):
turn: <integer>
energy: <integer>
productionRate: <integer>
gameStatus: <PLAYING or WON>
Use the constants/initialState from the scenario input. If a generator config is absent, default
gen1 = {{ baseCost: 10, costMultiplier: 2, power: 1 }}. All values must be integers (cost uses floor).

Output every file with EXACT markers, one per file:
=== FILE: <path> ===
<file body>
"""


def load_all(pdir, ddir, sdir):
    contract = json.loads((pdir / "contract.json").read_text(encoding="utf-8"))
    concept = (pdir / "concept.md").read_text(encoding="utf-8") if (pdir / "concept.md").exists() else ""
    manifest = json.loads((ddir / "module_manifest.json").read_text(encoding="utf-8"))
    sysd = (ddir / "system_design.md").read_text(encoding="utf-8") if (ddir / "system_design.md").exists() else ""
    scen = json.loads((sdir / "acceptance_tests_draft.json").read_text(encoding="utf-8"))
    risk = json.loads((sdir / "oracle_risk_review.json").read_text(encoding="utf-8"))
    return contract, concept, manifest, sysd, scen, risk


def build_prompt(concept, contract, manifest, sysd):
    rules = contract.get("data_contract", {}).get("rules", [])
    files_desc = "\n".join(
        f"- {f['path']}: exports {f.get('exports', [])}, imports {f.get('imports', [])}"
        for f in manifest.get("files", []))
    return _PROMPT.format(concept=concept.strip() or "(none)",
                          rules="\n".join(f"- {r}" for r in rules) or "(none)",
                          system_design=sysd.strip() or "(none)", files=files_desc)


def _norm_output(stdout):
    """key:value 출력을 정규화(dict) — 합의 비교용. 줄 순서 무관."""
    d = {}
    for line in stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return tuple(sorted(d.items()))


def gate_and_run(workspace, manifest, scenarios):
    """게이트 통과 시 채점가능 시나리오를 실행해 출력 dict 반환. (ok, reason, outputs) ."""
    sg = static_gate.check(str(workspace))
    if not sg["ok"]:
        return False, f"static_gate: {sg['reason']}", {}
    mpath = workspace.parent / "module_manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    cv = contract_validator.validate(workspace, mpath, strict=False)  # 빌드=자유구현 수용
    if not cv["ok"]:
        return False, f"contract_validator: {cv['errors'][:2]}", {}
    outputs = {}
    for i, sc in enumerate(scenarios, 1):
        try:
            r = subprocess.run(["node", "main.js", "--scenario", str(i)], cwd=str(workspace),
                               capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, f"smoke SCN{i}: 타임아웃", {}
        if i == 1 and (r.returncode != 0 or ":" not in r.stdout):
            return False, f"smoke SCN1: exit {r.returncode} out={r.stdout[:80]!r}", {}
        outputs[sc["id"]] = _norm_output(r.stdout) if r.returncode == 0 else None
    return True, "ok", outputs


def consensus(passed_outputs, gradeable_ids):
    """시나리오별 다수합의 + 일치율. passed_outputs: {build: {scen_id: norm_output}}."""
    report = {}
    for sid in gradeable_ids:
        votes = [outs.get(sid) for outs in passed_outputs.values() if outs.get(sid) is not None]
        if not votes:
            report[sid] = {"agree": 0, "total": 0, "rate": 0.0}
            continue
        top, n = Counter(votes).most_common(1)[0]
        report[sid] = {"agree": n, "total": len(votes), "rate": round(n / len(votes), 3)}
    rates = [r["rate"] for r in report.values() if r["total"] > 0]
    overall = round(sum(rates) / len(rates), 3) if rates else 0.0
    return overall, report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--design", default=str(HERE / "design_packet"))
    ap.add_argument("--specqa", default=str(HERE / "specqa_packet"))
    ap.add_argument("--cap", type=int, default=11)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    import os
    os.environ["GENERATOR_MODEL"] = MODEL_31
    os.environ["CRITIC_MODEL"] = MODEL_31
    from config import force_utf8_stdout, get_api_keys
    from llm import AllKeysExhausted, KeyPool, LLMClient
    force_utf8_stdout()

    contract, concept, manifest, sysd, scenarios, risk = load_all(
        Path(args.packet), Path(args.design), Path(args.specqa))
    risky = set(risk.get("risky_scenarios", []))
    gradeable = [s["id"] for s in scenarios if s["id"] not in risky and s.get("expected") is not None]
    scen_inputs = [s.get("input", {}) for s in scenarios]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(args.out) if args.out else (HERE / "build_runs" / f"graded-{run_id}")
    prompt = build_prompt(concept, contract, manifest, sysd)
    pool = KeyPool(get_api_keys(), models=[MODEL_31])
    print(f"[BUILD v1] design 4모듈 manifest, 시나리오 {len(scenarios)}(채점가능 {len(gradeable)}), "
          f"cap={args.cap} keys={pool.size}, run={run_id}")

    manifest_v = {"schema_version": "0.1", "module_format": "commonjs", **manifest}
    lock = threading.Lock()
    passed_outputs = {}
    cracked = None

    def worker(attempt):
        with pool.checkout() as key:
            resp = LLMClient(api_key=key).generate("critic", prompt)
        ws = base / f"attempt{attempt:02d}" / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        write_candidate(ws, parse_files(resp))
        (ws / "scenarios.json").write_text(json.dumps(scen_inputs, ensure_ascii=False), encoding="utf-8")
        ok, reason, outputs = gate_and_run(ws, manifest_v, scenarios)
        return attempt, ok, reason, outputs

    with ThreadPoolExecutor(max_workers=min(pool.size, args.cap)) as ex:
        futs = {ex.submit(worker, a): a for a in range(1, args.cap + 1)}
        for fut in as_completed(futs):
            try:
                a, ok, reason, outputs = fut.result()
            except CancelledError:
                continue
            except AllKeysExhausted as e:
                print(f"[BUILD v1] 중단: {e}")
                break
            print(f"  [attempt {a:02d}] gate={ok} {reason}")
            if ok:
                with lock:
                    passed_outputs[a] = outputs
                    if cracked is None:
                        cracked = a

    overall, report = consensus(passed_outputs, gradeable)
    base.mkdir(parents=True, exist_ok=True)
    (base / "consensus.json").write_text(json.dumps(
        {"gate_passed": len(passed_outputs), "cap": args.cap,
         "gradeable": gradeable, "overall_agreement": overall, "per_scenario": report},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[BUILD v1] 게이트 통과 {len(passed_outputs)}/{args.cap}, "
          f"합의 채점(채점가능 {len(gradeable)}): 전체 일치율 {overall}")
    for sid, r in report.items():
        print(f"    {sid}: 합의 {r['agree']}/{r['total']} (일치율 {r['rate']})")
    print(f"[BUILD v1] → {base}")
    return 0 if passed_outputs else 1


if __name__ == "__main__":
    raise SystemExit(main())
