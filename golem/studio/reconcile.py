# Golem Studio 자동 해소 — Build 합의 vs oracle(golden) 자동 diff + 모델 진단/해소 (수작업 제거)
"""이번까지 손으로 하던 일을 코드로 옮긴다: (1) graded 런의 게이트통과 빌드 합의를 시나리오 golden과
자동 대조해 불일치를 뽑고(키0), (2) 각 불일치를 31B에 되먹여 진단·해소한다.

진단 3종(계약이 진실):
  CONTRACT_AMBIGUOUS — 규칙이 안 박음. 두 읽기 다 그럴듯 → contract_fix 제안.
  ORACLE_BUG         — 규칙이 박았고 빌드 합의가 맞음(oracle expected가 틀림) → scenario_fix.
  BUILD_BUG          — 규칙이 박았고 oracle가 맞음(빌드가 틀림) → 재빌드 필요(계약/시나리오 안 고침).
분류: AUTO(명확한 디폴트 → 자동 적용 가능) / ESCALATE(게임 거동이 갈리는 진짜 설계 fork → 사람에게).

--apply: AUTO 건만 자동 적용(ORACLE_BUG=시나리오 expected 교정, CONTRACT_AMBIGUOUS+AUTO=규칙 교체).
         ESCALATE는 절대 자동 적용 안 함 — 사람 결정 대기.

사용:
  python golem/studio/reconcile.py --run <build_runs/graded-...> --packet <pp> --specqa <sp>          # diff만(키0)
  python golem/studio/reconcile.py --run ... --packet ... --specqa ... --resolve [--apply]            # ★키
  python golem/studio/reconcile.py --replay <fixture.json>                                            # 키0(plumbing)
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

from build_graded import _norm_output    # noqa: E402
from planning import _extract_json       # noqa: E402

MODEL_31 = "gemma-4-31b-it"
GRADING_KEYS = {"id", "expected", "oracle_risk", "covers_reqs"}

_RESOLVE_PROMPT = """You are the RECONCILER for a deterministic game. The BUILD CONSENSUS (what most independent
implementations computed) disagrees with the ORACLE (the spec's stated expected) on ONE scenario. Decide WHY,
using ONLY the frozen rules below as the source of truth.

RULES:
{rules}

SCENARIO INPUT:
{input}

DIFFERING KEYS (build-consensus value vs oracle-expected value):
{diffs}

Output ONE JSON object EXACTLY:
{{
  "diagnosis": "CONTRACT_AMBIGUOUS | ORACLE_BUG | BUILD_BUG",
  "correct_value": {{"<key>": <value per the rules, if determinable, else omit>}},
  "contract_fix": "<if CONTRACT_AMBIGUOUS: the EXACT full replacement text for the single rule that is
                    ambiguous (start with its 'R-..'/'RULE-..' id), choosing the more sensible default;
                    else null>",
  "class": "AUTO | ESCALATE",
  "reason": "<one line>"
}}
Rules: ORACLE_BUG = rules pin it and BUILD consensus is right. BUILD_BUG = rules pin it and ORACLE is right.
CONTRACT_AMBIGUOUS = rules do not pin it. Use ESCALATE only when CONTRACT_AMBIGUOUS AND the choice materially
changes game behavior (a genuine design fork). JSON only, no prose."""


def output_keys_of(contract):
    ss = contract.get("data_contract", {}).get("state_shape", {})
    return {k for k, v in ss.items() if not isinstance(v, dict)}


def _case_input(c):
    return {k: v for k, v in c.items() if k not in GRADING_KEYS}


def _run_one(ws, inputs, idx):
    (ws / "scenarios.json").write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
    try:
        r = subprocess.run(["node", "main.js", "--scenario", str(idx)], cwd=str(ws),
                           capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None
    return dict(_norm_output(r.stdout)) if r.returncode == 0 else None


def diff(run_dir, scenarios, output_keys):
    """게이트통과 빌드 합의 vs golden 자동 대조. (disagreements, n_valid) ."""
    inputs = [_case_input(c) for c in scenarios]
    builds = sorted(d for d in run_dir.glob("attempt*/workspace") if (d / "main.js").exists())
    valid = [b for b in builds if _run_one(b, inputs, 1) is not None]
    disagreements = []
    for j, sc in enumerate(scenarios, 1):
        outs = [_run_one(b, inputs, j) for b in valid]
        votes = [json.dumps(o, sort_keys=True) for o in outs if o is not None]
        top = Counter(votes).most_common(1)[0] if votes else (None, 0)
        consensus = json.loads(top[0]) if top[0] else None
        exp = sc.get("expected") or {}
        gnorm = {k: (json.dumps(exp[k]) if k == "logs" else str(exp[k]))
                 for k in (set(exp) & output_keys)}
        differing = {k: {"consensus": (consensus or {}).get(k), "oracle": v}
                     for k, v in gnorm.items() if not consensus or consensus.get(k) != v}
        if differing:
            disagreements.append({"id": sc["id"], "input": _case_input(sc), "differing": differing,
                                  "agreement": {"agree": top[1], "total": len(votes)}})
    return disagreements, len(valid)


class FakeCaller:
    def __init__(self, fx):
        self.fx = {v["id"]: v for v in fx.get("verdicts", [])}

    def resolve(self, rules, d):
        return self.fx.get(d["id"], {"diagnosis": "CONTRACT_AMBIGUOUS", "class": "ESCALATE",
                                     "reason": "(fixture default)"})


class RealCaller:
    def __init__(self):
        import os
        os.environ["GENERATOR_MODEL"] = MODEL_31
        os.environ["CRITIC_MODEL"] = MODEL_31
        from config import get_api_keys
        from llm import KeyPool
        self.pool = KeyPool(get_api_keys(), models=[MODEL_31])

    def resolve(self, rules, d):
        from llm import LLMClient
        prompt = _RESOLVE_PROMPT.format(
            rules="\n".join(f"- {r}" for r in rules),
            input=json.dumps(d["input"], ensure_ascii=False),
            diffs="\n".join(f"- {k}: build={v['consensus']!r} oracle={v['oracle']!r}"
                            for k, v in d["differing"].items()))
        with self.pool.checkout() as key:
            return _extract_json(LLMClient(api_key=key).generate("critic", prompt))


def apply_fixes(verdicts, contract_path, scen_path, scenarios):
    """AUTO 건만 적용. ORACLE_BUG→시나리오 expected 교정, CONTRACT_AMBIGUOUS+AUTO→규칙 교체. (applied, list)."""
    applied = []
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    rules = contract["data_contract"]["rules"]
    scen_by_id = {s["id"]: s for s in scenarios}
    for v in verdicts:
        diag, cls = v.get("diagnosis"), v.get("class")
        if cls != "AUTO":
            continue
        if diag == "ORACLE_BUG" and v.get("correct_value"):
            sc = scen_by_id.get(v["id"])
            if sc is not None:
                sc.setdefault("expected", {}).update(
                    {k: (json.loads(val) if isinstance(val, str) and val[:1] in "[{\"" else val)
                     for k, val in v["correct_value"].items()})
                applied.append(f"{v['id']}: ORACLE_BUG→expected {v['correct_value']}")
        elif diag == "CONTRACT_AMBIGUOUS" and v.get("contract_fix"):
            fix = v["contract_fix"].strip()
            rid = fix.split(":")[0].strip()
            for i, r in enumerate(rules):
                if str(r).startswith(rid):
                    rules[i] = fix
                    applied.append(f"{v['id']}: CONTRACT_FIX {rid}")
                    break
    if any("CONTRACT_FIX" in a for a in applied):
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    if any("ORACLE_BUG" in a for a in applied):
        scen_path.write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


def _stringify(k, val):
    """diff()의 gnorm과 같은 방식으로 값을 문자열화 — 빌드 합의값과 비교 가능하게."""
    return json.dumps(val) if k == "logs" else str(val)


def apply_low_consensus_guard(verdicts, diffs):
    """저합의(다수파가 유효빌드 과반 미달) 시나리오의 AUTO를 ESCALATE로 강등(G50).
    저합의 위에선 '빌드 다수결이 oracle보다 옳다'를 신뢰할 수 없다 — 1표짜리 합의를
    근거로 expected를 자동교정하면 confidently-wrong(T1 고결합서 실측). 사람 결정으로 돌린다.
    방치형·발열(합의 1.0)은 과반 충족이라 영향 없음. 반환: 강등된 id 목록."""
    agr = {d["id"]: d.get("agreement") or {} for d in diffs}
    guarded = []
    for v in verdicts:
        a = agr.get(v["id"], {})
        total, agree = a.get("total", 0), a.get("agree", 0)
        if v.get("class") == "AUTO" and total and agree <= total / 2:
            v["class"] = "ESCALATE"
            v["low_consensus_guard"] = True
            v["reason"] = f"[저합의 {agree}/{total}] " + v.get("reason", "")
            guarded.append(v["id"])
    return guarded


def verify_auto_fixes(verdicts, diffs, ledger_path, run_id):
    """AUTO 적용 후 키0 검증 기록(게이트 아님, 측정용). G48 1순위 지표=AUTO 정확률.
    diffs: diff()/_golden_diff 항목 [{id, input, differing:{k:{consensus,oracle}}}].
    - ORACLE_BUG: 적용한 expected가 빌드 합의와 일치하나(다운스트림 일관성, 키0).
      불일치면 SUSPECT — confidently-wrong AUTO 후보(안 보이는 위험).
    - CONTRACT_AMBIGUOUS: 규칙 교체 → 재빌드 전엔 빌드거동 검증 불가(needs_rebuild 표시).
    - 되돌림: 같은 (id,key)를 과거 적용값과 다른 값으로 덮으면 flip(불안정) 기록.
    ledger(jsonl)는 카드별로 누적된다."""
    ledger_path = Path(ledger_path)
    ledger = []
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ledger.append(json.loads(line))
    diff_by_id = {d["id"]: d.get("differing", {}) for d in diffs}
    agr_by_id = {d["id"]: d.get("agreement") or {} for d in diffs}
    checks, new_entries = [], []
    for v in verdicts:
        if v.get("class") != "AUTO":
            continue
        sid, diag = v["id"], v.get("diagnosis")
        a = agr_by_id.get(sid, {})
        consensus_rate = round(a["agree"] / a["total"], 3) if a.get("total") else None
        if diag == "ORACLE_BUG" and v.get("correct_value"):
            differing = diff_by_id.get(sid, {})
            consistent = all(
                str(differing.get(k, {}).get("consensus")) == _stringify(k, val)
                for k, val in v["correct_value"].items() if k in differing)
            status = "downstream_consistent" if consistent else "SUSPECT:applied!=consensus"
            entries = [{"key": k, "value": _stringify(k, val)} for k, val in v["correct_value"].items()]
        elif diag == "CONTRACT_AMBIGUOUS" and v.get("contract_fix"):
            status = "needs_rebuild_to_verify"
            entries = [{"key": v["contract_fix"].split(":")[0].strip(), "value": v["contract_fix"].strip()}]
        else:
            continue
        reverted = any(e["id"] == sid and e["key"] == ne["key"] and e["value"] != ne["value"]
                       for e in ledger for ne in entries)
        checks.append({"id": sid, "diagnosis": diag, "status": status,
                       "consensus_rate": consensus_rate, "reverted_prior": reverted})
        for ne in entries:
            new_entries.append({"run": run_id, "id": sid, "diagnosis": diag, **ne})
    if new_entries:
        with ledger_path.open("a", encoding="utf-8") as f:
            for e in new_entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=None)
    ap.add_argument("--run", default=None)
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--specqa", default=str(HERE / "specqa_packet"))
    ap.add_argument("--resolve", action="store_true", help="불일치를 모델로 진단/해소(★키)")
    ap.add_argument("--apply", action="store_true", help="AUTO 건 자동 적용(ESCALATE는 제외)")
    args = ap.parse_args(argv)

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    if args.replay:
        fx = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        rules = fx["rules"]
        disagreements = fx["disagreements"]
        caller = FakeCaller(fx)
        n_valid = fx.get("n_valid", 0)
    else:
        contract = json.loads((Path(args.packet) / "contract.json").read_text(encoding="utf-8"))
        rules = contract["data_contract"]["rules"]
        scenarios = json.loads((Path(args.specqa) / "acceptance_tests_draft.json").read_text(encoding="utf-8"))
        run = Path(args.run) if args.run else max((HERE / "build_runs").glob("graded-*"), default=None)
        if not run or not run.exists():
            print("[RECONCILE] graded 런 필요")
            return 1
        disagreements, n_valid = diff(run, scenarios, output_keys_of(contract))
        caller = RealCaller() if args.resolve else None

    print(f"[RECONCILE] 유효빌드 {n_valid}, 불일치 시나리오 {len(disagreements)}")
    for d in disagreements:
        print(f"  - {d['id']}: " + ", ".join(
            f"{k}(build={v['consensus']} vs oracle={v['oracle']})" for k, v in d["differing"].items()))
    if not disagreements:
        print("  합의 == oracle (전부 일치). 해소 불필요.")
        return 0
    if not (args.resolve or args.replay):
        print("  → --resolve 로 모델 진단/해소(★키).")
        return 0

    verdicts = []
    for d in disagreements:
        v = caller.resolve(rules, d)
        v["id"] = d["id"]
        verdicts.append(v)
        print(f"  [{v.get('diagnosis')}/{v.get('class')}] {d['id']}: {v.get('reason', '')}")

    guarded = apply_low_consensus_guard(verdicts, disagreements)
    if guarded:
        print(f"  [저합의 가드] AUTO→ESCALATE 강등 {len(guarded)}: {guarded}")
    applied = []
    auto_verification = []
    if args.apply and not args.replay:
        applied = apply_fixes(verdicts, Path(args.packet) / "contract.json",
                              Path(args.specqa) / "acceptance_tests_draft.json", scenarios)
        auto_verification = verify_auto_fixes(
            verdicts, disagreements, Path(args.specqa) / "auto_fix_ledger.jsonl",
            Path(args.run).name if args.run else "?")
    escalate = [v for v in verdicts if v.get("class") == "ESCALATE"]

    if not args.replay:
        out = Path(args.specqa).parent / "reconcile_report.json"
        out.write_text(json.dumps({"run": Path(args.run).name if args.run else None,
                                   "verdicts": verdicts, "applied": applied,
                                   "auto_verification": auto_verification,
                                   "low_consensus_guarded": guarded,
                                   "escalate": [v["id"] for v in escalate]},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[RECONCILE] 자동적용 {len(applied)}건, 사람결정(ESCALATE) {len(escalate)}건")
    for a in applied:
        print(f"  적용: {a}")
    for c in auto_verification:
        flag = " ★되돌림" if c["reverted_prior"] else ""
        print(f"  [AUTO검증] {c['id']}: {c['status']} (합의율 {c['consensus_rate']}){flag}")
    for v in escalate:
        print(f"  ★ESCALATE {v['id']}: {v.get('reason', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
