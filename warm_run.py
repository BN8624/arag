# warm 캠페인: 풀 파이프라인(설계에 오답노트 주입) + 골든 오라클 고정, cold/warm 통과율 델타
"""결정25 운영(31solo)에서 노트 효과를 잰다 — '틱 스케줄러 오답노트가 설계를 개선하나'.

핵심 설정(왜 풀 파이프라인인가): 오답노트는 *설계 단계*에 주입된다. select-best의 frozen
(--resume)은 설계를 고정·스킵하므로 오답노트가 안 들어간다 → warm 무의미. 그래서 여기선
**설계 단계를 돌리되(오답노트 반영)** 오라클만 골든으로 고정(golden_from)해 같은 잣대로 잰다.
골든 오라클은 행동검증(main.py --scenario 실행→stdout 대조)이라 설계가 달라도 재사용된다.

병렬: 워커=키, KeyPool에서 키 하나를 빌려 그 키로만 콜(키별 4초 페이서). early-stop 없음 —
arm당 N개를 전부 독립 실행해 *통과율*을 잰다(select-best의 cracked_at이 아니라 pass rate).

주의(상한선): 같은 카드 warm은 노트가 이 카드 실패에서 나와 효과를 과대평가한다(PLAN §1.5).
목적은 파이프라인 검증 + 방향성. 정식 일반화는 cross-card warm에서.

장부: runs/warm_ledger.jsonl  →  끝에 cold vs warm 통과율·비용 델타 출력.
사용: python warm_run.py [N_per_arm=11] [width=11] [n_docker=5]
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout, get_api_keys

CARD = "T-000012"                       # 통합 frontier 카드
GOLDEN_DIR = PROJECT_ROOT / "frozen" / "T-000012"  # 골든 오라클(design.json + test_acceptance.py)
MODEL_31 = "gemma-4-31b-it"             # 31solo
MAX_MINUTES = 60                        # 풀 파이프라인(설계+구현+게이트+비평)이라 넉넉히
LEDGER = PROJECT_ROOT / "runs" / "warm_ledger.jsonl"

_log_lock = threading.Lock()


def _log(entry: dict) -> None:
    with _log_lock:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_one(idea: str, attempt: int, mode: str, key: str,
             cycle: int = 1) -> dict:
    """풀 파이프라인 1런(설계부터). 골든 오라클 고정, mode로 오답노트 ON/OFF.
    notes_enabled=(warm). 주입된 키로만 콜. 결과 dict 반환(장부용)."""
    from llm import LLMClient
    from orchestrator import Orchestrator

    run_dir = PROJECT_ROOT / "runs" / (
        datetime.now().strftime("%Y%m%d-%H%M%S")
        + f"-c{cycle:02d}{mode}{attempt:02d}")
    llm = LLMClient(api_key=key)
    llm.record_path = run_dir / "llm_calls.jsonl"
    orch = Orchestrator(llm, run_dir, max_minutes=MAX_MINUTES,
                        task_id=CARD, notes_enabled=(mode == "warm"),
                        golden_from=GOLDEN_DIR)  # 설계는 돌고, 오라클만 골든
    try:
        ok = bool(orch.run(idea))
    except Exception as err:  # 한 런의 폭주가 풀 전체를 죽이지 않게
        print(f"[WARM] {mode} 시도 {attempt} 예외: {err}")
        ok = False
    cost = 0.0
    try:
        cost = llm.cost_usd().get("total", 0.0)
    except Exception:  # noqa: BLE001
        pass
    passed = orch._score_passed()
    total = len(orch.scoreboard) if orch.scoreboard else None
    entry = {"t": datetime.now().isoformat(timespec="seconds"), "card": CARD,
             "cycle": cycle, "mode": mode, "attempt": attempt,
             "run": run_dir.name, "ok": ok, "passed": passed, "total": total,
             "cost_usd": round(cost, 4)}
    _log(entry)
    print(f"[WARM] c{cycle:02d} {mode} {attempt:02d} -> "
          f"{'PASS' if ok else 'fail'} (score {passed}/{total}, ${cost:.4f})")
    return entry


def _run_arm(pool, idea: str, mode: str, n: int, width: int,
             cycle: int = 1) -> list[dict]:
    """한 arm(cold 또는 warm)을 N개 독립 병렬 실행(early-stop 없음)."""
    from llm import AllKeysExhausted

    started_lock = threading.Lock()
    started = [0]

    def worker(attempt: int) -> dict:
        with pool.checkout() as key:
            with started_lock:
                started[0] += 1
            return _run_one(idea, attempt, mode, key, cycle)

    results: list[dict] = []
    print(f"[WARM] === c{cycle:02d} {mode} arm: {n}런 (width {width}) ===")
    with ThreadPoolExecutor(max_workers=width) as ex:
        futs = {ex.submit(worker, a): a for a in range(1, n + 1)}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except AllKeysExhausted as err:
                print(f"[WARM] 중단(키 소진): {err}")
                for f in futs:
                    if not f.done():
                        f.cancel()
                break
    return results


def _summary(rows: list[dict], mode: str) -> tuple[int, int, float]:
    arm = [r for r in rows if r["mode"] == mode]
    ok = sum(1 for r in arm if r["ok"])
    cost = sum(r.get("cost_usd") or 0 for r in arm)
    return ok, len(arm), cost


def _print_cycle(rows: list[dict], cycle: int) -> None:
    c_ok, c_n, c_cost = _summary(rows, "cold")
    w_ok, w_n, w_cost = _summary(rows, "warm")
    c_rate = c_ok / c_n if c_n else 0
    w_rate = w_ok / w_n if w_n else 0
    print(f"\n[WARM] ===== c{cycle:02d} 결과 =====")
    print(f"  cold: {c_ok}/{c_n} = {c_rate:.0%}  (${c_cost:.4f})")
    print(f"  warm: {w_ok}/{w_n} = {w_rate:.0%}  (${w_cost:.4f})")
    print(f"  델타(warm-cold): {(w_rate - c_rate):+.0%}  | 장부: {LEDGER.name}")


def main(argv=None) -> int:
    import sys
    force_utf8_stdout()
    args = list(argv or sys.argv[1:])
    n = int(args[0]) if len(args) > 0 else 11
    width = int(args[1]) if len(args) > 1 else 11
    n_docker = int(args[2]) if len(args) > 2 else 5
    max_cycles = int(args[3]) if len(args) > 3 else 0   # 0 = 중지 전까지 무한

    # 31solo 선점(load_env가 기존 env를 안 덮으므로 여기서)
    os.environ["GENERATOR_MODEL"] = MODEL_31
    os.environ["CRITIC_MODEL"] = MODEL_31

    from llm import KeyPool
    import docker_gate
    keys = get_api_keys()
    pool = KeyPool(keys, models=[MODEL_31])
    docker_gate.set_docker_concurrency(n_docker)

    from bank_db import BankDB
    with BankDB() as db:
        idea = db.get_task(CARD)["goal"]

    print(f"[WARM] 31solo 풀파이프라인+골든오라클 — 카드 {CARD}, arm당 {n}런, "
          f"width {width}/{len(keys)}키, 도커{n_docker}동시, "
          f"사이클 {max_cycles or '무한'}")
    cycle = 0
    while max_cycles == 0 or cycle < max_cycles:
        cycle += 1
        rows: list[dict] = []
        for mode in ("cold", "warm"):  # cold 먼저(노트 OFF), 그다음 warm(노트 ON)
            rows += _run_arm(pool, idea, mode, n, width, cycle)
        if not rows:  # 한 런도 못 돎 = 키 전부 소진 → 정지
            print(f"[WARM] c{cycle:02d}: 결과 0 (키 소진 추정) — 정지")
            break
        _print_cycle(rows, cycle)
    print(f"[WARM] 종료: {cycle}사이클 (장부 {LEDGER.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
