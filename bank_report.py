# Design Bank B2 리포트: runs/index를 task_id로 카드와 조인 → 태그/레벨별 결과 (콜 0)
"""task_id ↔ bank 왕복 조회 + 태그별·레벨별 붕괴 지점 첫 데이터.

index의 런(task_id 보유)과 bank 카드를 조인하고, observability.classify_run으로
ok/artifact_score/limit_type를 얻어 difficulty_tag·level별로 집계한다. 전부 콜 0.
"""

from collections import defaultdict
from pathlib import Path

from config import PROJECT_ROOT
from observability import classify_run
from run_index import load_index


def join_runs(db, runs_dir: Path | None = None) -> list[dict]:
    """task_id를 가진 런만 카드와 조인한 행 목록. (index↔bank 왕복 조회)"""
    runs_dir = Path(runs_dir) if runs_dir else PROJECT_ROOT / "runs"
    rows = []
    for entry in load_index(runs_dir):
        tid = entry.get("task_id")
        if not tid:
            continue
        card = db.get_task(tid)
        if card is None:
            continue
        cls = classify_run(runs_dir / entry.get("run", ""), entry)
        rows.append({
            "task_id": tid,
            "run": entry.get("run"),
            "level": card["difficulty_level"],
            "tags": card.get("difficulty_tags", []),
            "expected_failure_modes": card.get("expected_failure_modes", []),
            "ok": cls["ok"],
            "artifact_score": cls.get("artifact_score"),
            "limit_type": cls.get("limit_type"),
            "failure_class": cls.get("failure_class"),
        })
    return rows


def latest_per_card(rows: list[dict]) -> list[dict]:
    """task_id별로 가장 최근 런 하나만 남긴다 (재도전·재실행 이중계상 제거).

    join_runs는 index 순서(시간순)를 보존하므로, 뒤에 나온 런이 최신.
    카드 단위 보정(calibration)은 카드당 1결과여야 한다.
    """
    by_card: dict[str, dict] = {}
    for r in rows:
        by_card[r["task_id"]] = r  # 같은 task_id면 뒤(최신)가 덮어씀
    return list(by_card.values())


def _agg(rows: list[dict]) -> dict:
    n = len(rows)
    ok = sum(1 for r in rows if r["ok"])
    fails = [r for r in rows if not r["ok"]]
    scores = [r["artifact_score"] for r in fails if r["artifact_score"] is not None]
    limits: dict[str, int] = defaultdict(int)
    for r in fails:
        if r["limit_type"]:
            limits[r["limit_type"]] += 1
    return {
        "n": n, "ok": ok,
        "success_rate": round(ok / n, 2) if n else None,
        "avg_artifact_score": round(sum(scores) / len(scores), 2) if scores else None,
        "limit_types": dict(limits),
    }


def per_tag(rows: list[dict]) -> dict:
    """difficulty_tag별 집계 (한 런이 여러 태그에 중복 계상)."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for tag in r["tags"]:
            buckets[tag].append(r)
    return {tag: _agg(rs) for tag, rs in buckets.items()}


def per_level(rows: list[dict]) -> dict:
    buckets: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r["level"]].append(r)
    return {lv: _agg(rs) for lv, rs in sorted(buckets.items())}


def render(db, runs_dir: Path | None = None) -> str:
    all_rows = join_runs(db, runs_dir)
    if not all_rows:
        return "조인된 런이 없다 (task_id 가진 런이 index에 없음). 먼저 bank_run.py."
    rows = latest_per_card(all_rows)  # 카드 단위 (재도전 이중계상 제거)
    lines = [f"# Design Bank B2 리포트 (카드 {len(rows)}장 / 런 {len(all_rows)}개)", ""]
    lines.append("## 레벨별")
    for lv, a in per_level(rows).items():
        lines.append(f"- L{lv}: n={a['n']} 성공률={a['success_rate']} "
                     f"실패 artifact 평균={a['avg_artifact_score']} "
                     f"limit={a['limit_types']}")
    lines.append("")
    lines.append("## 태그별 (붕괴 지점)")
    tags = per_tag(rows)
    for tag, a in sorted(tags.items(), key=lambda kv: (kv[1]["success_rate"] or 0)):
        lines.append(f"- {tag}: n={a['n']} 성공률={a['success_rate']} "
                     f"실패 artifact 평균={a['avg_artifact_score']} "
                     f"limit={a['limit_types']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    from bank_db import BankDB
    with BankDB() as db:
        print(render(db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
