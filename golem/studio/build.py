# Golem Studio Build 단계 — FROZEN 계약을 gemma가 구현, static_gate + v0.1 매니페스트 정합 + 스모크로 게이트
"""Planning 패킷의 FROZEN 계약(interface_contract=매니페스트, data_contract=규칙)을 그대로 gemma에
줘서 멀티파일 구현을 받는다. 게이트(콜0 위주):
  1) static_gate.check  — 구문·멀티파일·npm·Math.random·고아모듈
  2) contract_validator.validate — 코드가 계약 매니페스트(파일/export/import)와 정합한가 (v0.1 재사용)
  3) 스모크 실행 — node main.js --scenario 1 이 크래시 없이 key:value를 출력하나
Build v0는 golden 정확일치(오라클)를 안 한다 — '계약대로 굴러가나'까지. 정확채점은 v1.

사용:
  python golem/studio/build.py --replay <build_response.txt>   # 키 안 씀(plumbing)
  python golem/studio/build.py [--packet <dir>] [--cap 11]      # ★키 (사용자 go 뒤에만)
"""

import argparse
import json
import subprocess
import sys
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))               # contract_validator
sys.path.insert(0, str(HERE.parent))        # golem(driver, static_gate)
sys.path.insert(0, str(HERE.parent.parent))  # arag 루트(llm, config)

import contract_validator                     # noqa: E402
import static_gate                            # noqa: E402
from driver import parse_files, write_candidate  # noqa: E402  (FILE 마커 멀티파일 파서 재사용)

MODEL_31 = "gemma-4-31b-it"

_BUILD_PROMPT = """You are the BUILD engineer. Implement this FROZEN game contract EXACTLY. Do not change the
file list, exports, or rules. Deterministic Node.js, CommonJS, stdlib only, NO Math.random.

CONCEPT:
{concept}

RULES (data contract):
{rules}

STATE SHAPE:
{state}

FILES YOU MUST CREATE (exact paths/exports/imports, named exports only — `exports.Name = ...` or
`module.exports = {{ Name }}`; NO `module.exports = function`):
{files}

SCENARIOS to hardcode (runnable as `node main.js --scenario N`, N=1..{nscen}):
{scenarios}

OUTPUT CONTRACT: `node main.js --scenario N` prints ONLY lines `key: value` (value = integer or short
string) for the final state, nothing else. Fully deterministic.

Output every file with EXACT markers, one per file:
=== FILE: <path> ===
<file body>
"""


def load_packet(pdir):
    contract = json.loads((pdir / "contract.json").read_text(encoding="utf-8"))
    concept = (pdir / "concept.md").read_text(encoding="utf-8") if (pdir / "concept.md").exists() else ""
    tests = json.loads((pdir / "acceptance_tests.json").read_text(encoding="utf-8"))
    ic = contract.get("interface_contract", {})
    manifest = {"schema_version": "0.1", "module_format": "commonjs",
                "entry": ic.get("entry", "main.js"), "files": ic.get("files", [])}
    return contract, concept, tests, manifest


def build_prompt(contract, concept, tests, manifest):
    dc = contract.get("data_contract", {})
    files_desc = "\n".join(
        f"- {f['path']}: exports {f.get('exports', [])}, imports {f.get('imports', [])}"
        for f in manifest["files"])
    return _BUILD_PROMPT.format(
        concept=concept.strip() or "(none)",
        rules="\n".join(f"- {r}" for r in dc.get("rules", [])) or "(none)",
        state=json.dumps(dc.get("state_shape", {}), ensure_ascii=False),
        files=files_desc,
        nscen=max(1, len(tests)),
        scenarios=json.dumps(tests, ensure_ascii=False, indent=2))


def gate(workspace, manifest, nscen):
    """3중 게이트. (ok, reason, detail) 반환."""
    sg = static_gate.check(str(workspace))
    if not sg["ok"]:
        return False, f"static_gate: {sg['reason']}", sg
    mpath = workspace.parent / "module_manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    cv = contract_validator.validate(workspace, mpath)
    if not cv["ok"]:
        return False, f"contract_validator: {cv['errors'][:3]}", cv
    # 스모크: scenario 1 크래시 없이 key:value 출력?
    try:
        r = subprocess.run(["node", "main.js", "--scenario", "1"], cwd=str(workspace),
                           capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "smoke: 타임아웃(30s, 무한루프/입력대기 의심)", None
    if r.returncode != 0:
        return False, f"smoke: exit {r.returncode}: {r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else '?'}", None
    if ":" not in r.stdout:
        return False, f"smoke: key:value 출력 없음 (stdout={r.stdout[:120]!r})", None
    return True, "ok", {"smoke_stdout": r.stdout[:400]}


def _process(resp, workspace, manifest, nscen):
    files = parse_files(resp)
    workspace.mkdir(parents=True, exist_ok=True)
    write_candidate(workspace, files)
    ok, reason, detail = gate(workspace, manifest, nscen)
    return list(files.keys()), ok, reason, detail


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default=str(HERE / "planning_packet"))
    ap.add_argument("--replay", default=None, help="저장된 build 응답으로 키 없이 게이트만")
    ap.add_argument("--cap", type=int, default=11)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    pdir = Path(args.packet)
    contract, concept, tests, manifest = load_packet(pdir)
    nscen = max(1, len(tests))
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(args.out) if args.out else (HERE / "build_runs" / run_id)

    if args.replay:
        resp = Path(args.replay).read_text(encoding="utf-8")
        emitted, ok, reason, detail = _process(resp, base / "replay" / "workspace", manifest, nscen)
        print(json.dumps({"emitted": emitted, "pass": ok, "reason": reason,
                          "smoke": (detail or {}).get("smoke_stdout")},
                         ensure_ascii=False, indent=2))
        return 0 if ok else 1

    # ---- ★키 병렬 select-best ----
    import os
    os.environ["GENERATOR_MODEL"] = MODEL_31
    os.environ["CRITIC_MODEL"] = MODEL_31
    from config import get_api_keys
    from llm import AllKeysExhausted, KeyPool, LLMClient
    pool = KeyPool(get_api_keys(), models=[MODEL_31])
    prompt = build_prompt(contract, concept, tests, manifest)
    print(f"[BUILD] 계약={pdir.name} cap={args.cap} keys={pool.size} → select-best, run={run_id}")

    cracked = None
    lock = threading.Lock()
    results = []

    def worker(attempt):
        with pool.checkout() as key:
            resp = LLMClient(api_key=key).generate("critic", prompt)
        return attempt, _process(resp, base / f"attempt{attempt:02d}" / "workspace", manifest, nscen)

    with ThreadPoolExecutor(max_workers=min(pool.size, args.cap)) as ex:
        futs = {ex.submit(worker, a): a for a in range(1, args.cap + 1)}
        for fut in as_completed(futs):
            try:
                a, (emitted, ok, reason, _d) = fut.result()
            except CancelledError:
                continue
            except AllKeysExhausted as e:
                print(f"[BUILD] 중단: {e}")
                break
            with lock:
                results.append((a, ok, reason))
            print(f"  [attempt {a:02d}] pass={ok} {reason}")
            if ok and cracked is None:
                cracked = a
                for f in futs:
                    if not f.done():
                        f.cancel()

    passed = sum(1 for _a, ok, _r in results if ok)
    print(f"\n[BUILD] {'CRACKED @ '+str(cracked) if cracked else 'NOT CRACKED'} "
          f"({passed}/{len(results)} 통과) → {base}")
    return 0 if cracked else 1


if __name__ == "__main__":
    raise SystemExit(main())
