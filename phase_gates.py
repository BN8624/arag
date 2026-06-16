"""게이트 단계: 정적 → 실행(Docker) → pytest → 채점표, 층별 K회 자가수정.

진전 없음 감지, 시험지 불량 수리 위임, 단언 분쟁 중재, 부분 합격 출하까지
게이트 통과에 관련된 모든 판단이 여기 모여 있다.
Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import json
import re
from pathlib import Path

import trace_diff
from docker_gate import (install_packages, run_criteria_checks, run_exec_gate,
                         run_pytest, run_turn_trace)
from gates import external_imports, format_issues, run_static_gate
from phase_common import K_MAX_FIX, PARTIAL_PASS_RATE, TEST_FILE, RunAborted
from prompts import arbitrate_prompt, extract_code, fix_prompt, revise_prompt
from schema import extract_json


class GatesPhase:
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
            exec_issues = self._add_trace_hint(exec_issues)
            self._say(f"  [GATE] exec failed -> self-fix {target} ({exec_left} left)")
            self.log("exec-issues", context=context, target=target,
                     issues=[i["message"] for i in exec_issues])
            self._fix_files({target: exec_issues})

    def _add_trace_hint(self, exec_issues: list[dict]) -> list[dict]:
        """골든 불일치 시 모델 트레이스를 골든과 diff해 '몇 턴째 어느 규칙' 힌트를 붙인다.

        trace-diff 오라클(결정27): all-or-nothing 최종상태 피드백을 첫-발산 국소화로 보강.
        golden_from/golden_traces가 있을 때만 작동. **게이트 판정은 안 바꾼다** — 자가수정
        프롬프트에 들어갈 issue 하나를 추가할 뿐. 트레이스를 못 뽑으면 조용히 기존 issue 유지.
        """
        gdir = self.golden_from / "golden_traces" if self.golden_from else None
        if not gdir or not gdir.is_dir():
            return exec_issues
        blob = "\n".join(i.get("message", "") for i in exec_issues)
        if "golden output mismatch" not in blob:   # 크래시/타임아웃엔 트레이스 무의미
            return exec_issues
        deps = self.deps_dir if getattr(self, "_packages", None) else None
        for scen_file in sorted(gdir.glob("scen*.txt")):
            m = re.search(r"scen(\d+)", scen_file.name)
            if not m:
                continue
            scenario = int(m.group(1))
            try:
                model_trace = run_turn_trace(self.workspace, scenario, deps_dir=deps)
                div = trace_diff.first_divergence(
                    model_trace, scen_file.read_text(encoding="utf-8"))
            except OSError:
                div = None
            if div:
                hint = trace_diff.hint_text(div)
                self.log("trace-hint", scenario=scenario, turn=div.get("turn"),
                         kind=div.get("kind"))
                self._say(f"  [TRACE] scenario {scenario}: 첫 발산 턴 "
                          f"{div.get('turn')} ({div.get('kind')})")
                return list(exec_issues) + [{
                    "file": self.design.get("entrypoint", "main.py"), "line": 0,
                    "kind": "trace-hint",
                    "message": f"(scenario {scenario}) {hint}"}]
        return exec_issues

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
            label = ""
            if self.improve_from and self._old_commands:
                # regression=기존 기준(사수 대상) / capability=새 기준(확장)
                kind = ("regression"
                        if r.get("criterion") in self._old_commands
                        else "capability")
                label = f" [{kind}]"
            line = f"{mark}{label} {r['criterion']}"
            if not r["passed"]:
                line += f" - {r['detail']}"
            lines.append(line)
        return "\n".join(lines)

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
