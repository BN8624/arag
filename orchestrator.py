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
from docker_gate import (docker_available, install_packages,
                         run_criteria_checks, run_exec_gate, run_pytest)
from gates import external_imports, format_issues, run_static_gate
from lessons import find_relevant, record_lesson
from llm import CallBudgetExceeded
from prompts import (critique_prompt, design_prompt, extract_code,
                     extract_markdown, fix_prompt, implement_prompt,
                     readme_prompt, revise_prompt, tests_prompt)
from schema import extract_json, parse_design

K_MAX_FIX = 3          # 층마다 자가수정 상한
DESIGN_ATTEMPTS = 3    # 설계 1회 + 재설계 2회
DEFAULT_ROUNDS = 2     # 비평-개선 바퀴
DEFAULT_MAX_CALLS = 60
DEFAULT_MAX_MINUTES = 40
TEST_FILE = "test_acceptance.py"


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
        self.idea = ""
        self.critique_history: list[dict] = []
        self.last_exec_log = "(execution gate skipped)"
        self.scoreboard: list[dict] = []
        self.deps_dir = self.run_dir / "deps"
        self._packages: list[str] = []
        self._last_issues: list[dict] = []
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
        self.idea = idea
        try:
            self._phase_design(idea, self._load_lessons(idea))
            self._phase_tests()
            self._phase_implement()
            self._git_init()
            ok = self._pass_gates(context="initial build")
            if not ok:
                raise RunAborted("gates not passed after self-fix budget")
            self._snapshot("gates-pass-initial")
            self._run_scoreboard()
            self._phase_critique_loop()
            self._write_readme()
            self._write_pyproject()
            self._write_report(idea, status="OK")
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
            self.log("error", reason=str(err), traceback=tb)
            self._record_failure(idea, f"{err}\n{tb}")
            self._write_report(idea, status=f"ERROR: {err}")
            self._say(f"[FAIL] unexpected error: {err}")
            self._say(f"       details: {self.run_dir / 'events.jsonl'}")
            return False
        finally:
            self._events.close()

    # ------------------------------------------------------------ lessons

    def _load_lessons(self, idea: str) -> list[str]:
        try:
            found = find_relevant(idea)
            if found:
                self.log("lessons-injected", count=len(found), lessons=found)
                self._say(f"[NOTE] {len(found)} lesson(s) from past failures injected")
            return found
        except Exception:  # noqa: BLE001 - 오답노트 문제로 회차를 막지 않는다
            return []

    def _record_failure(self, idea: str, reason: str) -> None:
        try:
            entry = record_lesson(self.llm, idea, self._failure_summary(reason))
            if entry:
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

    # ------------------------------------------------------------ phases

    def _phase_design(self, idea: str, lesson_texts: list[str] | None = None) -> None:
        self._say("[PHASE] design (31B)")
        errors: list[str] = []
        for attempt in range(DESIGN_ATTEMPTS):
            self._check_time()
            text = self.llm.generate("critic",
                                     design_prompt(idea, errors or None, lesson_texts))
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

    def _phase_tests(self) -> None:
        """31B가 설계 계약 기반 pytest 출제. 실패해도 회차는 계속 (테스트 없이 진행)."""
        if self.skip_exec:
            return  # 실행 게이트가 없으면 pytest를 돌릴 곳도 없다
        self._say("[PHASE] write acceptance tests (31B)")
        import ast as ast_mod
        for attempt in range(2):
            self._check_time()
            text = self.llm.generate("critic", tests_prompt(self.design))
            code = extract_code(text)
            if code is None:
                continue
            try:
                ast_mod.parse(code)
            except SyntaxError:
                self.log("tests-syntax-error", attempt=attempt + 1)
                continue
            (self.workspace / TEST_FILE).write_text(code, encoding="utf-8")
            self.log("tests-written", chars=len(code))
            self._say(f"  [OK] wrote {TEST_FILE}")
            return
        self.log("tests-skipped", reason="no valid test code after 2 attempts")
        self._say("  [SKIP] test generation failed twice - continuing without tests")

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
                self._last_issues = issues
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

            deps_dir = self._ensure_packages()
            exec_issues, log_text = run_exec_gate(self.workspace,
                                                  self.design["success_signal"],
                                                  deps_dir=deps_dir)
            self.last_exec_log = log_text
            if not exec_issues and (self.workspace / TEST_FILE).exists():
                exec_issues, pytest_log = run_pytest(self.workspace,
                                                     deps_dir=deps_dir)
                self.last_exec_log = log_text + "\n\n" + pytest_log
            if not exec_issues:
                self._say("  [GATE] static + exec passed")
                return True
            self._last_issues = exec_issues
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
            target = self._blame_file(self.last_exec_log)
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
                       if (self.workspace / f.get("path", "")).exists()
                       and f.get("path") != TEST_FILE]  # 테스트는 계약 - 26B가 못 고침
            if not flagged:
                self._say("  [SKIP] critique flagged no existing files")
                return
            self._say(f"  [REVISE] {len(flagged)} file(s) flagged (26B)")
            for f in flagged:
                self._check_time()
                self._revise_file(f["path"], f.get("issues", []))
            if self._pass_gates(context=f"critique round {round_no}"):
                prev_score = self._score_passed()
                self._run_scoreboard()
                now_score = self._score_passed()
                if (prev_score is not None and now_score is not None
                        and now_score < prev_score):
                    # 수정본이 돌긴 하는데 수용기준을 더 못 맞춤 -> 손해 본 수정
                    self._say(f"  [ROLLBACK] revision lowered the score "
                              f"({prev_score} -> {now_score}) - restoring")
                    self.log("score-regression", round=round_no,
                             before=prev_score, after=now_score)
                    self._rollback()
                    try:
                        self._run_scoreboard()  # 복원본 점수로 되돌림
                    except Exception:  # noqa: BLE001
                        pass
                    return
                self._snapshot(f"critique-round-{round_no}-pass")
            else:
                self._say("  [ROLLBACK] revision broke the gates - "
                          "restoring last good snapshot")
                self.log("rollback", round=round_no)
                self._rollback()
                return

    # ------------------------------------------------------------ helpers

    def _ensure_packages(self) -> Path | None:
        """워크스페이스가 쓰는 화이트리스트 패키지를 deps에 설치. 없으면 None."""
        self._packages = sorted(external_imports(self.workspace))
        if (self.workspace / TEST_FILE).exists():
            self._packages = sorted(set(self._packages) | {"pytest"})
        if not self._packages:
            return None
        ok, out = install_packages(self.deps_dir, self._packages)
        if not ok:
            self.log("pip-install-failed", packages=self._packages,
                     output=out[-2000:])
            raise RunAborted(f"package install failed: {self._packages}")
        self.log("packages-installed", packages=self._packages)
        return self.deps_dir

    def _run_scoreboard(self) -> None:
        """수용기준 채점표 실행 (게이트 통과 후). 실패해도 회차는 계속."""
        self.scoreboard = []
        checks = (self.design or {}).get("criteria_checks") or []
        if self.skip_exec or not checks:
            return
        deps = self.deps_dir if self._packages else None
        self.scoreboard = run_criteria_checks(self.workspace, checks,
                                              deps_dir=deps)
        passed = sum(1 for r in self.scoreboard if r["passed"])
        self.log("scoreboard", passed=passed, total=len(self.scoreboard),
                 results=[{k: r[k] for k in ("criterion", "passed", "detail")}
                          for r in self.scoreboard])
        self._say(f"  [SCORE] acceptance checks: "
                  f"{passed}/{len(self.scoreboard)} passed")

    def _score_passed(self) -> int | None:
        if not self.scoreboard:
            return None
        return sum(1 for r in self.scoreboard if r["passed"])

    def _scoreboard_text(self) -> str:
        if not self.scoreboard:
            return "(not run)"
        lines = []
        for r in self.scoreboard:
            mark = "[PASS]" if r["passed"] else "[FAIL]"
            line = f"{mark} {r['criterion']}"
            if not r["passed"]:
                line += f" - {r['detail']}"
            lines.append(line)
        return "\n".join(lines)

    def _get_critique(self) -> dict | str | None:
        prompt = critique_prompt(self.design, self._read_files(),
                                 "clean (all static checks passed)",
                                 self.last_exec_log,
                                 self._scoreboard_text(),
                                 idea=self.idea)
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
        # pytest -q 스타일 트레이스백 (예: "core.py:12: in add_item")도 본다
        hits += re.findall(r'^([\w.]+\.py):\d+:', log_text, re.MULTILINE)
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

    # ------------------------------------------------------------ extras

    def _write_readme(self) -> None:
        """26B 1콜로 README.md 생성. 실패해도 회차는 계속 (비필수 산출물)."""
        if self.skip_exec:
            return
        try:
            text = self.llm.generate("generator", readme_prompt(self.design))
            md = extract_markdown(text)
            if md:
                (self.workspace / "README.md").write_text(md, encoding="utf-8")
                self.log("readme-written", chars=len(md))
                self._say("  [OK] README.md generated")
            else:
                self.log("readme-skipped", reason="no markdown block in response")
        except Exception as err:  # noqa: BLE001 - README 실패로 회차를 막지 않는다
            self.log("readme-skipped", reason=str(err))

    def _write_pyproject(self) -> None:
        """pip install 가능한 패키징 메타데이터. 모델 콜 0 - 기계적 생성."""
        try:
            d = self.design
            name = re.sub(r"[^a-zA-Z0-9]+", "-", d["project_name"]).strip("-").lower()
            name = name or "prototype"
            mods = [Path(f["path"]).stem for f in d["files"]
                    if f["path"].endswith(".py")
                    and not f["path"].startswith("test_")]
            deps = sorted(external_imports(self.workspace))
            deps_str = ", ".join(f'"{p}"' for p in deps)
            mods_str = ", ".join(f'"{m}"' for m in mods)
            scripts = ""
            entry_mod = Path(d["entrypoint"]).stem
            if self._entry_defines_main():
                scripts = (f'\n[project.scripts]\n'
                           f'{name} = "{entry_mod}:main"\n')
            content = (
                '[build-system]\n'
                'requires = ["setuptools>=68"]\n'
                'build-backend = "setuptools.build_meta"\n\n'
                '[project]\n'
                f'name = "{name}"\n'
                'version = "0.1.0"\n'
                f'description = "{d.get("description", "")}"\n'
                'requires-python = ">=3.10"\n'
                f'dependencies = [{deps_str}]\n'
                f'{scripts}\n'
                '[tool.setuptools]\n'
                f'py-modules = [{mods_str}]\n')
            (self.workspace / "pyproject.toml").write_text(content, encoding="utf-8")
            self.log("pyproject-written", name=name, dependencies=deps)
        except Exception as err:  # noqa: BLE001 - 패키징 실패로 회차를 막지 않는다
            self.log("pyproject-skipped", reason=str(err))

    def _entry_defines_main(self) -> bool:
        import ast as ast_mod
        path = self.workspace / self.design["entrypoint"]
        try:
            tree = ast_mod.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError):
            return False
        return any(isinstance(n, ast_mod.FunctionDef) and n.name == "main"
                   for n in tree.body)

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
            reqs = self.design.get("requirements") or []
            req_lines = "\n".join(f"- {r.get('text', '')}" for r in reqs
                                  if isinstance(r, dict))
            req_part = (f"## Requirements (decomposed from the idea)\n"
                        f"{req_lines}\n\n") if req_lines else ""
            design_part = (f"## Files\n{files}\n\n{req_part}"
                           f"## Acceptance criteria\n{criteria}\n")
            run_part = (f"## How to run\n```\ncd {self.workspace}\n"
                        f"{sig['command']}\n```\n"
                        f"(expected output contains: `{sig['expect_substring']}`)\n")
        score_part = ""
        if self.scoreboard:
            passed = sum(1 for r in self.scoreboard if r["passed"])
            score_part = (f"## Acceptance check scoreboard "
                          f"({passed}/{len(self.scoreboard)} passed)\n"
                          f"{self._scoreboard_text()}\n\n")
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
                  f"{design_part}\n{run_part}\n{score_part}"
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
    parser.add_argument("--no-retry", action="store_true",
                        help="do not auto-retry once after a failed run")
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

    # 실패 시 1회 자동 재도전: 방금 기록된 오답노트 교훈을 들고 처음부터 다시
    if not ok and not args.no_retry and llm.call_count + 8 <= args.max_calls:
        print("[RETRY] first attempt failed - retrying once with recorded lessons")
        run_dir = PROJECT_ROOT / "runs" / (
            datetime.now().strftime("%Y%m%d-%H%M%S") + "-retry")
        print(f"[START] run dir: {run_dir}")
        orch = Orchestrator(llm, run_dir, critique_rounds=args.rounds,
                            skip_exec=skip_exec, max_minutes=args.max_minutes)
        ok = orch.run(args.idea)

    print(f"[INFO] API calls used: {llm.call_count}")
    print(f"[INFO] report: {run_dir / 'REPORT.md'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
