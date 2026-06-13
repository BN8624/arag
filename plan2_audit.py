# PLAN 2 폰 감사 화면 (콜0): 런 결과를 아이폰에서 yes/no로 판단 가능한 산문 1화면으로 렌더
"""PLAN.md §5 구현 — 코드 안 읽는 사용자가 폰에서 판단하는 런 요약.

콜0. run 디렉토리(events.jsonl·workspace·design.json) + index 엔트리 + plan2 레코드로
산문을 만든다. ASCII만(cp949 안전). 출력 끝에 사람 체크 3개.
"""

import json
from pathlib import Path

import plan2
from observability import _read_events


def _elapsed_sec(events: list[dict]) -> int | None:
    """events 첫/끝 타임스탬프로 런 경과시간 추정 (index에 elapsed 없음)."""
    ts = [e.get("t") for e in events if e.get("t")]
    if len(ts) < 2:
        return None
    from datetime import datetime
    try:
        a = datetime.fromisoformat(ts[0])
        b = datetime.fromisoformat(ts[-1])
        return int((b - a).total_seconds())
    except ValueError:
        return None


def _files_made(run_dir: Path) -> list[str]:
    ws = run_dir / "workspace"
    if not ws.exists():
        return []
    return sorted(p.name for p in ws.rglob("*.py")
                  if "deps" not in p.parts and p.name != "__init__.py")


def _scoreboard(events: list[dict]) -> list[dict]:
    """마지막 scoreboard 이벤트의 결과 리스트."""
    boards = [e for e in events if e.get("event") == "scoreboard"]
    return boards[-1].get("results", []) if boards else []


def _machine_notes(classify_row: dict) -> list[str]:
    earned = set(classify_row.get("earned", []))
    out = []
    if "failure-located" in earned:
        out.append("실패 위치 특정 가능")
    if "lesson-converted" in earned:
        out.append("오답노트 후보 있음")
    if classify_row.get("quality"):
        out.append(f"관측 품질 {classify_row['quality']}")
    return out


def _fmt_time(sec: int | None) -> str:
    if sec is None:
        return "-"
    return f"{sec // 60}m {sec % 60}s"


def render_audit(run_dir, entry: dict) -> str:
    """런 1건의 폰 감사 산문. run_dir=런 디렉토리, entry=index 엔트리."""
    run_dir = Path(run_dir)
    events = _read_events(run_dir)
    from observability import classify_run
    crow = classify_run(run_dir, entry)
    rec = plan2.build_record(entry, run_dir)
    board = _scoreboard(events)
    passed = [r.get("criterion", "?") for r in board if r.get("passed")]
    failed = [(r.get("criterion", "?"), r.get("detail", "")) for r in board
              if not r.get("passed")]

    cid = entry.get("task_id") or entry.get("run", "?")
    name = (entry.get("idea") or "").strip()
    mode = rec["mode"]
    cost = rec["cost_usd"]
    rounds = rec["repair_rounds"]
    rounds_s = f"{rounds}/{plan2.REPAIR_BUDGET}" if rounds is not None else "-"

    lines = [
        f"[{cid}] {name} / {mode}",
        f"결과: {rec['final_label']}",
        f"점수: prototype {rec['prototype_score_auto']}/5, "
        f"failure_usefulness {rec['failure_usefulness_auto']}/5 (기계 잠정)",
        f"비용: ${cost}   시간: {_fmt_time(_elapsed_sec(events))}   "
        f"수리: {rounds_s}",
        "만든 것:",
    ]
    lines += [f"- {f}" for f in _files_made(run_dir)] or ["- (없음)"]
    lines.append("통과:")
    lines += [f"- {c}" for c in passed] or ["- (없음)"]
    lines.append("실패:")
    lines += [f"- {c}" + (f" ({d})" if d else "") for c, d in failed] \
        or ["- (없음)"]
    lines.append("기계 판단:")
    lines += [f"- {n}" for n in _machine_notes(crow)] or ["- (없음)"]
    lines += [
        "사람 확인:",
        "[ ] 판정 맞음",
        "[ ] 프로토타입으로 건질 수 있음",
        "[ ] 오답노트로 쓸 만함",
    ]
    return "\n".join(lines)
