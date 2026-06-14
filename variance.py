# 분산(C)·노트효과 델타(D) 분석: index.json을 (카드×아키텍처×역할×모드)로 묶어 통과율을 낸다
"""같은 조건의 반복 런을 묶어 통과율(분산)과 cold/warm 노트 효과 델타를 계산한다.

왜: L4가 같은 조건에서 PASS↔FAIL로 뒤집힌다(분산). 한 번 돌려 "한다/못한다"를 단정하면
오판이다. 조건별로 N번 묶어 통과율을 봐야 "천장(능력 한계)"과 "분산(운)"이 갈린다.

그룹키는 저장하지 않고 entry 필드(task_id·whole·critic_model·generator_model·mode)에서
파생한다 → 스키마 변경 전 구버전 런도 best-effort로 묶인다(모델 미기록이면 '?').

사용:
  python variance.py             # 조건별 통과율(C) + 노트 델타(D) 전체
  python variance.py T-000007    # 특정 카드만
"""

import sys
from collections import defaultdict
from pathlib import Path

from config import PROJECT_ROOT, force_utf8_stdout
from run_index import load_index


def _model_tag(model_id) -> str:
    """'gemma-4-26b-a4b-it' -> '26b'. 미기록이면 '?'."""
    if not model_id:
        return "?"
    for part in str(model_id).split("-"):
        if part and part[0].isdigit() and part.endswith("b"):
            return part
    return str(model_id)


def condition_key(entry: dict) -> tuple:
    """모드를 뺀 조건(카드·아키텍처·역할). cold/warm 페어링(D)의 기준이 된다."""
    arch = "whole" if entry.get("whole") else "perfile"
    head = _model_tag(entry.get("critic_model"))
    hands = _model_tag(entry.get("generator_model"))
    return (entry.get("task_id") or "(no-card)", arch,
            f"head{head}+hands{hands}")


def _passed(entry: dict) -> bool:
    return bool(entry.get("ok") or str(entry.get("status", "")).startswith("OK"))


def aggregate(entries: list[dict], card: str | None = None) -> dict:
    """(조건, 모드) -> {n, passed, runs}. card 주면 그 카드만."""
    groups: dict[tuple, dict] = defaultdict(
        lambda: {"n": 0, "passed": 0, "runs": []})
    for e in entries:
        if not e.get("task_id"):
            continue  # 카드 없는 일반 런은 분산 분석 대상 아님
        if card and e.get("task_id") != card:
            continue
        key = condition_key(e) + (e.get("mode", "warm"),)
        g = groups[key]
        g["n"] += 1
        ok = _passed(e)
        g["passed"] += int(ok)
        g["runs"].append((e.get("run"), ok))
    return groups


def note_deltas(groups: dict) -> list[dict]:
    """같은 조건의 cold vs warm 통과율 차이(D). 양쪽 다 있는 조건만."""
    by_cond: dict[tuple, dict] = defaultdict(dict)
    for (cond_a, cond_b, cond_c, mode), g in groups.items():
        by_cond[(cond_a, cond_b, cond_c)][mode] = g
    out = []
    for cond, modes in by_cond.items():
        if "cold" in modes and "warm" in modes:
            c, w = modes["cold"], modes["warm"]
            cr = c["passed"] / c["n"] if c["n"] else 0
            wr = w["passed"] / w["n"] if w["n"] else 0
            out.append({"condition": cond, "cold_rate": cr, "warm_rate": wr,
                        "delta": wr - cr, "cold_n": c["n"], "warm_n": w["n"]})
    return out


def main(argv=None) -> int:
    force_utf8_stdout()
    args = list(argv if argv is not None else sys.argv[1:])
    card = args[0] if args else None
    entries = load_index(PROJECT_ROOT / "runs")
    groups = aggregate(entries, card)

    print("=== (C) 조건별 통과율 (분산) ===")
    if not groups:
        print("  (카드 런 없음)")
    for key in sorted(groups):
        task, arch, role, mode = key
        g = groups[key]
        rate = g["passed"] / g["n"] if g["n"] else 0
        flag = ""
        if g["n"] >= 2 and 0 < g["passed"] < g["n"]:
            flag = "  <- 분산(같은 조건 갈림)"
        print(f"  {task} {arch} {role} {mode}: "
              f"{g['passed']}/{g['n']} = {rate:.0%}{flag}")

    print("\n=== (D) 노트 효과 델타 (warm - cold) ===")
    deltas = note_deltas(groups)
    if not deltas:
        print("  (cold·warm 페어가 아직 없음 - warm 캠페인 필요)")
    for d in sorted(deltas, key=lambda x: -x["delta"]):
        t, arch, role = d["condition"]
        print(f"  {t} {arch} {role}: cold {d['cold_rate']:.0%}"
              f"(n={d['cold_n']}) -> warm {d['warm_rate']:.0%}"
              f"(n={d['warm_n']})  델타 {d['delta']:+.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
