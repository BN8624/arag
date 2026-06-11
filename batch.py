"""3층: 배치 모드 — 출제기가 뽑은 아이디어로 연속 생산.

회차마다: 아이디어 출제(콜 1) → orchestrator 서브프로세스 1회 완주.
회차 사이마다 STOP_AFTER_RUN 플래그 확인 (대시보드 종료예약 버튼이 만듦).

자동 중단 조건:
- STOP_AFTER_RUN 플래그 발견
- 일일 쿼터(RPD) 소진
- 연속 실패 2회 (쿼터·환경 문제로 헛돌며 콜을 태우는 것 방지)

사용법:
    python batch.py --runs 3
"""

import argparse
import subprocess
import sys
from pathlib import Path

from config import PROJECT_ROOT, STOP_FILE, force_utf8_stdout
from idea_factory import generate_idea

DEFAULT_RUNS = 3
MAX_RUNS = 20
MAX_CONSECUTIVE_FAILURES = 2


def _default_runner(idea: str) -> int:
    """orchestrator를 서브프로세스로 1회 완주시키고 exit code를 반환."""
    proc = subprocess.run([sys.executable, "orchestrator.py", idea],
                          cwd=PROJECT_ROOT)
    return proc.returncode


def run_batch(n_runs: int = DEFAULT_RUNS, runner=_default_runner,
              idea_gen=None, stop_file: Path = STOP_FILE) -> dict:
    """배치 루프. 결과 요약 dict 반환 (테스트 가능하도록 의존성 주입)."""
    n_runs = max(1, min(int(n_runs), MAX_RUNS))
    done = ok = 0
    consecutive_failures = 0
    stopped_by = None

    for round_no in range(1, n_runs + 1):
        if stop_file.exists():
            print("[BATCH] stop-after-run flag found - stopping")
            stopped_by = "stop-flag"
            break

        print(f"[BATCH] round {round_no}/{n_runs}: generating idea")
        try:
            if idea_gen is not None:
                out = idea_gen()
            else:
                from llm import LLMClient, DailyQuotaExceeded
                try:
                    out = generate_idea(LLMClient(max_calls=4))
                except DailyQuotaExceeded as err:
                    print(f"[BATCH] daily quota exhausted - stopping: {err}")
                    stopped_by = "daily-quota"
                    break
        except Exception as err:  # noqa: BLE001 - 출제 실패는 회차 실패로 집계
            print(f"[BATCH] idea generation failed: {err}")
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("[BATCH] consecutive failures - stopping")
                stopped_by = "consecutive-failures"
                break
            continue

        print(f"[BATCH] idea (repo {out.get('repo', '?')}, "
              f"level {out.get('level', '?')}): {out['idea']}")
        code = runner(out["idea"])
        done += 1
        if code == 0:
            ok += 1
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("[BATCH] consecutive failures - stopping")
                stopped_by = "consecutive-failures"
                break

    print(f"[BATCH] finished: {ok}/{done} runs ok"
          + (f" (stopped by {stopped_by})" if stopped_by else ""))
    return {"requested": n_runs, "done": done, "ok": ok,
            "stopped_by": stopped_by}


def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="batch production (3rd layer)")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help=f"number of rounds (default {DEFAULT_RUNS}, "
                             f"max {MAX_RUNS})")
    args = parser.parse_args()
    result = run_batch(args.runs)
    return 0 if result["done"] and result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
