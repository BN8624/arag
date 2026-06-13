"""관측 체계 0단계 (콜 0, 읽기 전용): 실패 분류 + 부산물 점수.

관측 원칙(PLAN.md §1) 구현 — 실패 분류 + 부산물 점수:
- limit_type: 실패의 상위 원인 (MODEL/LOOP/SPEC/INFRA + UNKNOWN)
  애매한 실패를 4분류에 욱여넣지 않는다 — UNKNOWN 비율 자체가 taxonomy
  보강 신호다.
- artifact_score 0~5: 실패가 남긴 관측 가치 (전부 기계 채점, 모델 콜 0)
  +1 design.json이 구조적으로 유효
  +1 events가 실패 위치를 특정 (게이트 지적/설계 반려/트레이스백)
  +1 실패 유형이 taxonomy에 매핑됨 (UNKNOWN이 아님)
  +1 오답노트로 전환된 교훈이 있음 (lesson-recorded)
  +1 재현 가능 (llm_calls.jsonl 녹음 → --replay 가능)
- 품질: good(4~5) / bad(2~3) / junk(0~1).
  줄여야 할 것은 실패율이 아니라 junk 비율이다.

사용법:
    python observability.py            # 전체 런 소급 분류 리포트
대시보드 /api/obs 와 지표 탭이 같은 함수를 쓴다. 배치 가동 중에도 안전.
"""

import argparse
import json
import sys
from pathlib import Path

from config import PROJECT_ROOT, force_utf8_stdout
from run_index import load_index

# 인프라 장애 표식 (모델 실력과 무관한 실패 — batch.py의 분류와 정합 유지)
INFRA_MARKERS = ("api call failed", "winerror", "connection reset",
                 "connection aborted", "500 internal", "internal error",
                 "429", "quota", "deadline")

LIMIT_TYPES = ("MODEL_LIMIT", "LOOP_LIMIT", "SPEC_LIMIT", "INFRA_LIMIT",
               "UNKNOWN")


def _read_events(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _looks_infra(text: str) -> bool:
    t = str(text).lower()
    return any(m in t for m in INFRA_MARKERS)


def _classify_limit(status: str, events: list[dict]) -> tuple[str, str]:
    """실패의 상위 원인 (limit_type, failure_class). 규칙 우선순위 순서대로.

    근거가 명확한 것만 4분류에 넣고 나머지는 UNKNOWN — 분류기가 junk를
    만들지 않게 한다.
    """
    text = str(status).lower()
    kinds = [e.get("event") for e in events]

    # 1) 인프라: 모델/루프와 무관 (재시도 소진 500, 네트워크 절단 등)
    if _looks_infra(text) or any(
            e.get("event") == "error" and _looks_infra(e.get("reason", ""))
            for e in events):
        return "INFRA_LIMIT", "api-or-network"
    if "pip-install-failed" in kinds:
        return "INFRA_LIMIT", "pip-install"

    # 2) 스펙: 시험지/기준 결함이 실제로 확인된 흔적
    if any(e.get("event") == "arbitration" and e.get("blame") == "test"
           for e in events) or "tests-regen" in kinds:
        return "SPEC_LIMIT", "test-overspec-or-broken"

    # 3) 루프: 구조가 기회를 못 준 경우
    if "time budget exhausted" in text:
        return "LOOP_LIMIT", "time-budget"

    # 4) 모델: 같은 실수 반복 / 수리 예산으로도 수렴 실패 / 출력 형식 위반
    if "no-progress" in kinds:
        layer = next((str(e.get("layer", "")) for e in events
                      if e.get("event") == "no-progress"), "")
        return "MODEL_LIMIT", f"no-progress:{layer or '?'}"
    if "budget-exhausted" in kinds:
        layer = next((str(e.get("layer", "")) for e in events
                      if e.get("event") == "budget-exhausted"), "")
        return "MODEL_LIMIT", f"fix-budget:{layer or '?'}"
    if "design failed" in text:
        return "MODEL_LIMIT", "design-rejected"
    if "returned no code" in text:
        return "MODEL_LIMIT", "no-code-block"

    # 5) 애매: improve 계획 파싱 실패는 모델 출력 불량(MODEL)일 수도,
    #    프롬프트 비대(LOOP, 다이어트 가설)일 수도 — 단정하지 않는다
    if "no usable plan" in text:
        return "UNKNOWN", "improve-plan-unusable"
    return "UNKNOWN", "unclassified"


def _artifact_score(run_dir: Path, events: list[dict],
                    limit_type: str) -> tuple[int, list[str]]:
    """실패 런의 관측 가치 0~5 (기계 채점). (점수, 충족 항목)."""
    run_dir = Path(run_dir)
    kinds = [e.get("event") for e in events]
    score = 0
    earned: list[str] = []

    design_path = run_dir / "design.json"
    if design_path.exists():
        try:
            d = json.loads(design_path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("files"):
                score += 1
                earned.append("design-valid")
        except (json.JSONDecodeError, OSError):
            pass

    located = any(k in kinds for k in
                  ("static-issues", "exec-issues", "design-rejected")) \
        or any(e.get("event") == "error" and e.get("traceback")
               for e in events)
    if located:
        score += 1
        earned.append("failure-located")

    if limit_type != "UNKNOWN":
        score += 1
        earned.append("taxonomy-mapped")

    if "lesson-recorded" in kinds:
        score += 1
        earned.append("lesson-converted")

    if (run_dir / "llm_calls.jsonl").exists():
        score += 1
        earned.append("replayable")

    return score, earned


def _quality(score: int) -> str:
    if score >= 4:
        return "good"
    if score >= 2:
        return "bad"
    return "junk"


def classify_run(run_dir: Path, entry: dict | None = None) -> dict:
    """런 하나의 관측 분류. 성공 런은 limit_type 없이 ok=True만."""
    run_dir = Path(run_dir)
    entry = entry or {}
    status = str(entry.get("status", ""))
    ok = bool(entry.get("ok", status.startswith("OK")))
    row = {"run": run_dir.name, "ok": ok,
           "cost_usd": entry.get("cost_usd") or 0}
    if ok:
        return row
    events = _read_events(run_dir)
    limit_type, failure_class = _classify_limit(status, events)
    score, earned = _artifact_score(run_dir, events, limit_type)
    row.update({"limit_type": limit_type, "failure_class": failure_class,
                "artifact_score": score, "earned": earned,
                "quality": _quality(score)})
    return row


def classify_all(runs_dir: Path | None = None) -> list[dict]:
    """index의 모든 런 소급 분류 (런 디렉토리가 없으면 events 없이 분류)."""
    runs_dir = Path(runs_dir) if runs_dir else PROJECT_ROOT / "runs"
    return [classify_run(runs_dir / e.get("run", ""), e)
            for e in load_index(runs_dir)]


def summary(rows: list[dict]) -> dict:
    """관측판 요약. useful = 성공 런 + good 실패 런 (관측 가치가 남은 단위)."""
    fails = [r for r in rows if not r["ok"]]
    n_ok = sum(1 for r in rows if r["ok"])
    by_limit = {k: 0 for k in LIMIT_TYPES}
    by_quality = {"good": 0, "bad": 0, "junk": 0}
    by_class: dict[str, int] = {}
    for r in fails:
        by_limit[r["limit_type"]] += 1
        by_quality[r["quality"]] += 1
        by_class[r["failure_class"]] = by_class.get(r["failure_class"], 0) + 1
    total_cost = sum(r.get("cost_usd") or 0 for r in rows)
    useful = n_ok + by_quality["good"]
    avg = (round(sum(r["artifact_score"] for r in fails) / len(fails), 2)
           if fails else None)
    return {
        "runs": len(rows), "ok": n_ok, "fails": len(fails),
        "by_limit": by_limit, "by_quality": by_quality,
        "by_class": dict(sorted(by_class.items(), key=lambda x: -x[1])),
        "avg_artifact_score": avg,
        "junk_rate": (round(by_quality["junk"] / len(fails), 3)
                      if fails else None),
        "total_cost_usd": round(total_cost, 4),
        "useful_artifacts": useful,
        "cost_per_useful_artifact": (round(total_cost / useful, 4)
                                     if useful else None),
    }


def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="loop observability report (read-only, 0 calls)")
    parser.add_argument("--runs", default=None, help="runs 디렉토리 (기본 runs)")
    args = parser.parse_args()
    rows = classify_all(Path(args.runs) if args.runs else None)
    s = summary(rows)

    print("=" * 70)
    print(f"관측 요약  런 {s['runs']} = 성공 {s['ok']} + 실패 {s['fails']}")
    print("=" * 70)
    print("limit_type 분포 (실패의 상위 원인):")
    for k in LIMIT_TYPES:
        n = s["by_limit"][k]
        if n:
            print(f"  {k:<12} {n}")
    print("\nfailure_class 상위:")
    for k, n in list(s["by_class"].items())[:8]:
        print(f"  {k:<28} {n}")
    print(f"\n실패 품질: good {s['by_quality']['good']} / "
          f"bad {s['by_quality']['bad']} / junk {s['by_quality']['junk']}"
          f"   (junk 비율 {s['junk_rate']})")
    print(f"artifact_score 평균: {s['avg_artifact_score']}")
    print(f"누적 비용 ${s['total_cost_usd']} / 유용 부산물 "
          f"{s['useful_artifacts']}개 = 부산물당 "
          f"${s['cost_per_useful_artifact']}")
    junk = [r for r in rows if not r["ok"] and r["quality"] == "junk"]
    if junk:
        print("\n[주의] junk 실패 (관측 불가능 — 최우선 수리 대상):")
        for r in junk[:6]:
            print(f"  {r['run']}  {r['limit_type']}  {r['failure_class']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
