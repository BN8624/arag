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

INPUT (FIXED — `scenarios.json` is a JSON array; `node main.js --scenario N` reads element N-1, 1-based,
and runs it deterministically). Match this EXACT input format (these are the real scenario elements you must
support — infer the shape precisely from them):
{input_examples}
Read the scenario element's setup / initial fields AND its config from the element itself, apply its actions
in order, then print the final state. Use the config values PROVIDED in the element — never invent your own.
NEVER crash on a missing optional field.

OUTPUT CONTRACT (FIXED — print EXACTLY these lines, this order, nothing else):
{output_lines}
All numeric state values are integers (use floor where a rule specifies). The `logs` line is a JSON array of
log strings in order (e.g. [] if none); emit a log ONLY where a rule explicitly says to, with that exact
wording, and never as a separate bare line.

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


def _output_lines(state_shape):
    """출력계약 줄을 state_shape에서 도출 — 최상위 스칼라 필드 + logs (중첩 dict=config 등은 미출력)."""
    lines = []
    for k, v in state_shape.items():
        if k == "logs" or isinstance(v, dict):
            continue
        lines.append(f"{k}: <{v}>")
    lines.append('logs: <a JSON array of strings in order, e.g. [] if none>')
    return "\n".join(lines)


def build_prompt(concept, contract, manifest, sysd, scen_inputs):
    rules = contract.get("data_contract", {}).get("rules", [])
    state_shape = contract.get("data_contract", {}).get("state_shape", {})
    examples = json.dumps(scen_inputs[:3], ensure_ascii=False, indent=2)
    files_desc = "\n".join(
        f"- {f['path']}: exports {f.get('exports', [])}, imports {f.get('imports', [])}"
        for f in manifest.get("files", []))
    return _PROMPT.format(concept=concept.strip() or "(none)",
                          rules="\n".join(f"- {r}" for r in rules) or "(none)",
                          system_design=sysd.strip() or "(none)", files=files_desc,
                          input_examples=examples, output_lines=_output_lines(state_shape))


def _norm_output(stdout):
    """key:value 출력을 정규화(dict) — 합의 비교용. 줄 순서 무관."""
    d = {}
    for line in stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    if "logs" in d:  # 공백·따옴표 차이로 헛갈리지 않게 JSON 정규화(순서는 보존)
        try:
            d["logs"] = json.dumps(json.loads(d["logs"]))
        except Exception:  # noqa: BLE001
            pass
    return tuple(sorted(d.items()))


def classify_attempt_failure(reason):
    """게이트 실패 사유를 기존 라벨 어휘로 사전분류(키0, G48). 카드 탓 전에 INFRA/HARNESS 먼저 분리.
    INFRA=plan2 INFRA_FAIL(api·network·쿼터) / HARNESS=plan2 HARNESS_FAIL(우리 도구 크래시) /
    CARD=plan2 MODEL_FAIL(생성 코드·계약 난이도: static/contract/스모크 실패). 새 taxonomy 도입 아님."""
    from observability import INFRA_MARKERS
    t = str(reason).lower()
    if t.startswith("infra:") or any(m in t for m in INFRA_MARKERS):
        return "INFRA"
    if t.startswith("harness:"):
        return "HARNESS"
    return "CARD"


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


def _golden_diff(passed_outputs, scenarios, gradeable, contract):
    """합의(다수) vs golden(expected) 자동 대조 — 출력표면 키만. 수작업 diff 제거(키0).
    각 항목에 reconcile.resolve가 쓰는 `input`(채점메타 제외 시나리오)도 담는다."""
    ss = contract.get("data_contract", {}).get("state_shape", {})
    output_keys = {k for k, v in ss.items() if not isinstance(v, dict)}
    grading = {"id", "expected", "oracle_risk", "covers_reqs"}
    by_id = {s["id"]: s for s in scenarios}
    diffs = []
    for sid in gradeable:
        votes = [outs[sid] for outs in passed_outputs.values() if outs.get(sid) is not None]
        if not votes:
            continue
        cons = dict(Counter(votes).most_common(1)[0][0])
        sc = by_id.get(sid, {})
        exp = sc.get("expected") or {}
        gnorm = {k: (json.dumps(exp[k]) if k == "logs" else str(exp[k]))
                 for k in (set(exp) & output_keys)}
        d = {k: {"consensus": cons.get(k), "oracle": v} for k, v in gnorm.items() if cons.get(k) != v}
        if d:
            diffs.append({"id": sid, "input": {k: v for k, v in sc.items() if k not in grading},
                          "differing": d})
    return diffs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--design", default=str(HERE / "design_packet"))
    ap.add_argument("--specqa", default=str(HERE / "specqa_packet"))
    ap.add_argument("--cap", type=int, default=11)
    ap.add_argument("--out", default=None)
    ap.add_argument("--reconcile", action="store_true",
                    help="빌드 후 합의-vs-oracle 불일치를 모델로 진단/라우팅(★키)")
    ap.add_argument("--apply", action="store_true",
                    help="--reconcile 진단 중 AUTO만 자동 적용(ESCALATE는 사람 대기)")
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
    grading_keys = {"id", "expected", "oracle_risk", "covers_reqs"}
    scen_inputs = [{k: v for k, v in s.items() if k not in grading_keys} for s in scenarios]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(args.out) if args.out else (HERE / "build_runs" / f"graded-{run_id}")
    prompt = build_prompt(concept, contract, manifest, sysd, scen_inputs)
    pool = KeyPool(get_api_keys(), models=[MODEL_31])
    print(f"[BUILD v1] design 4모듈 manifest, 시나리오 {len(scenarios)}(채점가능 {len(gradeable)}), "
          f"cap={args.cap} keys={pool.size}, run={run_id}")

    manifest_v = {"schema_version": "0.1", "module_format": "commonjs", **manifest}
    lock = threading.Lock()
    passed_outputs = {}
    failures = []
    cracked = None

    def worker(attempt):
        try:
            with pool.checkout() as key:
                resp = LLMClient(api_key=key).generate("critic", prompt)
        except AllKeysExhausted:
            raise
        except Exception as e:  # noqa: BLE001 — 생성 단계 실패는 api/network(INFRA)
            return attempt, False, f"infra: gen {type(e).__name__}: {e}", {}
        ws = base / f"attempt{attempt:02d}" / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        try:  # 파싱·쓰기·게이트는 우리 하네스 — 여기 크래시는 HARNESS(카드 탓 아님), 런 안 깨고 기록
            write_candidate(ws, parse_files(resp))
            (ws / "scenarios.json").write_text(json.dumps(scen_inputs, ensure_ascii=False), encoding="utf-8")
            ok, reason, outputs = gate_and_run(ws, manifest_v, scenarios)
        except Exception as e:  # noqa: BLE001
            return attempt, False, f"harness: {type(e).__name__}: {e}", {}
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
            else:
                with lock:
                    failures.append(reason)

    overall, report = consensus(passed_outputs, gradeable)
    golden_diffs = _golden_diff(passed_outputs, scenarios, gradeable, contract)
    fail_classes = Counter(classify_attempt_failure(r) for r in failures)
    base.mkdir(parents=True, exist_ok=True)
    (base / "consensus.json").write_text(json.dumps(
        {"gate_passed": len(passed_outputs), "cap": args.cap,
         "gradeable": gradeable, "overall_agreement": overall, "per_scenario": report,
         "golden_diffs": golden_diffs,
         "failure_classes": dict(fail_classes), "gate_failed_reasons": failures},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[BUILD v1] 게이트 통과 {len(passed_outputs)}/{args.cap}, "
          f"합의 채점(채점가능 {len(gradeable)}): 전체 일치율 {overall}")
    if failures:  # 실패 사전분류(G48): 카드 탓 전에 INFRA/HARNESS 먼저 분리
        print("  [실패 사전분류] " + ", ".join(f"{k}={v}" for k, v in fail_classes.items())
              + "  (INFRA·HARNESS는 카드 실패로 안 셈 — 하네스 수정 후 재실행)")
    for sid, r in report.items():
        print(f"    {sid}: 합의 {r['agree']}/{r['total']} (일치율 {r['rate']})")
    if golden_diffs:  # 합의-vs-oracle 자동 diff(키0) — 수작업 제거
        print(f"  [합의 vs oracle] 불일치 {len(golden_diffs)}건 — reconcile --resolve로 진단(★키):")
        for d in golden_diffs:
            print("    - " + d["id"] + ": " + ", ".join(
                f"{k}(합의={v['consensus']} vs oracle={v['oracle']})" for k, v in d["differing"].items()))
    else:
        print("  [합의 vs oracle] 전부 일치.")

    if args.reconcile and golden_diffs:  # T0: diff → resolve(★키) → AUTO apply → ESCALATE/BUILD_BUG 리포트
        import reconcile  # 늦은 import(순환 방지)
        rules = contract["data_contract"]["rules"]
        rc = reconcile.RealCaller()
        verdicts = []
        for d in golden_diffs:
            v = rc.resolve(rules, d)
            v["id"] = d["id"]
            verdicts.append(v)
            print(f"    [{v.get('diagnosis')}/{v.get('class')}] {d['id']}: {v.get('reason', '')}")
        applied = reconcile.apply_fixes(
            verdicts, Path(args.packet) / "contract.json",
            Path(args.specqa) / "acceptance_tests_draft.json", scenarios) if args.apply else []
        auto_verification = reconcile.verify_auto_fixes(
            verdicts, golden_diffs, Path(args.specqa) / "auto_fix_ledger.jsonl", run_id) \
            if args.apply else []
        escalate = [v["id"] for v in verdicts if v.get("class") == "ESCALATE"]
        build_bugs = [v["id"] for v in verdicts if v.get("diagnosis") == "BUILD_BUG"]
        (base / "reconcile_report.json").write_text(json.dumps(
            {"verdicts": verdicts, "applied": applied, "auto_verification": auto_verification,
             "escalate": escalate, "build_bugs": build_bugs},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [reconcile] 자동적용 {len(applied)}, ESCALATE(사람) {len(escalate)}, BUILD_BUG {len(build_bugs)}")
        for a in applied:
            print(f"    적용: {a}")
        for c in auto_verification:
            flag = " ★되돌림" if c["reverted_prior"] else ""
            print(f"    [AUTO검증] {c['id']}: {c['status']}{flag}")
        if build_bugs:
            print(f"    ★재빌드 권장(BUILD_BUG {build_bugs}) — 계약 정본 그대로, 빌드만 다시.")
        for sid in escalate:
            print(f"    ★ESCALATE {sid} — 사람 결정 필요.")

    print(f"[BUILD v1] → {base}")
    return 0 if passed_outputs else 1


if __name__ == "__main__":
    raise SystemExit(main())
