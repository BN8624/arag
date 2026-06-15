"""개선 단계 (31B 계획 + 26B 적용): 성공 런을 더 좋게.

기존 기준은 회귀 방지선으로 강제 보존하고, 새 기준을 1~3개 추가한 뒤
변경 계획에 따라 표적 수정한다. NOCHANGE 출구와 불량 신규 기준 구제 포함.
Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import json
import re
from pathlib import Path

from design_validator import validate_design
from phase_common import TEST_FILE, RunAborted
from prompts import extract_code, implement_prompt, improve_prompt
from schema import extract_json


class ImprovePhase:
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
        self._say(f"[PHASE] improve from {prev.name} ({self._mlabel('critic')}) - "
                  f"previous score {self._prev_score}")
        self.log("phase", name="improve", from_run=prev.name,
                 prev_score=self._prev_score)

        # 다이어트: 시험지는 빼고 보낸다 — 기준·체크는 설계 JSON에 이미 있고,
        # 31B의 변경 계획은 시험지를 수정 대상으로 삼지 않는다 (~5K자 절약)
        code_files = {n: c for n, c in self._read_files().items()
                      if n != TEST_FILE}
        prompt = improve_prompt(old_design, code_files, self.feedback,
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
                # 에러가 "새로 추가한 채점 커맨드"에만 있으면 그 기준만 떨구고
                # 진행 (31B가 echo 리다이렉션 등을 반복해 통째로 ABORT되던 것 방지)
                salvaged = self._salvage_new_checks(old_design, design, errs)
                if salvaged is None or validate_design(salvaged[0]):
                    self.log("improve-design-rejected", errors=errs)
                    continue
                design, dropped = salvaged
                self.log("improve-criteria-salvaged", dropped=dropped)
                self._say(f"  [WARN] dropped {len(dropped)} invalid new "
                          "criteria - keeping the rest of the plan")
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
        self._say(f"[PHASE] apply improvement changes ({self._mlabel('generator')})")
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
    def _salvage_new_checks(old: dict, design: dict,
                            errs: list[str]) -> tuple[dict, list[str]] | None:
        """검증 에러가 '신규 채점 커맨드'에만 있으면 그 기준만 떨군 설계를 반환.

        기존 기준은 이미 검증을 통과했던 것이라 건드리지 않는다. 에러에
        criteria_checks 외 항목이 섞여 있거나 기존 기준이 걸렸으면 구제 불가(None).
        반환: (수정된 설계, 떨군 기준 이름들)
        """
        idxs: set[int] = set()
        for e in errs:
            m = re.match(r"criteria_checks\[(\d+)\]", str(e))
            if not m:
                return None
            idxs.add(int(m.group(1)))
        checks = list(design.get("criteria_checks") or [])
        old_set = {json.dumps(c, sort_keys=True, ensure_ascii=False)
                   for c in old.get("criteria_checks") or []}
        dropped: list[dict] = []
        for i in idxs:
            if i >= len(checks):
                return None
            if json.dumps(checks[i], sort_keys=True,
                          ensure_ascii=False) in old_set:
                return None  # 기존 기준이 걸렸다 → 구제 대상 아님
            dropped.append(checks[i])
        design = dict(design)
        design["criteria_checks"] = [c for j, c in enumerate(checks)
                                     if j not in idxs]
        # 떨군 체크와 짝인 신규 수용기준도 제거 (기존 수용기준은 보존)
        dropped_crit = {str(c.get("criterion", "")) for c in dropped}
        old_acc = {str(a) for a in old.get("acceptance_criteria") or []}
        design["acceptance_criteria"] = [
            a for a in design.get("acceptance_criteria") or []
            if not (str(a) in dropped_crit and str(a) not in old_acc)]
        names = [str(c.get("criterion") or c.get("command", ""))
                 for c in dropped]
        return design, names

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
        # 용어(evals 글 반영): 기존 기준=regression(회귀 방지선, 100% 사수 대상)
        # / 새 기준=capability(능력 확장, 낮은 통과율도 정상)
        return (f"{tag} - regression {old_passed}/{len(old)} "
                f"(was {self._prev_score}), capability "
                f"{new_passed}/{len(new)}")
