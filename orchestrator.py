"""오케스트레이터: 아이디어 -> 설계 -> 구현 -> 게이트 -> 비평 루프 -> 최종본.

사용법:
    python orchestrator.py "아이디어 한 줄" [--rounds 2] [--skip-exec]

가드레일 전부 포함: 층별 K회 자가수정, 진전 없음 감지, 콜/시간/파일 캡,
git 스냅샷 + rollback, 비평 바퀴 상한 + LGTM 조기 종료.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, force_utf8_stdout
from design_validator import implementation_order, validate_design
from docker_gate import docker_available, run_exec_gate
from gates import format_issues, run_static_gate
from llm import CallBudgetExceeded
from prompts import (critique_prompt, design_prompt, extract_code, fix_prompt,
                     implement_prompt, revise_prompt)
from schema import extract_json, parse_design

K_MAX_FIX = 3          # 층마다 자가수정 상한
DESIGN_ATTEMPTS = 3    # 설계 1회 + 재설계 2회
DEFAULT_ROUNDS = 2     # 비평-개선 바퀴
DEFAULT_MAX_CALLS = 60
DEFAULT_MAX_MINUTES = 40


class RunAborted(Exception):
    """가드레일 발동으로 회차 종료."""


class Orchestrator:
    def __init__(self, llm, run_dir: Path, critique_rounds: int = DEFAULT_ROUNDS,
                 skip_exec: bool = False, max_minutes: int = DEFAULT_MAX_MINUTES):
        self.llm = llm
        self.run_dir = Path(run_dir)
        self.workspace = self.run_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.critique_rounds = critique_rounds
        self.skip_exec = skip_exec
        self.deadline = time.monotonic() + max_minutes * 60
        self.design: dict | None = None
        self.critique_history: list[dict] = []
        self.last_exec_log = "(execution gate skipped)"
        self._last_snapshot: str | None = None
        self._events = (self.run_dir / "events.jsonl").open("a", encoding="utf-8")

    # ------------------------------------------------------------ events

    def log(self, kind: str, **data) -> None:
        record = {"t": datetime.now().isoformat(timespec="seconds"),
                  "event": kind, **data}
        self._events.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._events.flush()

    def _say(self, msg: str) -> None:
        print(msg, flush=True)

    def _check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise RunAborted("time budget exhausted")

    # ------------------------------------------------------------ main

    def run(self, idea: str) -> bool:
        try:
            self._phase_design(idea)
            self._phase_implement()
            self._git_init()
            ok = self._pass_gates(context="initial build")
            if not ok:
                raise RunAborted("gates not passed after self-fix budget")
            self._snapshot("gates-pass-initial")
            self._phase_critique_loop()
            self._write_report(idea, status="OK")
            self._say(f"[OK] run complete: {self.workspace}")
            return True
        except (RunAborted, CallBudgetExceeded) as err:
            self.log("aborted", reason=str(err))
            self._write_report(idea, status=f"ABORTED: {err}")
            self._say(f"[FAIL] run aborted: {err}")
            self._say(f"       details: {self.run_dir / 'events.jsonl'}")
            return False
        finally:
            self._events.close()

    # ------------------------------------------------------------ phases

    def _phase_design(self, idea: str) -> None:
        self._say("[PHASE] design (31B)")
        errors: list[str] = []
        for attempt in range(DESIGN_ATTEMPTS):
            self._check_time()
            text = self.llm.generate("critic", design_prompt(idea, errors or None))
            design, errs = parse_design(text)
            if design is not None:
                errs = validate_design(design)
                if not errs:
                    self.design = design
                    (self.run_dir / "design.json").write_text(
                        json.dumps(design, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    self.log("design-accepted", attempt=attempt + 1,
                             files=[f["path"] for f in design["files"]])
                    self._say(f"[OK] design accepted "
                              f"({len(design['files'])} files, attempt {attempt + 1})")
                    return
            errors = errs
            self.log("design-rejected", attempt=attempt + 1, errors=errs)
            self._say(f"[RETRY] design rejected (attempt {attempt + 1}): "
                      f"{len(errs)} errors")
        raise RunAborted(f"design failed after {DESIGN_ATTEMPTS} attempts: {errors}")

    def _phase_implement(self) -> None:
        self._say("[PHASE] implement (26B)")
        order = implementation_order(self.design)
        written: dict[str, str] = {}
        for path in order:
            self._check_time()
            text = self.llm.generate("generator",
                                     implement_prompt(self.design, path, written))
            code = extract_code(text)
            if code is None:
                # 한 번만 재요청
                text = self.llm.generate("generator",
                                         implement_prompt(self.design, path, written))
                code = extract_code(text)
                if code is None:
                    raise RunAborted(f"implementer returned no code block for {path}")
            (self.workspace / path).write_text(code, encoding="utf-8")
            written[path] = code
            self.log("file-written", file=path, chars=len(code))
            self._say(f"  [OK] wrote {path}")

    def _pass_gates(self, context: str) -> bool:
        """정적 게이트 -> 실행 게이트, 층별 K회 자가수정. 둘 다 통과하면 True."""
        static_left = K_MAX_FIX
        exec_left = K_MAX_FIX
        prev_static: frozenset | None = None
        prev_exec: frozenset | None = None

        while True:
            self._check_time()
            issues = run_static_gate(self.workspace, self.design)
            if issues:
                sig = frozenset((i["file"], i["kind"], i["message"]) for i in issues)
                if sig == prev_static:
                    self.log("no-progress", layer="static", context=context)
                    self._say("[STUCK] static gate: same errors twice in a row")
                    return False
                prev_static = sig
                if static_left == 0:
                    self.log("budget-exhausted", layer="static", context=context)
                    self._say("[STUCK] static gate: fix budget exhausted")
                    return False
                static_left -= 1
                self._say(f"  [GATE] static: {len(issues)} issues "
                          f"-> self-fix ({static_left} left)")
                self.log("static-issues", context=context, issues=issues)
                self._fix_files(self._group_issues(issues))
                continue

            if self.skip_exec:
                self._say("  [GATE] static passed (exec gate skipped)")
                return True

            exec_issues, log_text = run_exec_gate(self.workspace,
                                                  self.design["success_signal"])
            self.last_exec_log = log_text
            if not exec_issues:
                self._say("  [GATE] static + exec passed")
                return True
            sig = frozenset(i["message"] for i in exec_issues)
            if sig == prev_exec:
                self.log("no-progress", layer="exec", context=context)
                self._say("[STUCK] exec gate: same errors twice in a row")
                return False
            prev_exec = sig
            if exec_left == 0:
                self.log("budget-exhausted", layer="exec", context=context)
                self._say("[STUCK] exec gate: fix budget exhausted")
                return False
            exec_left -= 1
            target = self._blame_file(log_text)
            self._say(f"  [GATE] exec failed -> self-fix {target} ({exec_left} left)")
            self.log("exec-issues", context=context, target=target,
                     issues=[i["message"] for i in exec_issues])
            self._fix_files({target: exec_issues})

    def _phase_critique_loop(self) -> None:
        for round_no in range(1, self.critique_rounds + 1):
            self._check_time()
            self._say(f"[PHASE] critique round {round_no}/{self.critique_rounds} (31B)")
            verdict = self._get_critique()
            if verdict is None:
                self._say("  [SKIP] critique unparseable twice - keeping current build")
                return
            if verdict == "LGTM":
                self.log("critique-lgtm", round=round_no)
                self._say("  [OK] LGTM - early exit")
                return
            self.critique_history.append({"round": round_no, "critique": verdict})
            flagged = [f for f in verdict.get("files", [])
                       if (self.workspace / f.get("path", "")).exists()]
            if not flagged:
                self._say("  [SKIP] critique flagged no existing files")
                return
            self._say(f"  [REVISE] {len(flagged)} file(s) flagged (26B)")
            for f in flagged:
                self._check_time()
                self._revise_file(f["path"], f.get("issues", []))
            if self._pass_gates(context=f"critique round {round_no}"):
                self._snapshot(f"critique-round-{round_no}-pass")
            else:
                self._say("  [ROLLBACK] revision broke the gates - "
                          "restoring last good snapshot")
                self.log("rollback", round=round_no)
                self._rollback()
                return

    # ------------------------------------------------------------ helpers

    def _get_critique(self) -> dict | str | None:
        prompt = critique_prompt(self.design, self._read_files(),
                                 "clean (all static checks passed)",
                                 self.last_exec_log)
        for _ in range(2):
            text = self.llm.generate("critic", prompt).strip()
            if re.match(r"^LGTM\b", text):
                return "LGTM"
            raw = extract_json(text)
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict) and parsed.get("verdict"):
                        return parsed
                except json.JSONDecodeError:
                    pass
            self.log("critique-unparseable", sample=text[:200])
        return None

    def _group_issues(self, issues: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        entry = self.design["entrypoint"]
        for it in issues:
            target = it["file"]
            if target in ("(project)", "(run)") or not target.endswith(".py"):
                target = entry
            groups.setdefault(target, []).append(it)
        return groups

    def _fix_files(self, groups: dict[str, list[dict]]) -> None:
        all_files = self._read_files()
        for path, file_issues in groups.items():
            self._check_time()
            text = self.llm.generate("generator", fix_prompt(
                path, all_files, format_issues(file_issues), self.design))
            code = extract_code(text)
            if code is None:
                self.log("fix-no-code", file=path)
                continue
            (self.workspace / path).write_text(code, encoding="utf-8")
            all_files[path] = code
            self.log("file-fixed", file=path)

    def _revise_file(self, path: str, issues: list[str]) -> None:
        text = self.llm.generate("generator", revise_prompt(
            path, self._read_files(), issues, self.design))
        code = extract_code(text)
        if code is None:
            self.log("revise-no-code", file=path)
            return
        (self.workspace / path).write_text(code, encoding="utf-8")
        self.log("file-revised", file=path)

    def _blame_file(self, log_text: str) -> str:
        """실행 로그의 트레이스백에서 책임 파일을 고른다. 못 찾으면 진입점."""
        project_files = {f["path"] for f in self.design["files"]}
        hits = re.findall(r'File "(?:/app/)?([\w.]+\.py)"', log_text)
        for name in reversed(hits):  # 가장 깊은 프레임 우선
            if name in project_files:
                return name
        return self.design["entrypoint"]

    def _read_files(self) -> dict[str, str]:
        return {p.name: p.read_text(encoding="utf-8")
                for p in sorted(self.workspace.glob("*.py"))}

    # ------------------------------------------------------------ snapshots

    def _git(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.workspace),
             "-c", "user.name=arag", "-c", "user.email=arag@local", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL)

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

    # ------------------------------------------------------------ report

    def _write_report(self, idea: str, status: str) -> None:
        if self.design is None:
            design_part = "(no accepted design)"
            run_part = ""
        else:
            sig = self.design["success_signal"]
            criteria = "\n".join(f"- {c}" for c in self.design["acceptance_criteria"])
            files = "\n".join(f"- `{f['path']}` - {f.get('role', '')}"
                              for f in self.design["files"])
            design_part = (f"## Files\n{files}\n\n"
                           f"## Acceptance criteria\n{criteria}\n")
            run_part = (f"## How to run\n```\ncd {self.workspace}\n"
                        f"{sig['command']}\n```\n"
                        f"(expected output contains: `{sig['expect_substring']}`)\n")
        critiques = ""
        for entry in self.critique_history:
            critiques += f"\n### Round {entry['round']}\n"
            for f in entry["critique"].get("files", []):
                critiques += f"- **{f.get('path')}**\n"
                for i in f.get("issues", []):
                    critiques += f"  - {i}\n"
        report = (f"# Generator run report\n\n"
                  f"- Status: **{status}**\n"
                  f"- Idea: {idea}\n"
                  f"- API calls used: {getattr(self.llm, 'call_count', '?')}\n\n"
                  f"{design_part}\n{run_part}\n"
                  f"## Critique history\n{critiques or '(none - passed without revision)'}\n\n"
                  f"## Last execution log\n```\n{self.last_exec_log}\n```\n")
        (self.run_dir / "REPORT.md").write_text(report, encoding="utf-8")


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
    args = parser.parse_args()

    skip_exec = args.skip_exec
    if not skip_exec and not docker_available():
        print("[WARN] Docker is not available - execution gate will be skipped")
        skip_exec = True

    from llm import LLMClient
    llm = LLMClient(max_calls=args.max_calls)

    run_dir = PROJECT_ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"[START] run dir: {run_dir}")
    orch = Orchestrator(llm, run_dir, critique_rounds=args.rounds,
                        skip_exec=skip_exec, max_minutes=args.max_minutes)
    ok = orch.run(args.idea)
    print(f"[INFO] API calls used: {llm.call_count}")
    print(f"[INFO] report: {run_dir / 'REPORT.md'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
