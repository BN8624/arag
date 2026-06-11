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

import critique_notes
import run_index
from config import PROJECT_ROOT, STOP_FILE, force_utf8_stdout
from design_validator import implementation_order, validate_design
from docker_gate import (docker_available, install_packages,
                         run_criteria_checks, run_exec_gate, run_pytest)
from gates import external_imports, format_issues, run_static_gate
from lessons import find_relevant_entries, record_lesson
from llm import CallBudgetExceeded
from prompts import (arbitrate_prompt, critique_prompt, design_prompt,
                     extract_code, extract_markdown, fix_prompt,
                     implement_prompt, improve_prompt, readme_prompt,
                     revise_prompt, tests_fix_prompt, tests_prompt)
from schema import extract_json, parse_design

K_MAX_FIX = 3          # 층마다 자가수정 상한
PARTIAL_PASS_RATE = 0.8  # 부분 합격 출하: 성공 신호 통과 + pytest 통과율 하한
DESIGN_ATTEMPTS = 3    # 설계 1회 + 재설계 2회
DEFAULT_ROUNDS = 1     # 비평-개선 바퀴 (반복 다듬기는 1/10 비용인 improve가 담당.
                       #  부분 합격이면 루프가 자동으로 2바퀴까지 허용)
DEFAULT_MAX_CALLS = 60
DEFAULT_MAX_MINUTES = 40
TEST_FILE = "test_acceptance.py"


class RunAborted(Exception):
    """가드레일 발동으로 회차 종료."""


class Orchestrator:
    def __init__(self, llm, run_dir: Path, critique_rounds: int = DEFAULT_ROUNDS,
                 skip_exec: bool = False, max_minutes: int = DEFAULT_MAX_MINUTES,
                 resume_from: Path | None = None,
                 improve_from: Path | None = None, feedback: str = ""):
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
            # 같은 장애에 재도전 콜을 더 태우지 않도록 표시한다 (브레이커)
            if "API call failed after" in str(err):
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

    def _load_lessons(self, idea: str) -> list[str]:
        try:
            entries = find_relevant_entries(idea)
            found = [str(e.get("lesson", "")).strip() for e in entries]
            if found:
                # 재발률 집계용: 주입한 lesson의 keyword를 index에 남긴다
                self._injected_lesson_keywords = sorted(
                    {str(k).lower() for e in entries
                     for k in e.get("keywords", []) if str(k).strip()})
                self.log("lessons-injected", count=len(found), lessons=found)
                self._say(f"[NOTE] {len(found)} lesson(s) from past failures injected")
            return found
        except Exception:  # noqa: BLE001 - 오답노트 문제로 회차를 막지 않는다
            return []

    def _load_notes(self) -> list[str]:
        try:
            found = critique_notes.find_relevant(self.idea)
            if found:
                self.log("critique-notes-injected", count=len(found), notes=found)
                self._say(f"[NOTE] {len(found)} critique note(s) injected")
            return found
        except Exception:  # noqa: BLE001 - 비평노트 문제로 회차를 막지 않는다
            return []

    def _record_failure(self, idea: str, reason: str) -> None:
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

    # ------------------------------------------------------------ phases

    # ------------------------------------------------------------ improve

    def _phase_improve(self) -> bool:
        """이전 성공 런을 개선. False = NOCHANGE (개선할 게 없음)."""
        prev = self.improve_from
        design_path = prev / "design.json"
        if not design_path.exists():
            raise RunAborted(f"--improve: no design.json in {prev}")
        old_design = json.loads(design_path.read_text(encoding="utf-8"))
        prev_ws = prev / "workspace"
        if not prev_ws.exists():
            raise RunAborted(f"--improve: no workspace in {prev}")

        # 이전 결과물 전체 복사 (코드 + 테스트 + fixture)
        for f in sorted(prev_ws.iterdir()):
            if f.is_file():
                (self.workspace / f.name).write_bytes(f.read_bytes())
        self._prev_score = self._prev_passed(prev)
        self._old_commands = {str(c.get("criterion", "")) or str(c.get("command", ""))
                              for c in old_design.get("criteria_checks") or []}
        self._say(f"[PHASE] improve from {prev.name} (31B) - "
                  f"previous score {self._prev_score}")
        self.log("phase", name="improve", from_run=prev.name,
                 prev_score=self._prev_score)

        prompt = improve_prompt(old_design, self._read_files(), self.feedback,
                                self._prev_scoreboard_text(prev))
        plan = None
        for _ in range(2):
            text = self.llm.generate("critic", prompt).strip()
            if re.match(r"^NOCHANGE\b", text):
                self.log("improve-nochange")
                return False
            raw = extract_json(text)
            if not raw:
                self.log("improve-plan-reject", reason="no-json",
                         tail=text[-400:])
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as err:
                self.log("improve-plan-reject", reason=f"bad-json: {err}",
                         tail=raw[-400:])
                continue
            changes = parsed.get("changes")
            design = parsed.get("design")
            if not isinstance(design, dict):
                # 폴백: 설계 재출력이 깨졌어도 변경 계획만 멀쩡하면 기존 설계로
                # 진행한다 (새 기준은 못 얻지만 떨어진 기존 기준 회복은 측정됨)
                if isinstance(changes, list) and changes:
                    self.log("improve-design-fallback")
                    self._say("  [WARN] 31B design re-emit unusable - "
                              "keeping old design, applying changes only")
                    plan = parsed
                    self.design = json.loads(json.dumps(old_design))
                    break
                self.log("improve-plan-reject", reason="no-design-no-changes",
                         tail=raw[-400:])
                continue
            design = self._merge_old_criteria(old_design, design)
            errs = validate_design(design)
            if errs:
                self.log("improve-design-rejected", errors=errs)
                continue
            plan = parsed
            self.design = design
            break
        if plan is None:
            raise RunAborted("--improve: 31B returned no usable plan")

        (self.run_dir / "design.json").write_text(
            json.dumps(self.design, ensure_ascii=False, indent=2),
            encoding="utf-8")
        self.log("improve-plan", files=[c.get("path")
                                        for c in plan.get("changes", [])])

        # 변경 계획 적용: 기존 파일은 표적 수정, 새 파일은 구현
        self._say("[PHASE] apply improvement changes (26B)")
        self.log("phase", name="implement")
        for change in plan.get("changes", []):
            self._check_time()
            path = str(change.get("path", "")).strip()
            instructions = [str(i) for i in change.get("instructions", [])]
            if not path or path == TEST_FILE:
                continue
            if (self.workspace / path).exists():
                self._revise_file(path, instructions)
            else:
                text = self.llm.generate(
                    "generator",
                    implement_prompt(self.design, path, self._read_files()))
                code = extract_code(text)
                if code is not None:
                    (self.workspace / path).write_text(code, encoding="utf-8")
                    self.log("file-written", file=path, chars=len(code))
                    self._say(f"  [OK] wrote {path}")
        return True

    @staticmethod
    def _merge_old_criteria(old: dict, new: dict) -> dict:
        """기존 기준은 회귀 방지선 — 31B가 빼먹었으면 강제로 되살린다."""
        for key in ("acceptance_criteria", "criteria_checks"):
            old_items = old.get(key) or []
            new_items = list(new.get(key) or [])
            seen = {json.dumps(i, sort_keys=True, ensure_ascii=False)
                    for i in new_items}
            restored = [i for i in old_items
                        if json.dumps(i, sort_keys=True,
                                      ensure_ascii=False) not in seen]
            new[key] = restored + new_items
        return new

    @staticmethod
    def _prev_passed(prev: Path) -> int | None:
        """이전 런의 마지막 채점표 통과 수 (events.jsonl에서)."""
        path = prev / "events.jsonl"
        if not path.exists():
            return None
        passed = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "scoreboard":
                passed = e.get("passed")
        return passed

    @staticmethod
    def _prev_scoreboard_text(prev: Path) -> str:
        path = prev / "events.jsonl"
        if not path.exists():
            return "(not available)"
        results = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "scoreboard":
                results = e.get("results")
        if not results:
            return "(not available)"
        return "\n".join(
            f"{'[PASS]' if r.get('passed') else '[FAIL]'} {r.get('criterion')}"
            + ("" if r.get("passed") else f" - {r.get('detail', '')}")
            for r in results)

    def _improvement_verdict(self) -> str | None:
        """improve 모드 결과 판정 문자열 (REPORT용). 일반 런이면 None."""
        if not self.improve_from or not self.scoreboard:
            return None
        old = [r for r in self.scoreboard
               if r.get("criterion") in self._old_commands]
        new = [r for r in self.scoreboard
               if r.get("criterion") not in self._old_commands]
        old_passed = sum(1 for r in old if r["passed"])
        new_passed = sum(1 for r in new if r["passed"])
        regressed = (self._prev_score is not None
                     and old_passed < self._prev_score)
        improved = (not regressed
                    and (new_passed > 0 or
                         (self._prev_score is not None
                          and old_passed > self._prev_score)))
        tag = ("REGRESSED" if regressed
               else "IMPROVED" if improved else "NO-GAIN")
        return (f"{tag} - old criteria {old_passed}/{len(old)} "
                f"(was {self._prev_score}), new criteria "
                f"{new_passed}/{len(new)}")

    def _resume_design(self) -> None:
        design_path = self.resume_from / "design.json"
        if not design_path.exists():
            raise RunAborted(f"--resume: no design.json in {self.resume_from}")
        self.design = json.loads(design_path.read_text(encoding="utf-8"))
        # design.json을 새 run_dir에도 복사 (REPORT 생성에 필요)
        (self.run_dir / "design.json").write_text(
            design_path.read_text(encoding="utf-8"), encoding="utf-8")
        self.log("design-resumed", from_dir=str(self.resume_from),
                 files=[f["path"] for f in self.design["files"]])
        self._say(f"[RESUME] design loaded from {self.resume_from.name} "
                  f"({len(self.design['files'])} files)")

    def _resume_tests(self) -> None:
        if self.skip_exec:
            return
        src = self.resume_from / "workspace" / TEST_FILE
        if src.exists():
            (self.workspace / TEST_FILE).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8")
            self.log("tests-resumed", from_dir=str(self.resume_from))
            self._say(f"[RESUME] {TEST_FILE} copied from previous run")
        else:
            self._say(f"[RESUME] no {TEST_FILE} in previous run - regenerating")
            self._phase_tests()

    def _phase_design(self, idea: str, lesson_texts: list[str] | None = None) -> None:
        self._say("[PHASE] design (31B)")
        self.log("phase", name="design")
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

    def _tests_look_broken(self, log: str) -> bool:
        """pytest 실패의 책임이 테스트 코드 자체인지 판별 (보수적).

        에러 직전 프레임이 테스트 파일이나 라이브러리 내부(/deps/)이고,
        프로젝트 파일에서 터진 에러가 하나도 없을 때만 True.
        AssertionError는 코드가 계약을 못 맞춘 것이므로 제외.
        """
        if TEST_FILE not in log:
            return False
        proj_files = {f["path"] for f in (self.design or {}).get("files", [])}
        frame_re = re.compile(r"^(\S+?\.py):\d+: in ")
        err_re = re.compile(r"^E\s+(\w+(?:Error|Exception))\b")
        last_frame: str | None = None
        test_bug = proj_bug = False
        for line in log.splitlines():
            m = frame_re.match(line.strip())
            if m:
                last_frame = m.group(1)
                continue
            e = err_re.match(line.strip())
            if not e or last_frame is None:
                continue
            err_name = e.group(1)
            frame_name = Path(last_frame).name
            if err_name == "AssertionError" or frame_name in proj_files:
                proj_bug = True
            elif frame_name == TEST_FILE or "/deps/" in last_frame.replace("\\", "/"):
                if err_name in ("TypeError", "AttributeError", "KeyError",
                                "NameError", "ImportError"):
                    test_bug = True
        return test_bug and not proj_bug

    def _regenerate_tests(self, arbiter_note: str = "") -> None:
        """31B에게 (자기가 낸) 테스트의 수리를 요청. 실패하면 기존 테스트 유지."""
        import ast as ast_mod
        test_path = self.workspace / TEST_FILE
        current = test_path.read_text(encoding="utf-8")
        tail = "\n".join(self.last_exec_log.strip().splitlines()[-40:])
        if arbiter_note:
            tail += (f"\n\nARBITER VERDICT: {arbiter_note}\n"
                     "Follow this instruction even if it relaxes an "
                     "over-specified assertion.")
        text = self.llm.generate("critic",
                                 tests_fix_prompt(self.design, current, tail))
        code = extract_code(text)
        if code is None:
            self.log("tests-regen-no-code")
            return
        try:
            ast_mod.parse(code)
        except SyntaxError:
            self.log("tests-regen-syntax-error")
            return
        test_path.write_text(code, encoding="utf-8")
        self.log("tests-regen-written", chars=len(code))
        self._say(f"  [OK] rewrote {TEST_FILE}")

    def _phase_tests(self) -> None:
        """31B가 설계 계약 기반 pytest 출제. 실패해도 회차는 계속 (테스트 없이 진행)."""
        if self.skip_exec:
            return  # 실행 게이트가 없으면 pytest를 돌릴 곳도 없다
        self._say("[PHASE] write acceptance tests (31B)")
        self.log("phase", name="tests")
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
        self.log("phase", name="implement")
        notes = self._load_notes()
        order = implementation_order(self.design)
        written: dict[str, str] = {}
        for path in order:
            self._check_time()
            text = self.llm.generate("generator",
                                     implement_prompt(self.design, path, written,
                                                      notes=notes))
            code = extract_code(text)
            if code is None:
                # 한 번만 재요청
                text = self.llm.generate("generator",
                                         implement_prompt(self.design, path, written,
                                                          notes=notes))
                code = extract_code(text)
                if code is None:
                    raise RunAborted(f"implementer returned no code block for {path}")
            (self.workspace / path).write_text(code, encoding="utf-8")
            written[path] = code
            self.log("file-written", file=path, chars=len(code))
            self._say(f"  [OK] wrote {path}")

    def _write_fixtures(self) -> None:
        """설계가 출제한 모의 API 응답 파일을 워크스페이스에 깐다 (콜 0)."""
        for fx in (self.design or {}).get("mock_fixtures") or []:
            path = str(fx.get("path", "")).strip()
            if not path:
                continue
            content = fx.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, indent=2)
            (self.workspace / path).write_text(content, encoding="utf-8")
            self.log("fixture-written", file=path, chars=len(content))
            self._say(f"  [OK] wrote fixture {path}")

    def _pass_gates(self, context: str) -> bool:
        """정적 게이트 -> 실행 게이트, 층별 K회 자가수정. 둘 다 통과하면 True."""
        static_left = K_MAX_FIX
        exec_left = K_MAX_FIX
        seen_static: set[frozenset] = set()
        seen_exec: set[frozenset] = set()

        while True:
            self._check_time()
            issues = run_static_gate(self.workspace, self.design)
            if issues:
                self._last_issues = issues
                sig = frozenset((i["file"], i["kind"], i["message"]) for i in issues)
                if sig in seen_static:
                    # 동일 에러 재방문 = 핑퐁(A->B->A 포함) - K를 안 채우고 중단
                    self.log("no-progress", layer="static", context=context)
                    self._say("[STUCK] static gate: error state repeated")
                    return False
                seen_static.add(sig)
                if static_left == 0:
                    self.log("budget-exhausted", layer="static", context=context)
                    self._say("[STUCK] static gate: fix budget exhausted")
                    return False
                static_left -= 1
                self.fix_count["static"] += 1
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
            pytest_only = False  # 성공 신호는 통과, pytest만 실패한 상태인가
            if not exec_issues and (self.workspace / TEST_FILE).exists():
                exec_issues, pytest_log = run_pytest(self.workspace,
                                                     deps_dir=deps_dir)
                self.last_exec_log = log_text + "\n\n" + pytest_log
                pytest_only = bool(exec_issues)
            if not exec_issues:
                self.partial_pass = False
                self._say("  [GATE] static + exec passed")
                return True
            self._last_issues = exec_issues
            if (self._tests_regen_left > 0
                    and (self.workspace / TEST_FILE).exists()
                    and self._tests_look_broken(self.last_exec_log)):
                # 실패 원인이 테스트 코드 자체 -> 26B 예산을 태우지 말고
                # 출제자(31B)에게 테스트 수리를 1회 요청
                self._tests_regen_left -= 1
                self._say("  [GATE] pytest errors come from the test file itself "
                          "-> 31B repairs tests")
                self.log("tests-regen", context=context)
                self._regenerate_tests()
                continue
            sig = frozenset(i["message"] for i in exec_issues)
            if sig in seen_exec or exec_left == 0:
                # 막혔다. 포기 전에 두 가지 출구를 순서대로 시도:
                # 1) 단언 실패 반복이면 31B 중재 (시험이 과한가, 코드가 위반인가)
                if (self._arbitration_left > 0 and pytest_only
                        and "AssertionError" in self.last_exec_log
                        and self._arbitrate(exec_issues)):
                    seen_exec.clear()
                    continue
                # 2) 성공 신호 통과 + pytest 통과율이 충분하면 부분 합격 출하
                #    (89% 완성품을 통째로 버리지 않는다 - 남은 기준은 채점표에
                #     FAIL로 남아 비평·improve의 표적이 됨)
                rate = self._pytest_pass_rate()
                if pytest_only and rate is not None and rate >= PARTIAL_PASS_RATE:
                    self.partial_pass = True
                    self.log("partial-pass", rate=round(rate, 2), context=context)
                    self._say(f"  [GATE] partial pass: success signal OK, "
                              f"pytest {rate:.0%} - shipping with open criteria")
                    return True
                if sig in seen_exec:
                    self.log("no-progress", layer="exec", context=context)
                    self._say("[STUCK] exec gate: error state repeated")
                else:
                    self.log("budget-exhausted", layer="exec", context=context)
                    self._say("[STUCK] exec gate: fix budget exhausted")
                return False
            seen_exec.add(sig)
            exec_left -= 1
            self.fix_count["exec"] += 1
            target = self._blame_file(self.last_exec_log)
            self._say(f"  [GATE] exec failed -> self-fix {target} ({exec_left} left)")
            self.log("exec-issues", context=context, target=target,
                     issues=[i["message"] for i in exec_issues])
            self._fix_files({target: exec_issues})

    def _pytest_pass_rate(self) -> float | None:
        """마지막 실행 로그의 pytest 요약에서 통과율. 요약이 없으면 None."""
        passed = re.findall(r"(\d+) passed", self.last_exec_log)
        failed = re.findall(r"(\d+) failed", self.last_exec_log)
        if not passed and not failed:
            return None
        n_pass = int(passed[-1]) if passed else 0
        n_fail = int(failed[-1]) if failed else 0
        total = n_pass + n_fail
        return n_pass / total if total else None

    def _arbitrate(self, exec_issues: list[dict]) -> bool:
        """단언 실패 반복 시 31B 중재 1콜: 시험이 과한가, 코드가 계약 위반인가.

        중재가 실제 행동(시험 수리 또는 표적 수정)으로 이어졌으면 True.
        """
        self._arbitration_left -= 1
        try:
            test_code = (self.workspace / TEST_FILE).read_text(encoding="utf-8")
            tail = "\n".join(self.last_exec_log.strip().splitlines()[-40:])
            text = self.llm.generate("critic",
                                     arbitrate_prompt(self.design, test_code, tail))
            raw = extract_json(text)
            verdict = json.loads(raw) if raw else None
        except (json.JSONDecodeError, OSError):
            verdict = None
        if not isinstance(verdict, dict):
            self.log("arbitration-unparseable")
            return False
        blame = str(verdict.get("blame", "")).strip().lower()
        instruction = str(verdict.get("instruction", "")).strip()
        self.log("arbitration", blame=blame, instruction=instruction)
        if blame == "test":
            self._say("  [ARBITER] test over-specifies the contract "
                      "-> 31B fixes the test")
            self._regenerate_tests(arbiter_note=instruction)
            return True
        if blame == "code" and instruction:
            self._say("  [ARBITER] code violates the contract -> targeted fix")
            target = self._blame_file(self.last_exec_log)
            issues = list(exec_issues) + [{"file": target, "line": 0,
                                           "kind": "arbiter",
                                           "message": f"ARBITER: {instruction}"}]
            self.fix_count["exec"] += 1
            self._fix_files({target: issues})
            return True
        return False

    def _phase_critique_loop(self) -> None:
        # 만점이면 비평 자체를 건너뜀 — 통과 빌드를 깎을 이유가 없다
        if self.scoreboard and all(r["passed"] for r in self.scoreboard):
            self._say("[SKIP] critique skipped - perfect scoreboard")
            self.log("critique-skipped-perfect")
            return
        # 부분 합격은 런 안에서 닫을 마지막 기회를 한 바퀴 더 준다
        total_rounds = (max(self.critique_rounds, 2) if self.partial_pass
                        else self.critique_rounds)
        for round_no in range(1, total_rounds + 1):
            self._check_time()
            self._say(f"[PHASE] critique round {round_no}/{total_rounds} (31B)")
            self.log("phase", name="critique", round=round_no,
                     total=total_rounds)
            self.critique_rounds_used = round_no
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
                # 수정이 게이트·채점표를 통과해 살아남음 = 검증된 비평 -> 비평노트 수확
                n = critique_notes.record_notes(self.idea, flagged)
                if n:
                    self.log("critique-notes-recorded", count=n)
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

    def _context_files(self, target: str) -> dict[str, str]:
        """수리·수정 프롬프트용 컨텍스트: 표적 + 직접 의존 + 직접 역의존만.

        프로젝트 전체를 넣으면 26B thinking이 입력 크기를 따라 길어진다(비용 주범).
        설계의 의존관계 지도로 관련 파일만 추린다.
        """
        all_files = self._read_files()
        deps_map = (self.design or {}).get("dependencies", {})
        keep = {target}
        keep.update(deps_map.get(target, []))                     # 표적이 부르는 것
        keep.update(p for p, deps in deps_map.items()
                    if target in deps)                            # 표적을 부르는 것
        sliced = {name: code for name, code in all_files.items() if name in keep}
        return sliced or all_files  # 지도에 없으면 안전하게 전체

    def _fix_files(self, groups: dict[str, list[dict]]) -> None:
        for path, file_issues in groups.items():
            self._check_time()
            text = self.llm.generate("generator", fix_prompt(
                path, self._context_files(path), format_issues(file_issues),
                self.design))
            code = extract_code(text)
            if code is None:
                self.log("fix-no-code", file=path)
                continue
            (self.workspace / path).write_text(code, encoding="utf-8")
            self.log("file-fixed", file=path)

    def _revise_file(self, path: str, issues: list[str]) -> None:
        text = self.llm.generate("generator", revise_prompt(
            path, self._context_files(path), issues, self.design))
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
        tokens = getattr(self.llm, "tokens", {})
        tok_line = ""
        if tokens and any(tokens.values()):
            tok_line = (f"- Tokens: input {tokens.get('input', 0):,} / "
                        f"output {tokens.get('output', 0):,} / "
                        f"thinking {tokens.get('thinking', 0):,}\n")
            by_role = getattr(self.llm, "tokens_by_role", None)
            cost_fn = getattr(self.llm, "cost_usd", None)
            if by_role and cost_fn:
                costs = cost_fn()
                for role, label in (("generator", "26B"), ("critic", "31B")):
                    t = by_role.get(role, {})
                    if any(t.values()):
                        tok_line += (
                            f"  - {label} ({role}): input {t.get('input', 0):,} / "
                            f"output {t.get('output', 0):,} / "
                            f"thinking {t.get('thinking', 0):,} "
                            f"-> ${costs.get(role, 0):.4f}\n")
                tok_line += (f"- Cost (OpenRouter paid equivalent): "
                             f"**${costs.get('total', 0):.4f}**\n")
        improve_line = ""
        verdict = self._improvement_verdict()
        if verdict:
            improve_line = (f"- Improved from: {self.improve_from.name}\n"
                            f"- Improvement: **{verdict}**\n")
        report = (f"# Generator run report\n\n"
                  f"- Status: **{status}**\n"
                  f"{improve_line}"
                  f"- Idea: {idea}\n"
                  f"- API calls used: {getattr(self.llm, 'call_count', '?')}\n"
                  f"{tok_line}\n"
                  f"{design_part}\n{run_part}\n{score_part}"
                  f"## Critique history\n{critiques or '(none - passed without revision)'}\n\n"
                  f"## Last execution log\n```\n{self.last_exec_log}\n```\n")
        (self.run_dir / "REPORT.md").write_text(report, encoding="utf-8")
        self._record_index(idea, status)

    def _record_index(self, idea: str, status: str) -> None:
        """runs/index.json에 런 한 줄 요약 누적 (콜 0, 실패해도 무시)."""
        cost_fn = getattr(self.llm, "cost_usd", None)
        costs = cost_fn() if cost_fn else {}
        entry = {
            "run": self.run_dir.name,
            "t": datetime.now().isoformat(timespec="seconds"),
            "idea": idea,
            "status": status,
            "ok": status.startswith("OK"),
            "score": {"passed": self._score_passed(),
                      "total": len(self.scoreboard) if self.scoreboard else None},
            "calls": getattr(self.llm, "call_count", None),
            "tokens": dict(getattr(self.llm, "tokens", {}) or {}),
            "cost_usd": round(costs.get("total", 0), 6) if costs else None,
            "fixes": dict(self.fix_count),
            "critique_rounds": self.critique_rounds_used,
            "packages": list(self._packages),
            "failure_keywords": list(self._failure_keywords),
        }
        if self._injected_lesson_keywords:
            entry["lessons_injected"] = list(self._injected_lesson_keywords)
        if self.scoreboard:
            # 배치의 자동 improve가 "뭘 고칠지"를 공짜로 알 수 있게 (피드백 원료)
            entry["failed_criteria"] = [r["criterion"] for r in self.scoreboard
                                        if not r["passed"]]
        if self.improve_from:
            entry["improved_from"] = self.improve_from.name
            entry["improvement"] = self._improvement_verdict()
        if run_index.record_run(self.run_dir, entry):
            self.log("index-recorded", run=entry["run"], status=status)


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
    orch = Orchestrator(llm, run_dir, critique_rounds=args.rounds,
                        skip_exec=skip_exec, max_minutes=args.max_minutes,
                        resume_from=resume_from, improve_from=improve_from,
                        feedback=args.feedback)
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
                            resume_from=retry_resume)
        ok = orch.run(args.idea)

    print(f"[INFO] API calls used: {llm.call_count}")
    print(f"[INFO] report: {run_dir / 'REPORT.md'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
