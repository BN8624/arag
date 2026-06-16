# golem 드라이버 — gemma 워커가 JS 전투엔진을 짓는다(키 11개 병렬 select-best) → grade.py 채점 → cracked 보고
"""사용:
  python golem/driver.py [--cap 11] [--width N]    # 실제 실행(키 사용 — 사용자 명시 지시로만)
  python golem/driver.py --replay <file>            # 저장된 응답으로 LLM 없이 1회 점검(키 안 씀)

병렬 select-best(워커=키): CAP개 시도를 키 11개에 동시 실행, 각 워커가 KeyPool에서 키 하나를
빌려 그 키로 LLMClient를 만든다. 키마다 쿼터(RPM 15) 독립이라 진짜 병렬. 각 시도는 독립
(self-fix 없음 — T-000012 병렬 select-best와 동일 모드). 첫 통과 시 미시작 시도 취소.
장부 golem/golem_ledger.jsonl, 후보 runs/golem/<ts>/attemptNN/."""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # arag 루트(llm.py, config)
sys.path.insert(0, str(HERE))          # golem(worker_prompt, grade)

from worker_prompt import build_prompt   # noqa: E402
import grade as grader                    # noqa: E402

FILE_RE = re.compile(r"^===\s*FILE:\s*(.+?)\s*===\s*$", re.MULTILINE)
LEDGER = HERE / "golem_ledger.jsonl"
CAP_DEFAULT = 11                          # 키 11개 = 한 웨이브에 11병렬
MODEL_31 = "gemma-4-31b-it"               # golem = 31solo (arag 기본 generator는 26B라 명시 고정)
_log_lock = threading.Lock()


def parse_files(text):
    """'=== FILE: name ===' 마커로 멀티파일 추출. 코드펜스(```)는 벗긴다."""
    parts = FILE_RE.split(text)   # [intro, name1, body1, name2, body2, ...]
    files = {}
    for i in range(1, len(parts) - 1, 2):
        files[parts[i].strip()] = _strip_fence(parts[i + 1])
    return files


def _strip_fence(body):
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[0].lstrip().startswith("```"):
        lines.pop(0)
        if lines and lines[-1].strip().startswith("```"):
            lines.pop()
    return "\n".join(lines) + "\n"


def write_candidate(out_dir, files):
    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir.resolve()
    for name, body in files.items():
        p = (out_dir / name).resolve()
        if root != p and root not in p.parents:   # 경로 탈출 차단
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _one_attempt(resp, cdir, card=None):
    files = parse_files(resp)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "_raw_response.txt").write_text(resp, encoding="utf-8")
    if "main.js" not in files:
        return files, {"pass": False,
                       "first_divergence": "no main.js in response (unparseable?)"}
    write_candidate(cdir, files)
    return files, grader.grade(str(cdir), card["scenarios"])


def _log(entry):
    with _log_lock:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _attempt(attempt, base, key, model, run_id, card=None, base_files=None):
    """한 시도: 주입된 key로 LLMClient → JS 생성 → 채점. (attempt, ok, first_div, cost) 반환."""
    from llm import LLMClient
    cdir = base / f"attempt{attempt:02d}"
    cdir.mkdir(parents=True, exist_ok=True)
    client = LLMClient(api_key=key)
    client.record_path = cdir / "llm_calls.jsonl"
    t0 = time.time()
    try:
        resp = client.generate("generator", build_prompt(card, base_files=base_files))  # 독립 시도
    except Exception as err:   # noqa: BLE001 - 한 시도 폭주가 풀을 안 죽이게
        cost = client.cost_usd().get("total", 0.0)
        _log({"t": datetime.now().isoformat(timespec="seconds"), "run": run_id,
              "attempt": attempt, "ok": False, "error": str(err)[:200],
              "cost_usd": round(cost, 4)})
        return attempt, False, f"generate error: {str(err)[:120]}", cost
    files, res = _one_attempt(resp, cdir, card=card)
    dt = time.time() - t0
    cost = client.cost_usd().get("total", 0.0)
    _log({"t": datetime.now().isoformat(timespec="seconds"), "run": run_id,
          "attempt": attempt, "ok": res["pass"],
          "first_divergence": res.get("first_divergence"),
          "files": list(files.keys()), "sec": round(dt, 1),
          "cost_usd": round(cost, 4)})
    print(f"[attempt {attempt:02d}] pass={res['pass']} "
          f"{res.get('first_divergence') or 'ALL PASS'} ({dt:.0f}s)")
    return attempt, res["pass"], res.get("first_divergence"), cost


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=CAP_DEFAULT)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--replay", default=None,
                    help="LLM 대신 이 파일 응답으로 1회 파이프라인(키 안 씀, 점검용)")
    ap.add_argument("--card", default="tempo-combat",
                    help="은행(game_bank)의 카드 slug. 기본 tempo-combat")
    ap.add_argument("--base", default=None,
                    help="확장 모드: 이 카드의 solution을 베이스 구현으로 워커에 컨텍스트로 준다")
    args = ap.parse_args(argv)

    import game_bank
    card = game_bank.get_card(args.card)
    if card is None:
        print(f"[GOLEM] 카드 '{args.card}' 없음 — bank_init.py로 적재하거나 game_bank.py로 확인")
        return 2
    base_files = None
    if args.base:
        base_card = game_bank.get_card(args.base)
        if base_card is None or not base_card.get("solution"):
            print(f"[GOLEM] 베이스 카드 '{args.base}'의 solution 없음")
            return 2
        base_files = base_card["solution"]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(args.out) if args.out else (HERE.parent / "runs" / "golem" / run_id)

    if args.replay:
        resp = Path(args.replay).read_text(encoding="utf-8")
        files, res = _one_attempt(resp, base / "replay", card=card)
        print(json.dumps({"files": list(files.keys()), "pass": res["pass"],
                          "first_divergence": res.get("first_divergence")},
                         ensure_ascii=False, indent=2))
        return 0 if res["pass"] else 1

    # ---- 키 쓰는 병렬 경로 ----
    from config import force_utf8_stdout, get_api_keys, get_model
    from llm import AllKeysExhausted, KeyPool
    force_utf8_stdout()
    # golem = 31solo. 31B로 명시 고정(T-000012 cracked@2와 사과-대-사과).
    os.environ["GENERATOR_MODEL"] = MODEL_31
    os.environ["CRITIC_MODEL"] = MODEL_31

    keys = get_api_keys()
    model = get_model("generator")          # = 31B (위에서 고정)
    pool = KeyPool(keys, models=[model])
    width = args.width or min(len(keys), args.cap)

    base_note = f" base={args.base}" if args.base else ""
    print(f"[GOLEM] 병렬 select-best (cap {args.cap}, width {width}/{len(keys)}키) "
          f"model={model} card={args.card}{base_note}, run={run_id}")

    cracked_at = None
    started = 0
    passed = 0
    total_cost = 0.0
    started_lock = threading.Lock()

    def worker(attempt):
        nonlocal started
        with pool.checkout() as key:
            with started_lock:
                started += 1
            return _attempt(attempt, base, key, model, run_id, card=card, base_files=base_files)

    with ThreadPoolExecutor(max_workers=width) as ex:
        futs = {ex.submit(worker, a): a for a in range(1, args.cap + 1)}
        for fut in as_completed(futs):
            try:
                a, ok, _fd, cost = fut.result()
            except CancelledError:
                continue
            except AllKeysExhausted as err:
                print(f"[GOLEM] 중단: {err}")
                for f in futs:
                    if not f.done():
                        f.cancel()
                break
            total_cost += cost
            if ok:
                passed += 1
                if cracked_at is None:
                    cracked_at = a
                    for f in futs:        # 첫 통과 — 미시작 시도 취소
                        if not f.done():
                            f.cancel()

    _log({"t": datetime.now().isoformat(timespec="seconds"), "run": run_id,
          "summary": True, "cracked_at": cracked_at, "attempts": started,
          "passed": passed, "cap": args.cap, "width": width, "keys": len(keys),
          "cost_usd_total": round(total_cost, 4)})
    print()
    if cracked_at:
        print(f"[CRACKED @ {cracked_at}] {passed}/{started}통과, cost ~${total_cost:.3f}")
    else:
        print(f"[NOT CRACKED] {passed}/{started}통과(0), cost ~${total_cost:.3f}")
    print(f"[GOLEM] 장부 {LEDGER}, 후보 {base}")
    return 0 if cracked_at else 1


if __name__ == "__main__":
    raise SystemExit(main())
