"""3층: 배치 모드 — 출제·생산·개선을 한 루프에서 연속 운영.

회차마다 우선순위 순으로 하나를 실행한다:
  1. 부분 실패 OK 런이 있으면 → improve (피드백 = 떨어진 수용기준, 콜 0)
  2. 총평 안 받은 만점 런이 있으면 → 31B 사용자 시점 총평 1콜
       → 지적 있으면 improve, NOCHANGE면 같은 회차에서 신규 생산으로 진행
  3. 신규 생산: 아이디어 출제(콜 1) → orchestrator 완주

improve 폭주 방지:
  - 런당 자동 improve 1회 (improved_from 기록으로 판별)
  - improve 런 자체는 다시 improve/총평 대상이 안 됨 (개선의 개선 금지)
  - 총평은 런당 1회 (auto_review.json 마커, NOCHANGE여도 기록)

회차 사이마다 STOP_AFTER_RUN 플래그 확인 (대시보드 종료예약 버튼이 만듦).
자동 중단: STOP 플래그 / 일일 쿼터(RPD) 소진 / 연속 실패 3회 /
인프라 장애(API 5xx·네트워크) 연속 2회 (첫 번은 15분 대기 후 재개).

사용법:
    python batch.py --runs 3
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, STOP_FILE, force_utf8_stdout
from idea_factory import generate_idea
from run_index import load_index

RUNS_DIR = PROJECT_ROOT / "runs"
DEFAULT_RUNS = 3
MAX_RUNS = 20
MAX_CONSECUTIVE_FAILURES = 3  # 회차당 내부 재도전 1회 포함 = 빌드 6연속 실패 시 정지
# 인프라 장애(API 5xx 연쇄·네트워크 절단)는 모델 실력과 무관 — 회차를 태우지 말고
# 한 번 길게 기다렸다가 재개, 그래도 죽으면 정지 (새벽 07시 500 연쇄로 3회차 소진 실관측)
INFRA_WAIT_SEC = 900
MAX_INFRA_STRIKES = 2
_INFRA_MARKERS = ("api call failed", "winerror", "connection reset",
                  "connection aborted")


def _looks_infra(text: str) -> bool:
    """실패 사유가 인프라 장애(API/네트워크)로 보이는가."""
    t = str(text).lower()
    return any(k in t for k in _INFRA_MARKERS)


def _last_status_since(runs_dir: Path, since_iso: str) -> str:
    """이번 회차가 기록한 마지막 런의 status (인프라 장애 분류용)."""
    entries = [e for e in load_index(runs_dir)
               if str(e.get("t", "")) >= since_iso]
    return str(entries[-1].get("status", "")) if entries else ""


def _default_runner(args: list[str]) -> int:
    """orchestrator를 서브프로세스로 1회 완주시키고 exit code를 반환."""
    proc = subprocess.run([sys.executable, "orchestrator.py", *args],
                          cwd=PROJECT_ROOT)
    return proc.returncode


def _improve_done_or_running(entries: list[dict]) -> set[str]:
    """이미 improve가 시도된(성패 무관) 원본 런 이름들."""
    return {e["improved_from"] for e in entries if e.get("improved_from")}


def find_improve_target(runs_dir: Path) -> tuple[str, str, str] | None:
    """부분 실패 OK 런 → (런 이름, 원래 아이디어, 공짜 피드백). 없으면 None.

    피드백은 모델이 쓰는 게 아니라 채점표가 이미 적어둔 것 — 떨어진 기준 텍스트.
    """
    entries = load_index(runs_dir)
    improved = _improve_done_or_running(entries)
    for e in reversed(entries):  # 최신 우선
        if not e.get("ok") or e.get("improved_from") or e["run"] in improved:
            continue
        failed = [str(c) for c in e.get("failed_criteria") or [] if str(c).strip()]
        if not failed or not (Path(runs_dir) / e["run"]).exists():
            continue
        feedback = ("자동 개선: 아래 수용기준이 아직 실패한다. 기존에 통과한 "
                    "기능을 깨지 말고 이 기준들을 통과시켜라.\n- "
                    + "\n- ".join(failed))
        return e["run"], str(e.get("idea", "")), feedback
    return None


def find_review_target(runs_dir: Path) -> tuple[str, str] | None:
    """총평 안 받은 만점 OK 런 → (런 이름, 원래 아이디어). 없으면 None."""
    from reviewer import review_marker
    entries = load_index(runs_dir)
    improved = _improve_done_or_running(entries)
    for e in reversed(entries):
        if not e.get("ok") or e.get("improved_from") or e["run"] in improved:
            continue
        score = e.get("score") or {}
        if not score.get("total") or score.get("passed") != score.get("total"):
            continue
        run_dir = Path(runs_dir) / e["run"]
        if run_dir.exists() and not review_marker(run_dir).exists():
            return e["run"], str(e.get("idea", ""))
    return None


def summary_lines(entries: list[dict], since_iso: str) -> list[str]:
    """배치 시작 이후의 런들을 아침에 한눈에 읽을 표로 (콜 0)."""
    rows = [e for e in entries if str(e.get("t", "")) >= since_iso]
    if not rows:
        return ["(no runs recorded this batch)"]
    lines = []
    total_cost = 0.0
    n_ok = 0
    for e in rows:
        score = e.get("score") or {}
        sc = (f"{score['passed']}/{score['total']}"
              if score.get("total") else "-")
        cost = e.get("cost_usd") or 0
        total_cost += cost
        if e.get("ok"):
            n_ok += 1
        tag = "improve" if e.get("improved_from") else "new"
        mark = "OK " if e.get("ok") else "FAIL"
        lines.append(f"  {mark} {e.get('run', '?'):<24} {tag:<7} score {sc:<5} "
                     f"${cost:.4f}  {str(e.get('idea', ''))[:40]}")
    lines.append(f"  total: {n_ok}/{len(rows)} ok, ${total_cost:.4f}")
    return lines


def run_batch(n_runs: int = DEFAULT_RUNS, runner=_default_runner,
              idea_gen=None, reviewer_fn=None,
              stop_file: Path = STOP_FILE,
              runs_dir: Path | None = None,
              sleep_fn=time.sleep) -> dict:
    """배치 루프. 결과 요약 dict 반환 (테스트 가능하도록 의존성 주입)."""
    runs_dir = Path(runs_dir) if runs_dir else RUNS_DIR
    started_at = datetime.now().isoformat(timespec="seconds")
    n_runs = max(1, min(int(n_runs), MAX_RUNS))
    done = ok = improves = 0
    consecutive_failures = 0
    infra_strikes = 0
    stopped_by = None

    def _handle_failure(reason: str) -> str | None:
        """실패 1건 처리. 배치를 멈춰야 하면 중단 사유를 반환.

        인프라 장애는 모델 실패와 분리: 첫 번은 길게 기다렸다 재개,
        연속 두 번이면 정지 (회차·콜을 장애에 태우지 않는다).
        """
        nonlocal consecutive_failures, infra_strikes
        if _looks_infra(reason):
            infra_strikes += 1
            if infra_strikes >= MAX_INFRA_STRIKES:
                print("[BATCH] infra errors persist - stopping")
                return "infra-outage"
            print(f"[BATCH] infra error (API/network) - waiting "
                  f"{INFRA_WAIT_SEC // 60} min before the next round")
            sleep_fn(INFRA_WAIT_SEC)
            return None
        consecutive_failures += 1
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            print("[BATCH] consecutive failures - stopping")
            return "consecutive-failures"
        return None

    def _quota_guard(fn):
        """일일 쿼터 소진을 구분해서 배치 전체를 멈춘다."""
        from llm import DailyQuotaExceeded
        try:
            return fn(), None
        except DailyQuotaExceeded as err:
            return None, str(err)

    for round_no in range(1, n_runs + 1):
        if stop_file.exists():
            print("[BATCH] stop-after-run flag found - stopping")
            stopped_by = "stop-flag"
            break

        # ---- 1겹: 부분 실패 OK 런 → 공짜 피드백 improve
        target = find_improve_target(runs_dir)
        if target:
            run, idea, feedback = target
            print(f"[BATCH] round {round_no}/{n_runs}: improving {run} "
                  "(feedback = failed criteria, 0 calls)")
            round_start = datetime.now().isoformat(timespec="seconds")
            code = runner(["--improve", str(Path(runs_dir) / run),
                           "--feedback", feedback, idea])
            done += 1
            improves += 1
            if code == 0:
                ok += 1
                consecutive_failures = infra_strikes = 0
            else:
                stopped_by = _handle_failure(
                    _last_status_since(runs_dir, round_start))
                if stopped_by:
                    break
            continue

        # ---- 2겹: 만점 런 → 31B 사용자 시점 총평 1콜
        review = find_review_target(runs_dir)
        if review:
            run, idea = review
            print(f"[BATCH] round {round_no}/{n_runs}: user-view review of {run}")
            if reviewer_fn is not None:
                feedback = reviewer_fn(Path(runs_dir) / run, idea)
            else:
                from llm import LLMClient
                from reviewer import user_review
                feedback, quota_err = _quota_guard(
                    lambda: user_review(LLMClient(max_calls=2),
                                        Path(runs_dir) / run, idea))
                if quota_err:
                    print(f"[BATCH] daily quota exhausted - stopping: {quota_err}")
                    stopped_by = "daily-quota"
                    break
            if feedback:
                print(f"[BATCH] reviewer suggests improvements -> improve {run}")
                round_start = datetime.now().isoformat(timespec="seconds")
                code = runner(["--improve", str(Path(runs_dir) / run),
                               "--feedback", feedback, idea])
                done += 1
                improves += 1
                if code == 0:
                    ok += 1
                    consecutive_failures = infra_strikes = 0
                else:
                    stopped_by = _handle_failure(
                        _last_status_since(runs_dir, round_start))
                    if stopped_by:
                        break
                continue
            print("[BATCH] reviewer says NOCHANGE - moving on to a new idea")
            # 같은 회차에서 신규 생산으로 진행 (마커가 남아 재방문 없음)

        # ---- 3겹: 신규 생산
        print(f"[BATCH] round {round_no}/{n_runs}: generating idea")
        try:
            if idea_gen is not None:
                out = idea_gen()
            else:
                from llm import LLMClient
                out, quota_err = _quota_guard(
                    lambda: generate_idea(LLMClient(max_calls=4)))
                if quota_err:
                    print(f"[BATCH] daily quota exhausted - stopping: {quota_err}")
                    stopped_by = "daily-quota"
                    break
        except Exception as err:  # noqa: BLE001 - 출제 실패는 회차 실패로 집계
            print(f"[BATCH] idea generation failed: {err}")
            stopped_by = _handle_failure(str(err))
            if stopped_by:
                break
            continue

        print(f"[BATCH] idea (repo {out.get('repo', '?')}, "
              f"level {out.get('level', '?')}): {out['idea']}")
        cmd = [out["idea"]]
        if out.get("level") is not None:
            # 출제 레벨을 index에 남겨 난이도 변화가 전후 비교를 오염시키는지 추적
            cmd += ["--level", str(out["level"])]
        round_start = datetime.now().isoformat(timespec="seconds")
        code = runner(cmd)
        done += 1
        if code == 0:
            ok += 1
            consecutive_failures = infra_strikes = 0
        else:
            stopped_by = _handle_failure(
                _last_status_since(runs_dir, round_start))
            if stopped_by:
                break

    print(f"[BATCH] finished: {ok}/{done} runs ok, {improves} improve round(s)"
          + (f" (stopped by {stopped_by})" if stopped_by else ""))
    print("[BATCH] summary:")
    for line in summary_lines(load_index(runs_dir), started_at):
        print(line)
    return {"requested": n_runs, "done": done, "ok": ok,
            "improves": improves, "stopped_by": stopped_by}


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
