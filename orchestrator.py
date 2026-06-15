"""오케스트레이터: 아이디어 -> 설계 -> 구현 -> 게이트 -> 비평 루프 -> 최종본.

사용법:
    python orchestrator.py "아이디어 한 줄" [--rounds 2] [--skip-exec]

가드레일 전부 포함: 층별 K회 자가수정, 진전 없음 감지, 콜/시간/파일 캡,
git 스냅샷 + rollback, 비평 바퀴 상한 + LGTM 조기 종료.

구조 (단계 로직은 phase_* 믹스인으로 분해 — 이 파일은 흐름·가드레일·스냅샷만):
    phase_common.py     공통 상수 + RunAborted
    phase_design.py     [31B] 설계 생성/검증/재사용
    phase_tests.py      [31B] 검수 시험지 출제/수리
    phase_implement.py  [26B] 파일별 구현 + 모의 자재
    phase_gates.py      정적/실행/pytest 게이트 + 자가수정 + 중재 + 채점표
    phase_critique.py   [31B] 품질심사 루프 + 롤백
    phase_improve.py    성공 런 개선 (회귀 방지선 보존)
    reporting.py        README/pyproject/REPORT/생산 장부
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, STOP_FILE, force_utf8_stdout
from docker_gate import _hidden_console_kwargs, docker_available
from gates import format_issues
from lessons import record_lesson
from llm import CallBudgetExceeded
from phase_common import (DEFAULT_MAX_CALLS, DEFAULT_MAX_MINUTES,  # noqa: F401
                          DEFAULT_ROUNDS, DESIGN_ATTEMPTS, K_MAX_FIX,
                          PARTIAL_PASS_RATE, TEST_FILE, RunAborted)
from phase_critique import CritiquePhase
from phase_design import DesignPhase
from phase_gates import GatesPhase
from phase_implement import ImplementPhase
from phase_improve import ImprovePhase
from phase_tests import TestsPhase
from reporting import ReportingMixin


class Orchestrator(DesignPhase, TestsPhase, ImplementPhase, GatesPhase,
                   CritiquePhase, ImprovePhase, ReportingMixin):
    def __init__(self, llm, run_dir: Path, critique_rounds: int = DEFAULT_ROUNDS,
                 skip_exec: bool = False, max_minutes: int = DEFAULT_MAX_MINUTES,
                 resume_from: Path | None = None,
                 improve_from: Path | None = None, feedback: str = "",
                 level: int | None = None, task_id: str | None = None,
                 notes_enabled: bool = True, whole: bool = False):
        self.llm = llm
        self.run_dir = Path(run_dir)
        self.workspace = self.run_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.critique_rounds = critique_rounds
        self.skip_exec = skip_exec
        self.deadline = time.monotonic() + max_minutes * 60
        self.started = time.monotonic()  # 경과시간(duration_sec) 측정 시작점
        self.design: dict | None = None
        self.idea = ""
        self.critique_history: list[dict] = []
        self.last_exec_log = "(execution gate skipped)"
        self.scoreboard: list[dict] = []
        self.deps_dir = self.run_dir / "deps"
        self._packages: list[str] = []
        self._last_issues: list[dict] = []
        self._last_snapshot: str | None = None
        self.fix_count: dict[str, int] = {"static": 0, "exec": 0}
        self._tests_regen_left = 1  # 테스트 자체 버그 시 31B 재생성 허용 횟수
        self._arbitration_left = 1  # 단언 실패 반복 시 31B 중재 허용 횟수
        self.partial_pass = False   # 마지막 게이트가 부분 합격이었나
        self.infra_error = False    # API 5xx 연속 등 인프라 장애로 죽었나
        self.critique_rounds_used = 0
        self._failure_keywords: list[str] = []
        self._injected_lesson_keywords: list[str] = []
        self.resume_from = Path(resume_from) if resume_from else None
        self.improve_from = Path(improve_from) if improve_from else None
        self.feedback = feedback
        self.level = level  # 출제 난이도 (배치 출제기가 전달, 전후 비교 분석용)
        self.task_id = task_id  # Design Bank 접점: 이 런이 어느 task_card에서 나왔나
        self.notes_enabled = notes_enabled  # cold=False: 오답/비평노트 주입 OFF
        self.mode = "warm" if notes_enabled else "cold"  # PLAN2 cold/warm 측정
        self.whole = whole  # True: 통짜(한 콜에 전체 파일) 구현 — 분해 대신
        self._prev_score: int | None = None   # improve: 직전 런의 통과 수
        self._old_commands: set[str] = set()  # improve: 기존 기준의 커맨드
        self._events = (self.run_dir / "events.jsonl").open("a", encoding="utf-8")

    # ------------------------------------------------------------ events

    def log(self, kind: str, **data) -> None:
        record = {"t": datetime.now().isoformat(timespec="seconds"),
                  "event": kind, **data}
        self._events.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._events.flush()

    def _say(self, msg: str) -> None:
        print(msg, flush=True)

    def _mlabel(self, role: str) -> str:
        """단계 로그에 실제 사용 모델명을 찍는다 (역할별 하드코딩 라벨 대체).
        구성(31단독·26단독·혼합)에 따라 모델이 바뀌므로 고정 '(26B)'는 거짓말이 된다."""
        from config import get_model
        return get_model(role)

    def _check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise RunAborted("time budget exhausted")

    # ------------------------------------------------------------ main

    def run(self, idea: str) -> bool:
        self.idea = idea
        try:
            if self.improve_from:
                if not self._phase_improve():
                    # 31B가 NOCHANGE - 개선 없이 원본 그대로가 답
                    self._write_report(idea, status="OK (NOCHANGE - nothing "
                                                    "worth improving)")
                    self._say("[OK] 31B says NOCHANGE - original kept")
                    return True
            elif self.resume_from:
                self._resume_design()
                self._resume_tests()
            else:
                self._phase_design(idea, self._load_lessons(idea))
                self._phase_tests()
            if not self.improve_from:
                self._phase_implement()
            self._write_fixtures()
            self._git_init()
            ok = self._pass_gates(context="initial build")
            if not ok:
                raise RunAborted("gates not passed after self-fix budget")
            self._snapshot("gates-pass-initial")
            self._run_scoreboard()
            self._phase_critique_loop()
            self._write_readme()
            self._write_pyproject()
            status = ("OK (partial - some acceptance tests still failing)"
                      if self.partial_pass else "OK")
            self._write_report(idea, status=status)
            self._say(f"[OK] run complete: {self.workspace}")
            return True
        except (RunAborted, CallBudgetExceeded) as err:
            if self._last_snapshot:
                # 게이트 통과본이 있다 - 비평 도중 예산이 끝나도 그걸 결과물로 낸다
                self._say(f"[SALVAGE] aborted mid-critique ({err}) - "
                          "delivering last passing build")
                self.log("salvaged", reason=str(err), snapshot=self._last_snapshot)
                self._rollback()
                try:
                    self._run_scoreboard()  # 복원본 기준 점수로 보고
                except Exception:  # noqa: BLE001
                    pass
                self._write_pyproject()
                self._write_report(idea, status=f"OK (salvaged last passing "
                                                f"build - aborted later: {err})")
                self._say(f"[OK] run complete (salvaged): {self.workspace}")
                return True
            self.log("aborted", reason=str(err))
            self._record_failure(idea, str(err))
            self._write_report(idea, status=f"ABORTED: {err}")
            self._say(f"[FAIL] run aborted: {err}")
            self._say(f"       details: {self.run_dir / 'events.jsonl'}")
            return False
        except Exception as err:
            import traceback
            tb = traceback.format_exc()
            # 콜 래퍼가 재시도를 다 쓰고 죽었다 = 인프라 장애.
            # 같은 장애에 재도전 콜을 더 태우지 않도록 표시한다 (브레이커).
            # API 소진뿐 아니라 일일쿼터·429·5xx·네트워크 절단도 인프라로 본다
            # (모델·설계 실패가 아니므로 오답노트도 안 남긴다 — _record_failure가 스킵).
            err_str = str(err).lower()
            if any(m in err_str for m in (
                    "api call failed after", "daily quota", "quota exhausted",
                    "resource_exhausted", "429", "500 internal", "internal error",
                    "connection reset", "connection aborted", "deadline")):
                self.infra_error = True
            self.log("error", reason=str(err), traceback=tb)
            self._record_failure(idea, f"{err}\n{tb}")
            self._write_report(idea, status=f"ERROR: {err}")
            self._say(f"[FAIL] unexpected error: {err}")
            self._say(f"       details: {self.run_dir / 'events.jsonl'}")
            return False
        finally:
            self._events.close()

    # ------------------------------------------------------------ lessons

    def _record_failure(self, idea: str, reason: str) -> None:
        # 인프라 장애(API 5xx/네트워크 소진)는 모델·설계 실패가 아니다 — 오답노트에
        # 남기면 "다른 LLM으로 폴백하라" 류 파이프라인 교훈이 설계 풀을 오염시킨다.
        if self.infra_error:
            self._say("[NOTE] infra failure - skipping lesson (not a design fault)")
            return
        try:
            entry = record_lesson(self.llm, idea, self._failure_summary(reason))
            if entry:
                self._failure_keywords = entry["keywords"]
                self.log("lesson-recorded", lesson=entry["lesson"],
                         keywords=entry["keywords"])
                self._say("[NOTE] failure lesson recorded to lessons.json")
        except Exception:  # noqa: BLE001
            pass

    def _failure_summary(self, reason: str) -> str:
        parts = [f"failure reason: {reason}"]
        if self._last_issues:
            parts.append("last gate issues:\n"
                         + format_issues(self._last_issues[:10]))
        if self.last_exec_log and "skipped" not in self.last_exec_log:
            tail = "\n".join(self.last_exec_log.strip().splitlines()[-15:])
            parts.append("execution log tail:\n" + tail)
        if self.design is not None:
            parts.append("designed files: "
                         + ", ".join(f["path"] for f in self.design["files"]))
            sig = self.design.get("success_signal", {})
            parts.append(f"success signal: {sig.get('command', '')!r} "
                         f"expecting {sig.get('expect_substring', '')!r}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------ files

    def _read_files(self) -> dict[str, str]:
        return {p.name: p.read_text(encoding="utf-8")
                for p in sorted(self.workspace.glob("*.py"))}

    # ------------------------------------------------------------ snapshots

    def _git(self, *args) -> subprocess.CompletedProcess:
        # 콘솔 숨김: pythonw로 돌 때 git 호출마다 검은 창이 깜빡이는 것 방지
        return subprocess.run(
            ["git", "-C", str(self.workspace),
             "-c", "user.name=arag", "-c", "user.email=arag@local", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, **_hidden_console_kwargs())

    def _git_init(self) -> None:
        if not (self.workspace / ".git").exists():
            self._git("init", "-q")

    def _snapshot(self, label: str) -> None:
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", label)
        result = self._git("rev-parse", "HEAD")
        self._last_snapshot = result.stdout.strip() or None
        self.log("snapshot", label=label, commit=self._last_snapshot)

    def _rollback(self) -> None:
        if self._last_snapshot:
            self._git("reset", "--hard", "-q", self._last_snapshot)
            self._git("clean", "-fdq")


def resume_retry_dir(failed_run_dir: Path) -> Path | None:
    """실패 런의 설계·시험지가 재사용 가능하면 그 디렉토리, 아니면 None.

    design.json이 있다 = 설계는 검증을 통과하고 그 뒤(구현·게이트)에서 죽었다.
    그 설계와 시험지를 다시 쓰면 재도전에서 설계 단계 콜(5~7콜)이 절약된다.
    """
    failed_run_dir = Path(failed_run_dir)
    if (failed_run_dir / "design.json").exists():
        return failed_run_dir
    return None


def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="idea -> multi-file Python prototype")
    parser.add_argument("idea", help="one-line idea for the prototype")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS,
                        help="critique-improve rounds (default 2)")
    parser.add_argument("--skip-exec", action="store_true",
                        help="skip the Docker execution gate")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--max-minutes", type=int, default=DEFAULT_MAX_MINUTES)
    parser.add_argument("--no-retry", action="store_true",
                        help="do not auto-retry once after a failed run")
    parser.add_argument("--resume", metavar="RUN_DIR",
                        help="reuse design.json + test_acceptance.py from a "
                             "previous run dir, skip to implementation phase")
    parser.add_argument("--improve", metavar="RUN_DIR",
                        help="improve a previous successful run: keep its "
                             "criteria as the regression bar, add stricter "
                             "ones, apply targeted changes")
    parser.add_argument("--feedback", default="",
                        help="user feedback for --improve (what to fix/add)")
    parser.add_argument("--level", type=int, default=None,
                        help="idea difficulty level from the batch generator "
                             "(recorded in the index for before/after analysis)")
    parser.add_argument("--task-id", default=None,
                        help="Design Bank task_card id this run came from "
                             "(recorded in the index for per-card join)")
    parser.add_argument("--mode", choices=["cold", "warm"], default="warm",
                        help="PLAN2 측정 모드: cold=오답/비평노트 주입 OFF "
                             "(순수 모델), warm=노트 주입 ON (기본, 기존 동작)")
    parser.add_argument("--whole", action="store_true",
                        help="통짜 구현: 파일별 분해 대신 한 콜에 전체 파일 생성 "
                             "(아키텍처 실험)")
    parser.add_argument("--replay", metavar="RUN_DIR",
                        help="replay recorded LLM responses from a previous "
                             "run dir (llm_calls.jsonl) - no API calls. "
                             "use with --no-retry")
    args = parser.parse_args()

    if args.improve and args.resume:
        print("[ERROR] --improve and --resume are mutually exclusive")
        return 1

    skip_exec = args.skip_exec
    if not skip_exec and not docker_available():
        print("[WARN] Docker is not available - execution gate will be skipped")
        skip_exec = True

    resume_from = Path(args.resume) if args.resume else None
    if resume_from and not resume_from.exists():
        print(f"[ERROR] --resume dir not found: {resume_from}")
        return 1
    improve_from = Path(args.improve) if args.improve else None
    if improve_from and not improve_from.exists():
        print(f"[ERROR] --improve dir not found: {improve_from}")
        return 1

    if args.replay:
        from llm import ReplayLLM
        record = Path(args.replay) / "llm_calls.jsonl"
        if not record.exists():
            print(f"[ERROR] no llm_calls.jsonl in {args.replay}")
            return 1
        llm = ReplayLLM(record)
        print(f"[REPLAY] reusing recorded responses from {args.replay}")
    else:
        from llm import LLMClient
        llm = LLMClient(max_calls=args.max_calls)

    run_dir = PROJECT_ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    llm.record_path = None if args.replay else run_dir / "llm_calls.jsonl"
    print(f"[START] run dir: {run_dir}")
    notes_enabled = args.mode == "warm"
    print(f"[MODE] {args.mode} (notes {'ON' if notes_enabled else 'OFF'})")
    orch = Orchestrator(llm, run_dir, critique_rounds=args.rounds,
                        skip_exec=skip_exec, max_minutes=args.max_minutes,
                        resume_from=resume_from, improve_from=improve_from,
                        feedback=args.feedback, level=args.level,
                        task_id=args.task_id, notes_enabled=notes_enabled,
                        whole=args.whole)
    ok = orch.run(args.idea)

    # 종료 예약: 플래그가 있으면 이번 회차로 끝 (재도전도 안 잡는다)
    if STOP_FILE.exists():
        print("[STOP] stop-after-run flag found - no retry, exiting")
        return 0 if ok else 1

    # 실패 시 1회 자동 재도전 (resume 모드에서는 건너뜀 — 특정 설계를 재사용 중)
    # 인프라 장애(5xx 연속)면 재도전 생략 — 같은 장애에 콜을 더 태우지 않는다
    if (not ok and not args.no_retry and not resume_from and not improve_from
            and not orch.infra_error
            and llm.call_count + 8 <= args.max_calls):
        # 설계·시험지까지 멀쩡했던 실패면 그걸 재사용 (설계 5~7콜 절약).
        # 설계 단계에서 죽었으면 처음부터 (오답노트가 새 설계에 주입됨)
        retry_resume = resume_retry_dir(run_dir)
        if retry_resume:
            print("[RETRY] first attempt failed - retrying with its "
                  "design + tests reused (resume)")
        else:
            print("[RETRY] first attempt failed - retrying once with "
                  "recorded lessons")
        run_dir = PROJECT_ROOT / "runs" / (
            datetime.now().strftime("%Y%m%d-%H%M%S") + "-retry")
        llm.record_path = run_dir / "llm_calls.jsonl"
        print(f"[START] run dir: {run_dir}")
        orch = Orchestrator(llm, run_dir, critique_rounds=args.rounds,
                            skip_exec=skip_exec, max_minutes=args.max_minutes,
                            resume_from=retry_resume, level=args.level,
                            task_id=args.task_id, notes_enabled=notes_enabled,
                            whole=args.whole)
        ok = orch.run(args.idea)

    print(f"[INFO] API calls used: {llm.call_count}")
    print(f"[INFO] report: {run_dir / 'REPORT.md'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
