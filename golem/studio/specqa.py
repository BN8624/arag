# Golem Studio Step 4 Spec QA — 산문 수용기준 → 기계 시나리오 + 오라클 위험 표시 (§13 Step4·§8.4)
"""Planning/Design 산출물을 입력으로, 테스트 가능한 계약인지 먼저 검토한다.
산출물(§13 Step4): acceptance_tests_draft.json, oracle_risk_review.json.
완료기준(§8.4): 각 REQ에 ≥1 테스트 후보 연결 / expected가 모호한 시나리오 표시 /
TEST_ORACLE_ERROR 위험 분리 / BLOCKING 0.
이 단계가 "굴러가나"를 "맞는지 잴 수 있나"로 바꾼다 — 빌드들이 같은 입력을 받게 시나리오를 못박고,
정확일치로 채점 불가한(모호한 expected) 시나리오를 따로 떼어낸다.

사용:
  python golem/studio/specqa.py --replay <fixture.json>                       # 키 안 씀
  python golem/studio/specqa.py [--packet <planning_packet>] [--design <design_packet>]  # ★키
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

AXES = [
    "untestable requirement: a REQ no concrete scenario exercises",
    "ambiguous expected output: a scenario whose exact answer can't be pinned",
    "missing edge/boundary scenario",
    "non-deterministic expected: answer depends on float precision or order",
    "input not machine-runnable: scenario input is prose, not concrete data",
    "scenario does not actually exercise the REQ it claims",
    "expected contradicts the frozen contract rules",
    "oracle error risk: the stated expected value itself may be wrong",
    "coverage gap: a REQ only tested indirectly",
    "handoff risk to Build: a builder would run this scenario differently",
]

ISSUE_KEYS = ["untestable_reqs", "ambiguous_expected", "missing_scenarios",
              "nondeterministic", "oracle_errors", "risky_assumptions"]

_LEAD_PROMPT = """You are the SPEC QA LEAD. Turn the prose acceptance criteria into CONCRETE, machine-runnable
scenarios for a deterministic Node.js game (`node main.js --scenario N`, prints `key: value` lines).

CONCEPT:
{concept}

REQUIREMENTS (each MUST be covered by >=1 scenario):
{reqs}

EXISTING ACCEPTANCE SKETCHES (prose, make them concrete):
{acceptance}

Output ONE JSON object EXACTLY:
{{
  "scenarios": [
    {{"id": "SCN-001", "input": {{}}, "covers_reqs": ["RULE-01"],
      "expected": {{"turn": 0}}, "oracle_risk": {{"risk": false, "reason": ""}}}}
  ],
  "oracle_risk_summary": ["short note on any expected value that can't be pinned exactly"]
}}
RULES: "input" must be concrete machine data (action list / numbers), NOT prose. If you cannot pin
"expected" exactly (e.g. float rounding), set "expected": null and oracle_risk.risk=true with a reason.
Every REQ id must appear in some scenario's covers_reqs. JSON only, no prose."""

_REVIEW_INSTRUCTIONS = """Do NOT rewrite the game. ONLY hunt problems on your axis. Output ONE JSON object EXACTLY
(each a list of short strings, [] if none):
{{
  "untestable_reqs": [],
  "ambiguous_expected": [],
  "missing_scenarios": [],
  "nondeterministic": [],
  "oracle_errors": [],
  "risky_assumptions": [],
  "questions_for_lead": [{{"q": "...", "class": "BLOCKING|ASSUMED|DEFERRED"}}]
}}
JSON only, no prose."""

_REVIEWER_PROMPT = """You are a SPEC QA REVIEWER. Your single axis is:
AXIS: {axis}

The scenario set to review (JSON):
{spec}

{instructions}
"""

_SYNTHESIS_PROMPT = """You are the SPEC QA LEAD doing SYNTHESIS. Your scenario draft (JSON):
{spec}

Reviewers found these issues (JSON):
{issues}

Fix them and finalize. Output ONE JSON object EXACTLY in the same shape (scenarios, oracle_risk_summary).
HARD RULES: every REQ in {reqs} covered by >=1 scenario; inputs concrete machine data; any unpinnable
expected set to null with oracle_risk.risk=true; resolve every BLOCKING question. JSON only."""


def load_inputs(pdir, ddir):
    contract = json.loads((pdir / "contract.json").read_text(encoding="utf-8"))
    concept = (pdir / "concept.md").read_text(encoding="utf-8") if (pdir / "concept.md").exists() else ""
    acceptance = json.loads((pdir / "acceptance_tests.json").read_text(encoding="utf-8"))
    rules = contract.get("data_contract", {}).get("rules", [])
    reqs = []
    for i, r in enumerate(rules, 1):
        m = re.match(r"\s*(RULE-\d+)\s*[:\-]\s*(.*)", str(r))
        reqs.append({"id": m.group(1) if m else f"REQ-{i:02d}", "text": m.group(2) if m else str(r)})
    return concept, reqs, acceptance


def specqa_validate(final, reqs):
    """§13 Step4·§8.4 검증. (ok, errors, risky) 반환."""
    errors = []
    scenarios = final.get("scenarios", [])
    if not scenarios:
        errors.append("scenarios 비어 있음")
    covered = set()
    risky = []
    for s in scenarios:
        if not s.get("id"):
            errors.append("id 없는 시나리오")
        if "input" not in s:
            errors.append(f"{s.get('id', '?')}: input 없음")
        for rid in (s.get("covers_reqs") or []):
            covered.add(rid)
        orisk = s.get("oracle_risk") or {}
        if orisk.get("risk") or s.get("expected") is None:
            risky.append(s.get("id"))
    for r in reqs:
        if r["id"] not in covered:
            errors.append(f"{r['id']}: 커버하는 시나리오 없음(untested)")
    return (len(errors) == 0, errors, risky)


def _blocking(reviews):
    return [q.get("q", "") for r in reviews for q in (r.get("questions_for_lead") or [])
            if str(q.get("class", "")).upper() == "BLOCKING"]


class FakeCaller:
    def __init__(self, fx):
        self.fx = fx

    def lead(self, ctx):
        return self.fx["spec"]

    def reviews(self, spec, axes):
        return self.fx["reviews"][:len(axes)]

    def synth(self, spec, issues, reqs):
        return self.fx.get("synthesis", spec)


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

    def reviews(self, spec, axes):
        out = [None] * len(axes)
        sj = json.dumps(spec, ensure_ascii=False)
        with ThreadPoolExecutor(max_workers=min(len(axes), self.pool.size)) as ex:
            futs = {ex.submit(self._one, _REVIEWER_PROMPT.format(
                axis=ax, spec=sj, instructions=_REVIEW_INSTRUCTIONS)): i
                for i, ax in enumerate(axes)}
            for fut in futs:
                out[futs[fut]] = _extract_json(fut.result())
        return out

    def synth(self, spec, issues, reqs):
        return _extract_json(self._one(_SYNTHESIS_PROMPT.format(
            spec=json.dumps(spec, ensure_ascii=False),
            issues=json.dumps(issues, ensure_ascii=False), reqs=reqs)))


def run(concept, reqs, acceptance, caller):
    ctx = {"concept": concept.strip() or "(none)",
           "reqs": "\n".join(f"- {r['id']}: {r['text']}" for r in reqs) or "(none)",
           "acceptance": json.dumps(acceptance, ensure_ascii=False)}
    draft = caller.lead(ctx)
    reviews = caller.reviews(draft, AXES)
    issues = {k: [i for r in reviews for i in (r.get(k) or [])] for k in ISSUE_KEYS}
    issues["BLOCKING"] = _blocking(reviews)
    final = caller.synth(draft, issues, [r["id"] for r in reqs])
    return draft, reviews, issues, final


def _write_packet(final, risky, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    scenarios = final.get("scenarios", [])
    (outdir / "acceptance_tests_draft.json").write_text(
        json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "oracle_risk_review.json").write_text(
        json.dumps({"risky_scenarios": risky,
                    "notes": final.get("oracle_risk_summary", [])},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=None)
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--design", default=str(HERE / "design_packet"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    if args.replay:
        fx = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        concept, reqs, acceptance = fx["concept"], fx["reqs"], fx.get("acceptance", [])
        caller = FakeCaller(fx)
        api_calls = 0
    else:
        concept, reqs, acceptance = load_inputs(Path(args.packet), Path(args.design))
        caller = RealCaller()
        api_calls = None

    draft, reviews, issues, final = run(concept, reqs, acceptance, caller)
    outdir = Path(args.out) if args.out else (HERE / "specqa_packet")
    ok, errors, risky = specqa_validate(final, reqs)
    _write_packet(final, risky, outdir)

    n_block = len(issues.get("BLOCKING", []))
    n_scen = len(final.get("scenarios", []))
    status = ["# STATUS (Spec QA)", "",
              f"- REQ 수: {len(reqs)}", f"- 시나리오 수: {n_scen}",
              f"- 오라클 위험(정확일치 불가) 시나리오: {len(risky)} {risky}",
              f"- 리뷰어 BLOCKING: {n_block}",
              f"- §8.4 validator: {'PASS' if ok else 'FAIL'}",
              *([f"  - {e}" for e in errors[:8]] if errors else []),
              "", f"SPECQA_STATUS: {'COMPLETE' if ok else 'INCOMPLETE'}"]
    (outdir / "STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    print(f"[SPECQA] api_calls={0 if args.replay else api_calls} REQ={len(reqs)} "
          f"시나리오={n_scen} 오라클위험={len(risky)} BLOCKING={n_block}")
    print(f"  validator: {'PASS' if ok else 'FAIL'}  → {outdir}")
    for e in errors[:8]:
        print(f"    - {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
