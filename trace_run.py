# trace-diff 캠페인: 첫-발산 국소화 피드백이 T-000012 통과율을 올리나 A/B (결정27)
"""결정27 개입 측정 — '무정보 골든 피드백을 첫-발산 트레이스 힌트로 바꾸면 통과율↑?'.

깨끗한 A/B(한 변수=트레이스 피드백):
  - 둘 다 cold(노트 OFF), 둘 다 idea에 --trace 요구 포함(--trace 구현 세금 동일).
  - arm "trace_on":  golden_from=frozen/T-000012-trace (golden_traces 있음 → 자가수정에 힌트 주입).
  - arm "trace_off": golden_from=frozen/T-000012       (golden_traces 없음 → 기존 골든 diff만).
차이 = 피드백 품질뿐. (24% cold 베이스라인과도 대조 가능하나 그쪽은 --trace 세금이 없어 부차참고.)

게이트는 양 arm 동일(최종 골든 정확일치). 트레이스는 수정 신호로만 — 가짜 PASS 0.
병렬: 워커=키(KeyPool), early-stop 없음(통과율 측정). 장부: runs/trace_ledger.jsonl.
사용: python trace_run.py [N_per_arm=11] [width=11] [n_docker=5] [max_cycles=0(무한)]
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout, get_api_keys

CARD = "T-000012"
MODEL_31 = "gemma-4-31b-it"
MAX_MINUTES = 180
LAUNCH_STAGGER_SEC = 4.0
LEDGER = PROJECT_ROOT / "runs" / "trace_ledger.jsonl"
GOLDEN_TRACE = PROJECT_ROOT / "frozen" / "T-000012-trace"   # golden_traces 있음
GOLDEN_PLAIN = PROJECT_ROOT / "frozen" / "T-000012"          # golden_traces 없음

# idea에 덧붙이는 --trace 요구(양 arm 공통 = 세금 동일). game/combat._turn_line과 포맷 일치.
TRACE_SPEC = """

== 추가 요구: --trace 디버그 출력 (정확히 따르라) ==
main.py는 `--scenario N --trace` 형태도 지원하라. --trace가 있으면 그 시나리오를 한 판
돌리되, 최종 요약 대신 **턴별 트레이스를 한 줄씩** 다음 정확한 포맷으로 stdout에 출력한다:
  turn=<N> actor=<id> action=<action> | <id>=<hp> <id>=<hp> ...
- 한 행동(턴)마다 한 줄. turn은 1부터 증가(빙결로 스킵한 턴도 +1로 포함).
- action = 그 턴에 쓴 스킬명, 빙결 스킵이면 `frozen`, 화상으로 행동 전 사망이면 `burndead`,
  대상이 없으면 `noact`.
- `| ` 뒤에 등록 순서(heroes 먼저)대로 모든 엔티티의 현재 hp를 `<id>=<hp>` 공백 구분으로.
- hp 등 상태는 그 턴 처리가 끝난 시점 값.
--trace 없이 `--scenario N`만 주면 기존 골든 포맷(winner/turns/엔티티 hp)을 그대로 출력한다.
"""

_log_lock = threading.Lock()


def _log(entry: dict) -> None:
    with _log_lock:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_one(idea: str, attempt: int, arm: str, golden: object, key: str,
             cycle: int = 1) -> dict:
    """풀 파이프라인 1런(cold). arm별 golden_from으로 트레이스 피드백 ON/OFF."""
    from llm import LLMClient
    from orchestrator import Orchestrator

    run_dir = PROJECT_ROOT / "runs" / (
        datetime.now().strftime("%Y%m%d-%H%M%S")
        + f"-c{cycle:02d}{arm}{attempt:02d}")
    llm = LLMClient(api_key=key)
    llm.record_path = run_dir / "llm_calls.jsonl"
    orch = Orchestrator(llm, run_dir, max_minutes=MAX_MINUTES,
                        task_id=CARD, notes_enabled=False,  # cold: 노트 변수 제거
                        golden_from=golden)
    try:
        ok = bool(orch.run(idea))
    except Exception as err:
        print(f"[TRACE] {arm} 시도 {attempt} 예외: {err}")
        ok = False
    cost = 0.0
    try:
        cost = llm.cost_usd().get("total", 0.0)
    except Exception:  # noqa: BLE001
        pass
    passed = orch._score_passed()
    total = len(orch.scoreboard) if orch.scoreboard else None
    entry = {"t": datetime.now().isoformat(timespec="seconds"), "card": CARD,
             "cycle": cycle, "arm": arm, "attempt": attempt,
             "run": run_dir.name, "ok": ok, "passed": passed, "total": total,
             "cost_usd": round(cost, 4)}
    _log(entry)
    print(f"[TRACE] c{cycle:02d} {arm} {attempt:02d} -> "
          f"{'PASS' if ok else 'fail'} (score {passed}/{total}, ${cost:.4f})")
    return entry


def _run_arm(pool, idea: str, arm: str, golden: object, n: int, width: int,
             cycle: int = 1) -> list[dict]:
    from llm import AllKeysExhausted

    launch_lock = threading.Lock()
    next_launch = [0.0]

    def worker(attempt: int) -> dict:
        with launch_lock:
            slot = max(time.monotonic(), next_launch[0])
            next_launch[0] = slot + LAUNCH_STAGGER_SEC
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        with pool.checkout() as key:
            return _run_one(idea, attempt, arm, golden, key, cycle)

    results: list[dict] = []
    print(f"[TRACE] === c{cycle:02d} {arm} arm: {n}런 (width {width}) ===")
    with ThreadPoolExecutor(max_workers=width) as ex:
        futs = {ex.submit(worker, a): a for a in range(1, n + 1)}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except AllKeysExhausted as err:
                print(f"[TRACE] 중단(키 소진): {err}")
                for f in futs:
                    if not f.done():
                        f.cancel()
                break
    return results


def _summary(rows: list[dict], arm: str) -> tuple[int, int, float]:
    a = [r for r in rows if r["arm"] == arm]
    ok = sum(1 for r in a if r["ok"])
    cost = sum(r.get("cost_usd") or 0 for r in a)
    return ok, len(a), cost


def _print_cycle(rows: list[dict], cycle: int) -> None:
    on_ok, on_n, on_c = _summary(rows, "trace_on")
    off_ok, off_n, off_c = _summary(rows, "trace_off")
    on_r = on_ok / on_n if on_n else 0
    off_r = off_ok / off_n if off_n else 0
    print(f"\n[TRACE] ===== c{cycle:02d} 결과 =====")
    print(f"  trace_on : {on_ok}/{on_n} = {on_r:.0%}  (${on_c:.4f})")
    print(f"  trace_off: {off_ok}/{off_n} = {off_r:.0%}  (${off_c:.4f})")
    print(f"  델타(on-off): {(on_r - off_r):+.0%}  | 장부: {LEDGER.name}")


def main(argv=None) -> int:
    import sys
    force_utf8_stdout()
    args = list(argv or sys.argv[1:])
    n = int(args[0]) if len(args) > 0 else 11
    width = int(args[1]) if len(args) > 1 else 11
    n_docker = int(args[2]) if len(args) > 2 else 5
    max_cycles = int(args[3]) if len(args) > 3 else 0

    os.environ["GENERATOR_MODEL"] = MODEL_31
    os.environ["CRITIC_MODEL"] = MODEL_31

    from llm import KeyPool
    import docker_gate
    keys = get_api_keys()
    pool = KeyPool(keys, models=[MODEL_31])
    docker_gate.set_docker_concurrency(n_docker)

    from bank_db import BankDB
    with BankDB() as db:
        idea = db.get_task(CARD)["goal"] + TRACE_SPEC

    print(f"[TRACE] trace-diff A/B — 카드 {CARD}, arm당 {n}런, "
          f"width {width}/{len(keys)}키, 도커{n_docker}동시, 사이클 {max_cycles or '무한'}")
    arms = [("trace_on", GOLDEN_TRACE), ("trace_off", GOLDEN_PLAIN)]
    cycle = 0
    while max_cycles == 0 or cycle < max_cycles:
        cycle += 1
        rows: list[dict] = []
        for arm, golden in arms:
            rows += _run_arm(pool, idea, arm, golden, n, width, cycle)
        if not rows:
            print(f"[TRACE] c{cycle:02d}: 결과 0 (키 소진 추정) — 정지")
            break
        _print_cycle(rows, cycle)
    print(f"[TRACE] 종료: {cycle}사이클 (장부 {LEDGER.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
