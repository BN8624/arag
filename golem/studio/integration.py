# Golem Studio Step 7 Integration — 수렴 빌드 중 최종 workspace 선정 + static_gate/grade + final_report (§13 Stage6)
"""Adversarial QA까지 끝난 뒤, 게이트 통과(수렴) 빌드 중 대표 하나를 최종 산출물로 고정하고,
acceptance + edge_cases를 golden(expected) 대비 채점한다. 새 모델 콜 없음(키0) — 기존 graded 런의
빌드를 재사용한다. 산출물(§13 Stage6): final_workspace/ + static_gate_result.json + grade_result.json
+ final_report.md.

선정: 유효(게이트통과) 빌드 중 '모든 케이스에서 다수합의와 일치한 수'가 가장 많은 빌드(동률=낮은 attempt).
채점: 최종 빌드 출력 vs golden expected. 단 채점 표면 = 출력계약 키(turn/energy/productionRate/gameStatus/
logs)뿐 — golden의 levels 등 미출력 키는 'OUTPUT_SURFACE_SKIP'로 표기(G39: 재고 싶으면 출력에 넣어야 잰다).

사용:
  python golem/studio/integration.py [--run <build_runs/graded-...>]   # 키 안 씀
"""

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

import static_gate                       # noqa: E402
from build_graded import _norm_output    # noqa: E402


def _latest_run():
    runs = sorted((HERE / "build_runs").glob("graded-*"), reverse=True)
    return runs[0] if runs else None


def _run_case(ws, inputs, idx):
    (ws / "scenarios.json").write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
    try:
        r = subprocess.run(["node", "main.js", "--scenario", str(idx)], cwd=str(ws),
                           capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None
    return dict(_norm_output(r.stdout)) if r.returncode == 0 else None


def _golden_norm(expected, output_keys):
    """golden expected를 출력표면 키로 투영. (gradeable_dict, skipped_keys)."""
    g, skipped = {}, []
    for k, v in (expected or {}).items():
        if k not in output_keys:
            skipped.append(k)
            continue
        g[k] = json.dumps(v) if k == "logs" else str(v)
    return g, skipped


def grade_case(out, expected, output_keys):
    """최종 빌드 출력 dict를 golden에 대조. (status, detail)."""
    if out is None:
        return "CRASH", {}
    g, skipped = _golden_norm(expected, output_keys)
    if not g:
        return "NO_GRADEABLE_KEYS", {"skipped": skipped}
    mism = {k: {"got": out.get(k), "want": v} for k, v in g.items() if out.get(k) != v}
    return ("PASS" if not mism else "FAIL"), {"mismatch": mism, "skipped": skipped}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None)
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--specqa", default=str(HERE / "specqa_packet"))
    ap.add_argument("--adversarial", default=str(HERE / "adversarial_packet"))
    ap.add_argument("--out", default=str(HERE / "integration_packet"))
    args = ap.parse_args(argv)

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    run = Path(args.run) if args.run else _latest_run()
    if not run or not run.exists():
        print("[INTEG] graded 런이 없음 — 먼저 build_graded 실행 필요")
        return 1

    # 출력키는 계약 state_shape에서 도출(스칼라+logs, config 등 dict 제외) — 카드 무관
    contract = json.loads((Path(args.packet) / "contract.json").read_text(encoding="utf-8"))
    state_shape = contract.get("data_contract", {}).get("state_shape", {})
    output_keys = {k for k, v in state_shape.items() if not isinstance(v, dict)}
    cpath = Path(args.packet) / "concept.md"
    card_label = (cpath.read_text(encoding="utf-8").strip().split(".")[0][:80]
                  if cpath.exists() else Path(args.packet).name)

    grading_keys = {"id", "expected", "oracle_risk", "covers_reqs"}
    def _case_input(c):  # 실행입력 = 채점메타 뺀 전체(build_graded와 동일 규약)
        return {k: v for k, v in c.items() if k not in grading_keys}

    acc = json.loads((Path(args.specqa) / "acceptance_tests_draft.json").read_text(encoding="utf-8"))
    adv = Path(args.adversarial) / "edge_cases.json"
    edges = json.loads(adv.read_text(encoding="utf-8")) if adv.exists() else []
    cases = [{"id": c["id"], "kind": "acceptance", "input": _case_input(c), "expected": c.get("expected")}
             for c in acc] + \
            [{"id": c["id"], "kind": "edge", "input": _case_input(c), "expected": c.get("expected")}
             for c in edges]
    inputs = [c["input"] for c in cases]

    builds = sorted(d for d in run.glob("attempt*/workspace") if (d / "main.js").exists())
    # 유효 빌드 = 케이스1을 정상 실행
    valid = [b for b in builds if _run_case(b, inputs, 1) is not None]
    if not valid:
        print(f"[INTEG] {run.name}: 유효 빌드 0 — 선정 불가")
        return 1

    # 케이스별 출력 수집 + 다수합의
    outs = {b: [_run_case(b, inputs, i) for i in range(1, len(cases) + 1)] for b in valid}
    majority = []
    for j in range(len(cases)):
        votes = [json.dumps(outs[b][j], sort_keys=True) for b in valid if outs[b][j] is not None]
        majority.append(Counter(votes).most_common(1)[0][0] if votes else None)
    # 선정: 다수합의 일치 수 최다(동률=낮은 attempt 이름)
    def agree_count(b):
        return sum(1 for j in range(len(cases))
                   if outs[b][j] is not None and json.dumps(outs[b][j], sort_keys=True) == majority[j])
    # 선정: static_gate 통과 우선 → 다수합의 일치 최다 → 낮은 attempt
    gate_ok = {b: static_gate.check(str(b))["ok"] for b in valid}
    final = max(valid, key=lambda b: (gate_ok[b], agree_count(b), -valid.index(b)))

    sg = static_gate.check(str(final))

    # grade: 최종 빌드 vs golden
    grades = []
    for j, c in enumerate(cases):
        status, detail = grade_case(outs[final][j], c["expected"], output_keys)
        grades.append({"id": c["id"], "kind": c["kind"], "status": status, **detail})
    n_pass = sum(1 for g in grades if g["status"] == "PASS")
    n_gradeable = sum(1 for g in grades if g["status"] in ("PASS", "FAIL", "CRASH"))

    outdir = Path(args.out)
    final_ws = outdir / "final_workspace"
    if final_ws.exists():
        shutil.rmtree(final_ws)
    shutil.copytree(final, final_ws)
    for junk in final_ws.glob("scenarios.json"):  # 입력은 산출물이 아니므로 제거
        junk.unlink()

    (outdir / "static_gate_result.json").write_text(json.dumps(sg, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "grade_result.json").write_text(json.dumps(
        {"run": run.name, "final_attempt": final.parent.name, "valid_builds": len(valid),
         "grade_pass": n_pass, "gradeable": n_gradeable, "total_cases": len(cases), "cases": grades},
        ensure_ascii=False, indent=2), encoding="utf-8")

    n_files = len(list(final_ws.rglob("*.js")))
    crashes = [g["id"] for g in grades if g["status"] == "CRASH"]
    fails = [g["id"] for g in grades if g["status"] == "FAIL"]
    report = [
        "# Final Report — Golem Studio", "",
        f"- 카드: {card_label}",
        f"- 소스 런: {run.name} (유효 빌드 {len(valid)})",
        f"- 최종 산출물: {final.parent.name} → `final_workspace/` (파일 {n_files}개)",
        f"- static_gate: {'PASS' if sg['ok'] else 'FAIL — ' + sg.get('reason', '')}",
        f"- 채점(golden 대비): {n_pass}/{n_gradeable} PASS"
        + (f", FAIL={fails}" if fails else "") + (f", CRASH={crashes}" if crashes else ""),
        f"- acceptance {sum(1 for c in cases if c['kind']=='acceptance')} + edge {sum(1 for c in cases if c['kind']=='edge')} = {len(cases)} 케이스",
        "",
        "## 채점 상세",
        *[f"- [{g['status']}] {g['id']} ({g['kind']})"
          + (f" — mismatch {g['mismatch']}" if g.get('mismatch') else "")
          + (f" — 출력표면밖 {g['skipped']}" if g.get('skipped') else "")
          for g in grades],
    ]
    (outdir / "final_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"[INTEG] 런={run.name} 유효={len(valid)} 최종={final.parent.name} 파일={n_files}")
    print(f"  static_gate: {'PASS' if sg['ok'] else 'FAIL'}  채점: {n_pass}/{n_gradeable} PASS"
          + (f" FAIL={fails}" if fails else "") + (f" CRASH={crashes}" if crashes else ""))
    print(f"  → {outdir}")
    return 0 if (sg["ok"] and not crashes and not fails) else 1


if __name__ == "__main__":
    raise SystemExit(main())
