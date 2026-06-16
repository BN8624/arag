# Golem Studio Step 3 Design 단계 — Planning 패킷 → 모듈 분해 + traceability (§7·§8.2·§13 Step3 그대로)
"""Planning 산출물(FROZEN 계약)을 입력으로 받아 설계팀(lead+reviewer+synthesis)을 돌린다.
산출물(§13 Step3): system_design.md, module_manifest.json, traceability.json, traceability_report.md.
완료기준(§8.2): 모든 REQ가 ≥1 모듈에 배정 / 모든 REQ가 ≥1 테스트에 연결 / 순환참조 없음 /
module_manifest·traceability 존재 / traceability_report는 traceability.json에서 생성 / BLOCKING 0.
validator(§7): REQ→module·REQ→test 연결, manifest에 없는 파일이 trace에 나오면 실패, 없는 test id 실패.

사용:
  python golem/studio/design.py --replay <fixture.json>          # 키 안 씀(plumbing)
  python golem/studio/design.py [--packet <planning_packet>]     # ★키 (사용자 go 뒤에만)
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

from planning import _extract_json            # noqa: E402  (공용 JSON 추출 재사용)
from contract_validator import _find_cycle    # noqa: E402  (순환 탐지 재사용)

MODEL_31 = "gemma-4-31b-it"

# 설계 리뷰 10축(§8.2·§9.2 지향). 각 리뷰어는 하나의 축만 사냥한다.
AXES = [
    "unassigned requirement: a REQ/rule mapped to no module",
    "untested requirement: a REQ with no test linked",
    "circular dependency between modules",
    "god module: one module holding too many responsibilities (should split)",
    "missing forbidden-responsibility: a module without stated what-it-must-NOT-do",
    "unused export: an export no other module imports/uses",
    "state ownership gap: a state field no module is responsible for",
    "interface mismatch: exports declared vs imports expected across modules",
    "over-decomposition: trivial modules that should merge",
    "handoff risk to Build: design a builder would misread",
]

ISSUE_KEYS = ["unassigned_reqs", "untested_reqs", "circular_deps",
              "responsibility_problems", "interface_problems", "risky_assumptions"]

_LEAD_PROMPT = """You are the DESIGN LEAD. Take this FROZEN planning contract and produce a real module
decomposition (do NOT collapse into one big file — split by responsibility). Deterministic Node.js,
CommonJS, stdlib only.

CONCEPT:
{concept}

REQUIREMENTS (each MUST be assigned to >=1 module and >=1 test):
{reqs}

STATE SHAPE:
{state}

TEST IDS available to link: {tests}

Output ONE JSON object EXACTLY:
{{
  "system_design": [
    {{"path": "src/xxx.js", "responsibility": "...", "inputs": "...", "outputs": "...", "forbidden": "..."}}
  ],
  "module_manifest": {{"entry": "main.js", "files": [
    {{"path": "main.js", "exports": [], "imports": ["src/engine.js"]}}
  ]}},
  "traceability": {{
    "REQ-01": {{"text": "...", "design_modules": ["src/xxx.js"], "exports": ["fn"], "tests": ["SCN-001"], "status": "covered"}}
  }}
}}
RULES: every REQ in traceability with >=1 design_module and >=1 test. No circular imports.
module_manifest must be >=3 files (real decomposition). JSON only, no prose."""

_REVIEW_INSTRUCTIONS = """Do NOT redesign. ONLY hunt problems on your axis. Output ONE JSON object EXACTLY
(each a list of short strings, [] if none):
{{
  "unassigned_reqs": [],
  "untested_reqs": [],
  "circular_deps": [],
  "responsibility_problems": [],
  "interface_problems": [],
  "risky_assumptions": [],
  "questions_for_lead": [{{"q": "...", "class": "BLOCKING|ASSUMED|DEFERRED"}}]
}}
JSON only, no prose."""

_REVIEWER_PROMPT = """You are a DESIGN REVIEWER. Your single axis is:
AXIS: {axis}

The design to review (JSON):
{design}

{instructions}
"""

_SYNTHESIS_PROMPT = """You are the DESIGN LEAD doing SYNTHESIS. Your design draft (JSON):
{design}

Reviewers found these issues (JSON):
{issues}

Fix them and finalize. Output ONE JSON object EXACTLY in the same shape as the draft
(system_design, module_manifest, traceability). HARD RULES: every REQ has >=1 design_module AND
>=1 test; no circular imports; every design_module path also appears in module_manifest files;
every test id is one of {tests}. Resolve every BLOCKING reviewer question. JSON only."""


def load_planning(pdir):
    contract = json.loads((pdir / "contract.json").read_text(encoding="utf-8"))
    concept = (pdir / "concept.md").read_text(encoding="utf-8") if (pdir / "concept.md").exists() else ""
    tests = json.loads((pdir / "acceptance_tests.json").read_text(encoding="utf-8"))
    dc = contract.get("data_contract", {})
    rules = dc.get("rules", [])
    reqs = []
    for i, r in enumerate(rules, 1):
        m = re.match(r"\s*(RULE-\d+)\s*[:\-]\s*(.*)", str(r))
        reqs.append({"id": m.group(1) if m else f"REQ-{i:02d}", "text": m.group(2) if m else str(r)})
    test_ids = [t.get("id") for t in tests if t.get("id")]
    return concept, dc.get("state_shape", {}), reqs, test_ids


def design_validate(design, test_ids):
    """§7+§8.2 검증. (ok, errors) 반환."""
    errors = []
    manifest = design.get("module_manifest", {})
    files = manifest.get("files", [])
    paths = {f.get("path") for f in files}
    trace = design.get("traceability", {})
    if len(files) < 3:
        errors.append(f"module_manifest 파일 {len(files)}개 — 실제 분해(>=3) 필요")
    for f in files:
        if f.get("path") != manifest.get("entry") and not f.get("exports"):
            errors.append(f"모듈 {f.get('path')}에 exports 없음")
    if not trace:
        errors.append("traceability 비어 있음")
    for rid, t in trace.items():
        dm = t.get("design_modules") or []
        ts = t.get("tests") or []
        if not dm:
            errors.append(f"{rid}: 배정된 모듈 없음")
        if not ts:
            errors.append(f"{rid}: 연결된 테스트 없음")
        for p in dm:
            if p not in paths:
                errors.append(f"{rid}: manifest에 없는 파일 '{p}'")
        for tid in ts:
            if tid not in test_ids:
                errors.append(f"{rid}: 존재하지 않는 test id '{tid}'")
    graph = {f.get("path"): set(f.get("imports") or []) for f in files}
    cyc = _find_cycle(graph)
    if cyc:
        errors.append(f"순환 의존성: {' -> '.join(cyc)}")
    return (len(errors) == 0, errors)


def _blocking(reviews):
    return [q.get("q", "") for r in reviews for q in (r.get("questions_for_lead") or [])
            if str(q.get("class", "")).upper() == "BLOCKING"]


# ---- caller ----

class FakeCaller:
    def __init__(self, fx):
        self.fx = fx

    def lead(self, ctx):
        return self.fx["design"]

    def reviews(self, design, axes):
        return self.fx["reviews"][:len(axes)]   # 픽스처에 있는 만큼만

    def synth(self, design, issues, test_ids):
        return self.fx.get("synthesis", design)


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

    def reviews(self, design, axes):
        out = [None] * len(axes)
        dj = json.dumps(design, ensure_ascii=False)
        with ThreadPoolExecutor(max_workers=min(len(axes), self.pool.size)) as ex:
            futs = {ex.submit(self._one, _REVIEWER_PROMPT.format(
                axis=ax, design=dj, instructions=_REVIEW_INSTRUCTIONS)): i
                for i, ax in enumerate(axes)}
            for fut in futs:
                out[futs[fut]] = _extract_json(fut.result())
        return out

    def synth(self, design, issues, test_ids):
        return _extract_json(self._one(_SYNTHESIS_PROMPT.format(
            design=json.dumps(design, ensure_ascii=False),
            issues=json.dumps(issues, ensure_ascii=False), tests=test_ids)))


def run(concept, state, reqs, test_ids, caller):
    ctx = {"concept": concept.strip() or "(none)",
           "reqs": "\n".join(f"- {r['id']}: {r['text']}" for r in reqs) or "(none)",
           "state": json.dumps(state, ensure_ascii=False), "tests": test_ids}
    draft = caller.lead(ctx)
    reviews = caller.reviews(draft, AXES)
    issues = {k: [i for r in reviews for i in (r.get(k) or [])] for k in ISSUE_KEYS}
    issues["BLOCKING"] = _blocking(reviews)
    final = caller.synth(draft, issues, test_ids)
    return draft, reviews, issues, final


def _write_packet(final, reqs, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    sd = final.get("system_design", [])
    lines = ["# system_design", ""]
    for m in sd:
        lines += [f"## {m.get('path')}",
                  f"- 책임: {m.get('responsibility', '')}",
                  f"- 입력: {m.get('inputs', '')}",
                  f"- 출력: {m.get('outputs', '')}",
                  f"- 금지: {m.get('forbidden', '')}", ""]
    (outdir / "system_design.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = final.get("module_manifest", {})
    manifest = {"schema_version": "0.1", "module_format": "commonjs", **manifest}
    (outdir / "module_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    trace = final.get("traceability", {})
    (outdir / "traceability.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    # traceability_report.md는 traceability.json에서 생성(§7)
    rl = ["# traceability_report (traceability.json에서 생성)", "",
          "| REQ | text | modules | tests | status |", "|---|---|---|---|---|"]
    for rid, t in trace.items():
        rl.append(f"| {rid} | {str(t.get('text', ''))[:40]} | "
                  f"{', '.join(t.get('design_modules', []))} | "
                  f"{', '.join(t.get('tests', []))} | {t.get('status', '')} |")
    (outdir / "traceability_report.md").write_text("\n".join(rl) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=None)
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    if args.replay:
        fx = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        concept, state, reqs, test_ids = fx["concept"], fx.get("state", {}), fx["reqs"], fx["test_ids"]
        caller = FakeCaller(fx)
        api_calls = 0
    else:
        pdir = Path(args.packet)
        concept, state, reqs, test_ids = load_planning(pdir)
        caller = RealCaller()
        api_calls = None

    draft, reviews, issues, final = run(concept, state, reqs, test_ids, caller)
    outdir = Path(args.out) if args.out else (HERE / "design_packet")
    manifest = _write_packet(final, reqs, outdir)

    ok, errors = design_validate(final, test_ids)
    n_block = len(issues.get("BLOCKING", []))
    status = ["# STATUS (Design)", "",
              f"- REQ 수: {len(reqs)}", f"- 모듈 수: {len(manifest.get('files', []))}",
              f"- 리뷰어 BLOCKING: {n_block}",
              f"- §7·§8.2 validator: {'PASS' if ok else 'FAIL'}",
              *([f"  - {e}" for e in errors[:8]] if errors else []),
              "", f"DESIGN_STATUS: {'COMPLETE' if ok else 'INCOMPLETE'}"]
    (outdir / "STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    print(f"[DESIGN] api_calls={0 if args.replay else api_calls} REQ={len(reqs)} "
          f"모듈={len(manifest.get('files', []))} BLOCKING={n_block}")
    print(f"  validator: {'PASS' if ok else 'FAIL'}  → {outdir}")
    for e in errors[:8]:
        print(f"    - {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
