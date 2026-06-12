"""배치 결과 분석 (콜 0, 읽기 전용 — 배치 진행 중에도 안전).

index.json + 런별 events.jsonl + llm_calls.jsonl만 읽어서,
판정 포인트 5개를 단계별(개선 반영 전/후) × 런유형별(신규/재도전/개선)로 쪼개 집계한다.

판정 포인트:
  1. 컨텍스트 다이어트 — llm_calls.jsonl의 prompt_chars (효율반영 이후 런만 녹음 있음)
  2. 단언 분쟁·pytest 자체 오류 — events의 AssertionError 포함 exec-issues, tests-regen
  3. partial 출하의 ABORTED 흡수 — "OK (partial)" 수
  4. 자동 improve 성과 — improvement 필드 (IMPROVED/NO-GAIN/REGRESSED)
  5. resume 재도전 절약 — design-resumed/tests-resumed 이벤트

단계 컷오프 (git 커밋 시각):
  기준선        < 02:11  (06-12)
  출구반영      02:11 ~ 02:39  (부분합격 출하 + 31B 중재 + improve 자동 루프)
  효율반영      >= 02:39       (컨텍스트 다이어트·비평 1바퀴·resume·브레이커·녹음)

주의(해석 시):
  - 난이도 레벨은 런별로 기록되지 않음(현재 auto_state.json의 현재값만 존재).
    적응형 난이도가 움직이면 전후 성공률 비교가 오염될 수 있음 — 레벨 변화는
    배치 로그로 따로 확인할 것.
  - improve/재도전 런은 신규 런과 비용 구조가 다르므로 평균에 섞지 않는다.

사용: python analyze_batch.py [--runs runs] [--all]
  기본은 index.json 전체. --all은 단계 구분 없이 합산도 출력.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from run_index import load_index, recurrence_stats

CUTOFF_EXITS = datetime(2026, 6, 12, 2, 11)   # 부분합격·중재·improve 루프
CUTOFF_EFF = datetime(2026, 6, 12, 2, 39)     # 효율 7종 (다이어트·resume 등)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run_time(entry: dict) -> datetime | None:
    """런 시작 시각 — 런 이름의 타임스탬프 (index의 t는 종료 시각)."""
    name = str(entry.get("run", ""))
    try:
        return datetime.strptime(name[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def phase_of(entry: dict) -> str:
    t = run_time(entry)
    if t is None:
        return "?"
    if t < CUTOFF_EXITS:
        return "기준선"
    if t < CUTOFF_EFF:
        return "출구반영"
    return "효율반영"


def type_of(entry: dict) -> str:
    if entry.get("improved_from"):
        return "improve"
    if str(entry.get("run", "")).endswith("-retry"):
        return "재도전"
    return "신규"


def status_bucket(entry: dict) -> str:
    status = str(entry.get("status", ""))
    if status.startswith("OK (partial"):
        return "OK(partial)"
    if status.startswith("OK"):
        return "OK"
    if status.startswith("ERROR"):
        return "ERROR"
    return "ABORTED"


def load_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def event_stats(events: list[dict]) -> dict:
    """판정 포인트 2·3·5에 쓰는 이벤트 카운트."""
    c = Counter(e.get("event") for e in events)
    assertion_issues = sum(
        1 for e in events if e.get("event") == "exec-issues"
        and any("AssertionError" in str(m) for m in e.get("issues", [])))
    return {
        "exec_issues": c["exec-issues"],
        "assertion_issues": assertion_issues,
        "tests_regen": c["tests-regen"],
        "arbitration": c["arbitration"],
        "partial_pass": c["partial-pass"],
        "design_resumed": c["design-resumed"],
        "tests_resumed": c["tests-resumed"],
        "rollback": c["rollback"],
    }


def prompt_diet(run_dir: Path) -> dict | None:
    """llm_calls.jsonl이 있으면 역할별 prompt_chars 평균 (다이어트 측정)."""
    path = run_dir / "llm_calls.jsonl"
    if not path.exists():
        return None
    by_role: dict[str, list[int]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        by_role.setdefault(e.get("role", "?"), []).append(
            int(e.get("prompt_chars", 0)))
    return {role: {"calls": len(v), "avg_chars": round(sum(v) / len(v))}
            for role, v in by_role.items() if v}


def fmt_row(cols, widths):
    return "  ".join(str(c).ljust(w) for c, w in zip(cols, widths))


def summarize(entries: list[dict], runs_dir: Path) -> None:
    if not entries:
        print("index.json에 런이 없습니다.")
        return

    # ── 단계 × 유형 집계 ─────────────────────────────────────────
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        groups.setdefault((phase_of(e), type_of(e)), []).append(e)

    print("=" * 78)
    print("단계 x 런유형 집계  (OK율은 partial 포함)")
    print("=" * 78)
    widths = [8, 8, 3, 12, 7, 9, 10, 9, 8]
    print(fmt_row(["단계", "유형", "n", "성패", "평균콜",
                   "평균think", "평균비용$", "수정/런", "레벨"], widths))
    phase_order = {"기준선": 0, "출구반영": 1, "효율반영": 2, "?": 3}
    for (phase, rtype), group in sorted(
            groups.items(), key=lambda kv: (phase_order.get(kv[0][0], 9), kv[0][1])):
        n = len(group)
        buckets = Counter(status_bucket(e) for e in group)
        ok = buckets["OK"] + buckets["OK(partial)"]
        outcome = (f"OK {buckets['OK']}"
                   + (f"+p{buckets['OK(partial)']}" if buckets["OK(partial)"] else "")
                   + f"/AB {buckets['ABORTED']}"
                   + (f"/ER {buckets['ERROR']}" if buckets["ERROR"] else ""))
        calls = sum(e.get("calls", 0) for e in group) / n
        think = sum(e.get("tokens", {}).get("thinking", 0) for e in group) / n
        cost = sum(e.get("cost_usd", 0) for e in group) / n
        fixes = sum(e.get("fixes", {}).get("static", 0)
                    + e.get("fixes", {}).get("exec", 0) for e in group) / n
        levels = Counter(e.get("level") for e in group if e.get("level"))
        level_str = (" ".join(f"L{lv}:{c}" for lv, c in sorted(levels.items()))
                     or "-")
        print(fmt_row([phase, rtype, n, outcome, f"{calls:.1f}",
                       f"{think / 1000:.0f}K", f"{cost:.4f}", f"{fixes:.1f}",
                       level_str], widths))
        _ = ok  # OK율은 성패 칸으로 충분

    # ── 판정 2·3·5: 이벤트 기반 ──────────────────────────────────
    print()
    print("=" * 78)
    print("이벤트 집계 (단계별 합산)  — 단언분쟁 / 부분합격 / 중재 / resume")
    print("=" * 78)
    widths2 = [8, 3, 10, 10, 9, 7, 9, 9]
    print(fmt_row(["단계", "n", "exec이슈", "단언이슈", "시험수리",
                   "중재", "부분합격", "resume"], widths2))
    by_phase: dict[str, list[dict]] = {}
    for e in entries:
        by_phase.setdefault(phase_of(e), []).append(e)
    for phase in sorted(by_phase, key=lambda p: phase_order.get(p, 9)):
        group = by_phase[phase]
        total = Counter()
        for e in group:
            stats = event_stats(load_events(runs_dir / str(e.get("run", ""))))
            total.update(stats)
        print(fmt_row([phase, len(group), total["exec_issues"],
                       total["assertion_issues"], total["tests_regen"],
                       total["arbitration"], total["partial_pass"],
                       total["design_resumed"] + total["tests_resumed"]],
                      widths2))

    # ── 판정 4: improve 성과 ─────────────────────────────────────
    print()
    print("=" * 78)
    print("improve 성과")
    print("=" * 78)
    improves = [e for e in entries if e.get("improved_from")]
    if not improves:
        print("improve 런 없음")
    for e in improves:
        verdict = e.get("improvement") or e.get("status", "?")
        score = e.get("score", {})
        print(f"  {e['run']}  <- {e['improved_from']}"
              f"  [{score.get('passed')}/{score.get('total')}]"
              f"  콜 {e.get('calls')}  ${e.get('cost_usd', 0):.4f}"
              f"  {verdict}")

    # ── 판정 1: 컨텍스트 다이어트 (녹음 있는 런만) ───────────────
    print()
    print("=" * 78)
    print("프롬프트 크기 (llm_calls.jsonl 녹음이 있는 런 = 효율반영 이후)")
    print("=" * 78)
    any_diet = False
    for e in entries:
        diet = prompt_diet(runs_dir / str(e.get("run", "")))
        if not diet:
            continue
        any_diet = True
        parts = ", ".join(f"{role} {v['calls']}콜 평균 {v['avg_chars']:,}자"
                          for role, v in sorted(diet.items()))
        print(f"  {e['run']} [{type_of(e)}]  {parts}")
    if not any_diet:
        print("녹음 있는 런 없음 (녹음은 02:43 이후 런부터)")
    print("  비교 기준이 없으므로 다이어트 효과는 input 토큰/콜로 봐야 함:")
    for phase in sorted(by_phase, key=lambda p: phase_order.get(p, 9)):
        group = [e for e in by_phase[phase] if type_of(e) != "improve"
                 and e.get("calls")]
        if not group:
            continue
        per_call = (sum(e.get("tokens", {}).get("input", 0) for e in group)
                    / sum(e.get("calls", 0) for e in group))
        print(f"    {phase}: input {per_call:,.0f} tok/콜 "
              f"(신규+재도전 {len(group)}런)")

    # ── 평가자 실수 (31B 교정 자료 — 수집·표시만, 주입 없음) ──────
    print()
    print("=" * 78)
    print("평가자 실수 수집 (false-lgtm / perfect-but-gap / partial-lgtm / repeat-review)")
    print("=" * 78)
    from evaluator_notes import PROMOTE_FLOOR, harvest, promotion_candidates
    mistakes = harvest(runs_dir)
    if not mistakes:
        print("수집된 사례 없음 (총평을 받은 런이 쌓이면 나타남)")
    for m in mistakes:
        print(f"  {m['run']}  [{m['kind']}]  {m['detail'][:70]}")
    for n, kind in promotion_candidates(mistakes):
        print(f"  [승격후보] {kind} {n}회 반복 (>= {PROMOTE_FLOOR}) — "
              "비평/출제 프롬프트 보강 검토")

    # ── 재발률 ───────────────────────────────────────────────────
    print()
    rec = recurrence_stats(entries)
    print(f"오답노트 재발률: 주입 {rec['injected_runs']}런 중 재발 "
          f"{rec['recurred']}건"
          + (f" ({rec['rate']:.0%})" if rec["rate"] is not None else ""))

    # ── 전체 비용 ────────────────────────────────────────────────
    total_cost = sum(e.get("cost_usd", 0) for e in entries)
    print(f"누적 비용(인덱스 전체): ${total_cost:.4f}  / 런 {len(entries)}개")
    print()
    print("[주의] 레벨 칸이 '-'인 런은 --level 기록 전(배치 출제 외 또는 구버전)의 런 —")
    print("       적응형 난이도가 움직였으면 단계 간 성공률 비교가 오염될 수 있음.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", default="runs", help="runs 디렉토리 (기본 runs)")
    args = parser.parse_args()
    runs_dir = Path(args.runs)
    summarize(load_index(runs_dir), runs_dir)


if __name__ == "__main__":
    main()
