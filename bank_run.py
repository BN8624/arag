# Design Bank B2: 카드를 한 장씩 단발 orchestrator 런으로 돌린다 (배치 improve 미사용)
"""bank의 task_card를 실행 루프에 흘려보내 태그별 붕괴 지점 데이터를 모은다.

batch.py를 거치지 않는다 → 배치 레벨 improve 후속 런이 자동으로 빠진다.
런 안 비평루프(--rounds 기본)는 유지(사용자 결정: 정상 루프 측정).
카드는 goal만 아이디어로 넣는다(A안) — 31B가 평소대로 자체 설계, 카드의
expected_failure_modes와 실제 결과는 task_id로 사후 대조(bank_report).

콜·시간이 큰 작업이라 runner를 주입 가능하게 두어 테스트는 콜 0으로 돈다.
"""

import subprocess
import sys
from pathlib import Path

from config import PROJECT_ROOT

_INFRA_MARKERS = ("api call failed", "winerror", "connection reset",
                  "connection aborted")
MAX_INFRA_STRIKES = 2  # 연속 인프라 장애 2회면 중단 (콜·시간을 장애에 안 태움)


def _default_runner(args: list[str]) -> int:
    """orchestrator를 서브프로세스로 1회 완주시키고 exit code 반환."""
    proc = subprocess.run([sys.executable, "orchestrator.py", *args],
                          cwd=PROJECT_ROOT)
    return proc.returncode


def select_cards(db, count: int, exclude=(), min_level: int = 1) -> list[str]:
    """난이도 레벨에 고루 퍼지도록 task_id를 count개 고른다 (낮은 레벨부터 라운드로빈).

    exclude: 제외할 task_id(이미 실행한 카드 등).
    min_level: 이 레벨 미만 카드는 제외 (붕괴 구간 집중 측정용, 기본 1=전부).
    """
    exclude = set(exclude)
    by_level: dict[int, list[str]] = {}
    for t in db.list_tasks():
        if t["task_id"] in exclude:
            continue
        if t["difficulty_level"] < min_level:
            continue
        by_level.setdefault(t["difficulty_level"], []).append(t["task_id"])
    picked: list[str] = []
    levels = sorted(by_level)
    idx = 0
    while len(picked) < count and any(by_level.values()):
        lv = levels[idx % len(levels)]
        if by_level[lv]:
            picked.append(by_level[lv].pop(0))
        idx += 1
        if idx > count * len(levels) + len(levels):
            break
    return picked[:count]


def run_cards(db, count: int, runner=_default_runner,
              extra_args: list[str] | None = None, exclude=(),
              min_level: int = 1) -> dict:
    """카드 count장을 한 장씩 순차 실행. 통계 dict 반환.

    extra_args: orchestrator에 덧붙일 인자(예: ['--skip-exec']). 기본 없음.
    exclude: 제외할 task_id(이미 실행한 카드).
    min_level: 이 레벨 미만 카드 제외 (붕괴 구간 집중).
    """
    extra_args = extra_args or []
    task_ids = select_cards(db, count, exclude=exclude, min_level=min_level)
    stats = {"requested": count, "selected": len(task_ids), "ok": 0,
             "failed": 0, "stopped_by": None, "results": []}
    infra_strikes = 0
    for tid in task_ids:
        card = db.get_task(tid)
        idea = card["goal"]
        code = runner([idea, "--task-id", tid, *extra_args])
        ok = code == 0
        stats["results"].append({"task_id": tid, "ok": ok, "code": code})
        if ok:
            stats["ok"] += 1
            infra_strikes = 0
        else:
            stats["failed"] += 1
            # exit code만으로 인프라/모델 구분이 안 되므로 보수적으로 카운트만
            infra_strikes += 1
            if infra_strikes >= MAX_INFRA_STRIKES:
                stats["stopped_by"] = "consecutive-failures"
                break
    return stats


def main(argv=None) -> int:
    """CLI: python bank_run.py [N] [--min-level L] [--mode cold|warm] [--skip-exec].

    --min-level는 bank_run이 소비, 나머지 플래그(값 포함)는 orchestrator로 그대로 전달.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    min_level = 1
    if "--min-level" in args:
        i = args.index("--min-level")
        min_level = int(args[i + 1])
        del args[i:i + 2]
    # count = 첫 정수 위치인자. 나머지(플래그+값)는 orchestrator로 그대로 넘긴다.
    count = 20
    for i, a in enumerate(args):
        if a.isdigit():
            count = int(a)
            del args[i]
            break
    extra = args
    from bank_db import BankDB
    from run_index import load_index

    # 이미 실행한 카드(index에 task_id 있는 런)는 제외 — 재실행 방지, 커버리지 누적
    already = {e["task_id"] for e in load_index(PROJECT_ROOT / "runs")
               if e.get("task_id")}
    with BankDB() as db:
        if db.count() == 0:
            print("[ERROR] design_bank.sqlite가 비어있다 - 먼저 bank_generate.py")
            return 1
        stats = run_cards(db, count, extra_args=extra, exclude=already,
                          min_level=min_level)
    print(f"[OK] selected={stats['selected']} ok={stats['ok']} "
          f"failed={stats['failed']} stopped_by={stats['stopped_by']} "
          f"(제외 {len(already)}장 이미 실행됨)")
    print("     리포트: python bank_report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
