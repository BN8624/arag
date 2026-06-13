"""구현 단계 (26B): 비평노트 주입 → 의존 순서대로 파일별 구현 → 모의 자재 배치.

Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import json

import critique_notes
from design_validator import implementation_order
from phase_common import RunAborted
from prompts import extract_code, implement_prompt


class ImplementPhase:
    def _load_notes(self) -> list[str]:
        if not getattr(self, "notes_enabled", True):  # cold mode: 비평노트 주입 OFF
            self.log("notes-disabled", store="critique_notes", mode="cold")
            return []
        try:
            found = critique_notes.find_relevant(self.idea)
            if found:
                self.log("critique-notes-injected", count=len(found), notes=found)
                self._say(f"[NOTE] {len(found)} critique note(s) injected")
            return found
        except Exception:  # noqa: BLE001 - 비평노트 문제로 회차를 막지 않는다
            return []

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
