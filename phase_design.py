"""설계 단계 (31B): 오답노트 주입 → 설계 생성/검증 → 설계 재사용(resume).

Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import json

from design_validator import validate_design
from lessons import find_relevant_entries
from phase_common import DESIGN_ATTEMPTS, RunAborted
from prompts import design_prompt
from schema import parse_design


class DesignPhase:
    def _load_lessons(self, idea: str) -> list[str]:
        if not getattr(self, "notes_enabled", True):  # cold mode: 오답노트 주입 OFF
            self.log("notes-disabled", store="lessons", mode="cold")
            return []
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
