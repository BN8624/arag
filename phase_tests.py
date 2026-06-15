"""검수 시험지 단계 (31B): pytest 출제 → 시험지 자체 불량 판별 → 수리.

Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import re
from pathlib import Path

from phase_common import TEST_FILE
from prompts import extract_code, tests_fix_prompt, tests_prompt


class TestsPhase:
    def _phase_tests(self) -> None:
        """31B가 설계 계약 기반 pytest 출제. 실패해도 회차는 계속 (테스트 없이 진행)."""
        if self.skip_exec:
            return  # 실행 게이트가 없으면 pytest를 돌릴 곳도 없다
        self._say(f"[PHASE] write acceptance tests ({self._mlabel('critic')})")
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
