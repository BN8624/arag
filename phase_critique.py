"""품질심사 단계 (31B): 증거 기반 비평 → 표적 수정(26B) → 게이트 재확인/롤백.

만점이면 생략, LGTM이면 조기 종료, 점수 후퇴·게이트 파손이면 직전 합격품 복원.
살아남은 비평은 비평노트로 수확한다.
Orchestrator에 믹스인으로 들어간다 — self는 Orchestrator 인스턴스.
"""

import json
import re

import critique_notes
from phase_common import TEST_FILE
from prompts import critique_prompt
from schema import extract_json


class CritiquePhase:
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
            self._say(f"[PHASE] critique round {round_no}/{total_rounds} "
                      f"({self._mlabel('critic')})")
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
            self._say(f"  [REVISE] {len(flagged)} file(s) flagged "
                      f"({self._mlabel('generator')})")
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
