"""산출물 마무리: README(26B 1콜) / pyproject(콜 0) / REPORT.md / 생산 장부.

전부 비필수 산출물 — 실패해도 회차를 막지 않는다 (REPORT/장부 제외).
Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import re
import time
from datetime import datetime
from pathlib import Path

import run_index
from config import get_model
from gates import external_imports
from prompts import PROMPT_VERSION, extract_markdown, readme_prompt


class ReportingMixin:
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
            # 실험 무결성: 어느 프롬프트 세대에서 나온 런인지 (전후 비교용)
            "prompt_version": PROMPT_VERSION,
            # PLAN2 cold/warm 측정: 노트 주입 여부 (cold=OFF, warm=ON)
            "mode": getattr(self, "mode", "warm"),
            "notes_enabled": getattr(self, "notes_enabled", True),
            # 역할/아키텍처 정본화(A-2): 이 런에서 머리·손·구현방식이 뭐였나 (분산·역할 비교의 그룹키 원료)
            "critic_model": get_model("critic"),        # 머리 = 설계·출제·비평
            "generator_model": get_model("generator"),  # 손 = 구현
            "whole": getattr(self, "whole", False),     # True=통짜, False=파일별 분해
            # 비용과 짝이 되는 시간(B): 런 벽시계 경과초
            "duration_sec": (round(time.monotonic() - self.started, 1)
                             if hasattr(self, "started") else None),
        }
        if self.level is not None:
            entry["level"] = self.level
        if getattr(self, "task_id", None):
            entry["task_id"] = self.task_id
        if self._injected_lesson_keywords:
            entry["lessons_injected"] = list(self._injected_lesson_keywords)
        if self.scoreboard:
            # 배치의 자동 improve가 "뭘 고칠지"를 공짜로 알 수 있게 (피드백 원료)
            entry["failed_criteria"] = [r["criterion"] for r in self.scoreboard
                                        if not r["passed"]]
        if self.improve_from:
            entry["improved_from"] = self.improve_from.name
            entry["improvement"] = self._improvement_verdict()
            if self.scoreboard and self._old_commands:
                # regression(기존 기준)/capability(새 기준) 분리 점수
                old = [r for r in self.scoreboard
                       if r.get("criterion") in self._old_commands]
                new = [r for r in self.scoreboard
                       if r.get("criterion") not in self._old_commands]
                entry["score_split"] = {
                    "regression": {"passed": sum(r["passed"] for r in old),
                                   "total": len(old)},
                    "capability": {"passed": sum(r["passed"] for r in new),
                                   "total": len(new)},
                }
        if run_index.record_run(self.run_dir, entry):
            self.log("index-recorded", run=entry["run"], status=status)
