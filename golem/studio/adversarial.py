# Golem Studio Step 6 Adversarial QA — 깨질 케이스를 능동 탐색해 edge_cases + 최종 acceptance 생성 (§13 Step6·§8.5)
"""Adversarial QA팀은 구현을 새로 하지 않는다(§13). 오직 "naive 빌드가 갈라질" 경계/실패 케이스를 만든다.
입력: 계약(rules·state_shape) + concept + REQ + Spec QA가 만든 현재 시나리오(acceptance_tests_draft).
산출물(§13 Step6·§8.5): acceptance_tests.json(정상·실패·경계, 각 REQ≥1, golden 명확) + edge_cases.json
(구현을 깨는 케이스, 명확한 expected). 채점은 build_graded와 동일 — 특권 golden 아닌 빌드 다수합의로 잰다.

lead(케이스 생성) → 리뷰어 N축(놓친 break 사냥) → synthesis(병합·BLOCKING 해소) 구조는 specqa와 동일.
입력 스키마는 build와 동일하게 고정(action/id, costMultiplier, 캐노니컬 디폴트) — 생성 케이스도 같은 형식.

사용:
  python golem/studio/adversarial.py --replay <fixture.json>   # 키 안 씀
  python golem/studio/adversarial.py                            # ★키
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

from planning import _extract_json            # noqa: E402

MODEL_31 = "gemma-4-31b-it"

# 깨는 축 — naive 빌드가 갈라질 만한 곳(관측: 승리판정 평가시점이 실제로 빌드를 갈랐다 → G36)
AXES = [
    "win threshold boundary: energy exactly 999 vs 1000 vs 1001 at different points in the sequence",
    "win mid-sequence: WON triggers partway through actions; every remaining action MUST be skipped (RULE-06)",
    "cost/floor edge: currentCost at successive levels, large costMultiplier**level, floor() rounding",
    "insufficient-energy boundary: energy exactly equal to currentCost vs one less than currentCost",
    "action ordering: UPGRADE then WAIT vs WAIT then UPGRADE — when does the new productionRate apply",
    "absent input / defaults: no constants, no initialState, empty actions list — canonical defaults",
    "unknown or multiple generator id: UPGRADE on an undefined id, or two generators in constants",
    "productionRate recompute timing: rate change from an UPGRADE takes effect on which later WAIT",
]

_INPUT_CONTRACT = """INPUT SCHEMA (FIXED — every case input MUST use this exact shape):
scenario input = {{ "constants"?: {{ "<genId>": {{ "baseCost": int, "costMultiplier": int, "power": int }} }},
                   "initialState"?: {{ "turn": int, "energy": int, "levels": {{ "<genId>": int }}, "gameStatus": str }},
                   "actions": [ {{ "action": "WAIT" }} | {{ "action": "UPGRADE", "id": "<genId>" }} ] }}
Absent fields default to: turn=0, energy=0, levels={{}} (level 0), gameStatus="PLAYING"; productionRate via RULE-04.
The verb field is `action` (not type); the generator field is `id` (not generatorId)."""

_LEAD_PROMPT = """You are the ADVERSARIAL QA LEAD. Do NOT implement the game. Your job: build cases that would make
two plausible-but-naive implementations DIVERGE, plus finalize the acceptance suite. Deterministic Node.js game.

CONCEPT:
{concept}

FROZEN CONTRACT RULES (the only source of truth — design cases that stress their EDGES):
{rules}

REQUIREMENTS (each MUST be covered by >=1 test across acceptance_tests + edge_cases):
{reqs}

CURRENT ACCEPTANCE SCENARIOS (already converged — keep/clean them as `acceptance_tests`, do NOT just repeat):
{scenarios}

{input_contract}

Output ONE JSON object EXACTLY:
{{
  "acceptance_tests": [
    {{"id": "ACC-001", "category": "normal|failure|boundary", "input": {{"actions": [...]}},
      "covers_reqs": ["RULE-01"], "expected": {{"turn": 0, "energy": 0, "productionRate": 1, "gameStatus": "PLAYING"}},
      "oracle_risk": {{"risk": false, "reason": ""}}}}
  ],
  "edge_cases": [
    {{"id": "EDGE-001", "input": {{"actions": [...]}}, "covers_reqs": ["RULE-05"],
      "breaks": "why a naive build would get this wrong (one line)",
      "expected": {{"turn": 0, "energy": 1000, "productionRate": 1, "gameStatus": "WON"}},
      "oracle_risk": {{"risk": false, "reason": ""}}}}
  ],
  "notes": ["any rule whose edge is under-specified by the contract"]
}}
RULES: inputs are concrete machine data (NOT prose). `expected` is the FULL final state
(turn, energy, productionRate, gameStatus). If you cannot pin expected exactly, set it null and
oracle_risk.risk=true. acceptance_tests MUST include >=1 of each category (normal, failure, boundary).
edge_cases MUST be non-empty and each must state `breaks`. JSON only, no prose."""

_REVIEW_INSTRUCTIONS = """Do NOT rewrite the game. ONLY hunt on your axis for a breaking case the lead MISSED, as
concrete machine input with a pinned expected final state. Output ONE JSON object EXACTLY (lists, [] if none):
{{
  "missing_edge_cases": [{{"input": {{"actions": []}}, "expected": {{"turn": 0}}, "breaks": "..."}}],
  "uncovered_reqs": [],
  "weak_expected": ["id of a case whose golden output is vague or unpinned"],
  "questions_for_lead": [{{"q": "...", "class": "BLOCKING|ASSUMED|DEFERRED"}}]
}}
JSON only, no prose."""

_REVIEWER_PROMPT = """You are an ADVERSARIAL QA REVIEWER. Your single axis is:
AXIS: {axis}

{input_contract}

The case set to attack (JSON):
{cases}

{instructions}
"""

_SYNTHESIS_PROMPT = """You are the ADVERSARIAL QA LEAD doing SYNTHESIS. Your case draft (JSON):
{cases}

Reviewers proposed these missing breaks / problems (JSON):
{issues}

Merge the valid proposed edge cases in and finalize. Output ONE JSON object EXACTLY in the same shape
(acceptance_tests, edge_cases, notes). HARD RULES: every REQ in {reqs} covered by >=1 test across both lists;
acceptance_tests has >=1 of each category (normal, failure, boundary); edge_cases non-empty with `breaks`;
inputs concrete machine data; any unpinnable expected set null with oracle_risk.risk=true; resolve every
BLOCKING question. {input_contract_short} JSON only."""


def load_inputs(pdir, sdir):
    contract = json.loads((pdir / "contract.json").read_text(encoding="utf-8"))
    concept = (pdir / "concept.md").read_text(encoding="utf-8") if (pdir / "concept.md").exists() else ""
    rules = contract.get("data_contract", {}).get("rules", [])
    reqs = []
    for i, r in enumerate(rules, 1):
        m = re.match(r"\s*(RULE-\d+)\s*[:\-]\s*(.*)", str(r))
        reqs.append({"id": m.group(1) if m else f"REQ-{i:02d}", "text": m.group(2) if m else str(r)})
    scenarios = json.loads((sdir / "acceptance_tests_draft.json").read_text(encoding="utf-8"))
    return concept, rules, reqs, scenarios


def adversarial_validate(final, reqs):
    """§13 Step6·§8.5 검증. (ok, errors, risky) 반환."""
    errors = []
    acc = final.get("acceptance_tests", []) or []
    edge = final.get("edge_cases", []) or []
    if not acc:
        errors.append("acceptance_tests 비어 있음")
    if not edge:
        errors.append("edge_cases 비어 있음(구현을 깨는 케이스 필요)")
    cats = {str(t.get("category", "")).lower() for t in acc}
    for need in ("normal", "failure", "boundary"):
        if need not in cats:
            errors.append(f"acceptance_tests에 '{need}' 카테고리 없음")
    covered = set()
    risky = []
    for t in (acc + edge):
        for rid in (t.get("covers_reqs") or []):
            covered.add(rid)
        orisk = t.get("oracle_risk") or {}
        if orisk.get("risk") or t.get("expected") is None:
            risky.append(t.get("id"))
        elif not t.get("expected"):
            errors.append(f"{t.get('id', '?')}: expected(golden) 없음")
    for r in reqs:
        if r["id"] not in covered:
            errors.append(f"{r['id']}: 커버하는 테스트 없음(untested)")
    return (len(errors) == 0, errors, risky)


def _blocking(reviews):
    return [q.get("q", "") for r in reviews for q in (r.get("questions_for_lead") or [])
            if str(q.get("class", "")).upper() == "BLOCKING"]


class FakeCaller:
    def __init__(self, fx):
        self.fx = fx

    def lead(self, ctx):
        return self.fx["cases"]

    def reviews(self, cases, axes):
        return self.fx["reviews"][:len(axes)]

    def synth(self, cases, issues, reqs):
        return self.fx.get("synthesis", cases)


class RealCaller:
    def __init__(self):
        import os
        os.environ["GENERATOR_MODEL"] = MODEL_31
        os.environ["CRITIC_MODEL"] = MODEL_31
        from config import get_api_keys
        from llm import KeyPool
        self.pool = KeyPool(get_api_keys(), models=[MODEL_31])

    def _one(self, prompt):
        from llm import LLMClient
        with self.pool.checkout() as key:
            return LLMClient(api_key=key).generate("critic", prompt)

    def lead(self, ctx):
        return _extract_json(self._one(_LEAD_PROMPT.format(**ctx)))

    def reviews(self, cases, axes):
        out = [None] * len(axes)
        cj = json.dumps(cases, ensure_ascii=False)
        with ThreadPoolExecutor(max_workers=min(len(axes), self.pool.size)) as ex:
            futs = {ex.submit(self._one, _REVIEWER_PROMPT.format(
                axis=ax, cases=cj, input_contract=_INPUT_CONTRACT,
                instructions=_REVIEW_INSTRUCTIONS)): i
                for i, ax in enumerate(axes)}
            for fut in futs:
                out[futs[fut]] = _extract_json(fut.result())
        return out

    def synth(self, cases, issues, reqs):
        return _extract_json(self._one(_SYNTHESIS_PROMPT.format(
            cases=json.dumps(cases, ensure_ascii=False),
            issues=json.dumps(issues, ensure_ascii=False), reqs=reqs,
            input_contract_short="Inputs use the FIXED schema (action/id, costMultiplier, canonical defaults).")))


def run(concept, rules, reqs, scenarios, caller):
    ctx = {"concept": concept.strip() or "(none)",
           "rules": "\n".join(f"- {r}" for r in rules) or "(none)",
           "reqs": "\n".join(f"- {r['id']}: {r['text']}" for r in reqs) or "(none)",
           "scenarios": json.dumps(scenarios, ensure_ascii=False),
           "input_contract": _INPUT_CONTRACT}
    draft = caller.lead(ctx)
    reviews = caller.reviews(draft, AXES)
    issues = {"missing_edge_cases": [i for r in reviews for i in (r.get("missing_edge_cases") or [])],
              "uncovered_reqs": sorted({i for r in reviews for i in (r.get("uncovered_reqs") or [])}),
              "weak_expected": [i for r in reviews for i in (r.get("weak_expected") or [])],
              "BLOCKING": _blocking(reviews)}
    final = caller.synth(draft, issues, [r["id"] for r in reqs])
    return draft, reviews, issues, final


def _write_packet(final, risky, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "acceptance_tests.json").write_text(
        json.dumps(final.get("acceptance_tests", []), ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "edge_cases.json").write_text(
        json.dumps(final.get("edge_cases", []), ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "oracle_risk_review.json").write_text(
        json.dumps({"risky_cases": risky, "notes": final.get("notes", [])},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=None)
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--specqa", default=str(HERE / "specqa_packet"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    if args.replay:
        fx = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        concept, rules, reqs, scenarios = fx["concept"], fx["rules"], fx["reqs"], fx.get("scenarios", [])
        caller = FakeCaller(fx)
    else:
        concept, rules, reqs, scenarios = load_inputs(Path(args.packet), Path(args.specqa))
        caller = RealCaller()

    draft, reviews, issues, final = run(concept, rules, reqs, scenarios, caller)
    outdir = Path(args.out) if args.out else (HERE / "adversarial_packet")
    ok, errors, risky = adversarial_validate(final, reqs)
    _write_packet(final, risky, outdir)

    n_acc = len(final.get("acceptance_tests", []))
    n_edge = len(final.get("edge_cases", []))
    n_block = len(issues.get("BLOCKING", []))
    status = ["# STATUS (Adversarial QA)", "",
              f"- REQ 수: {len(reqs)}", f"- acceptance_tests: {n_acc}", f"- edge_cases: {n_edge}",
              f"- 오라클 위험(정확일치 불가) 케이스: {len(risky)} {risky}",
              f"- 리뷰어 BLOCKING: {n_block}",
              f"- §8.5 validator: {'PASS' if ok else 'FAIL'}",
              *([f"  - {e}" for e in errors[:8]] if errors else []),
              "", f"ADVERSARIAL_STATUS: {'COMPLETE' if ok else 'INCOMPLETE'}"]
    (outdir / "STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    print(f"[ADVQA] api_calls={'0' if args.replay else 'live'} REQ={len(reqs)} "
          f"acceptance={n_acc} edge={n_edge} 오라클위험={len(risky)} BLOCKING={n_block}")
    print(f"  validator: {'PASS' if ok else 'FAIL'}  → {outdir}")
    for e in errors[:8]:
        print(f"    - {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
