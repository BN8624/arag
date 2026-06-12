"""평가자 노트: 31B 평가자(비평·시험지 출제·총평)의 후한 판정 사례 수집 (콜 0).

세 번째 노트다. 분담:
- lessons.json            = "뭐가 깨지나" → 설계 단계(31B 입력)에 주입 (26B 실패 예방)
- critique_notes.json     = "뭐가 코드를 좋게 하나" → 구현 단계(26B 입력)에 주입
- evaluator_mistakes.json = 평가자(31B) 자체가 틀린 사례 → 평가자 교정 자료

중요(합의): 지금은 **수집 + 표시만** 한다 — 프롬프트 자동 주입은 하지 않는다.
같은 유형이 PROMOTE_FLOOR(3)회 이상 반복되면 critique/tests 프롬프트의
승격 후보로 표시만 한다. (Anthropic 하네스 글의 "평가자도 튜닝 대상" 반영)

수집 케이스 — 전부 기존 기록(index.json, events.jsonl, auto_review.json)에서 추출:
- false-lgtm      : 비평이 LGTM을 줬는데 사용자 시점 총평은 SUGGEST
                    (비평가가 사용자 눈높이의 빈틈을 놓침)
- perfect-but-gap : 채점표 만점인데 총평이 아쉬움을 지적
                    (출제된 시험지에 빈틈 — 기준이 사용자 가치를 다 못 덮음)
- partial-lgtm    : 부분 합격(미통과 기준 잔존)인데 비평이 LGTM
                    (떨어진 기준을 비평가가 못 잡음)
- repeat-review   : improve를 거쳤는데 총평이 비슷한 문제를 다시 지적
                    (개선 계획 또는 검증이 헛돎)

수확은 멱등(전체 재구축) — runs/를 다시 스캔해 파일을 통째로 다시 쓴다.
"""

import json
import re
import sys
from pathlib import Path

from config import PROJECT_ROOT
from run_index import load_index

NOTES_PATH = PROJECT_ROOT / "evaluator_mistakes.json"
PROMOTE_FLOOR = 3       # 이만큼 반복된 유형은 프롬프트 승격 후보로 표시
REPEAT_OVERLAP = 0.4    # repeat-review 판정: 피드백 토큰 겹침 비율 하한
DETAIL_MAX = 200


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[0-9a-zA-Z가-힣]{2,}", str(text).lower()))


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _review(run_dir: Path) -> dict | None:
    return _read_json(run_dir / "auto_review.json")


def _has_lgtm(run_dir: Path) -> bool:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            if json.loads(line).get("event") == "critique-lgtm":
                return True
        except json.JSONDecodeError:
            continue
    return False


def _feedback_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def harvest(runs_dir: Path, path: Path | None = None) -> list[dict]:
    """runs/ 전체에서 평가자 실수 사례를 재수집해 저장. 사례 목록 반환.

    실패해도 배치·분석을 막지 않도록 예외를 내지 않는다.
    """
    try:
        runs_dir = Path(runs_dir)
        entries = load_index(runs_dir)
        by_run = {str(e.get("run", "")): e for e in entries}
        mistakes: list[dict] = []
        for e in entries:
            run = str(e.get("run", ""))
            run_dir = runs_dir / run
            if not run_dir.exists():
                continue
            review = _review(run_dir)
            suggest = bool(review and review.get("verdict") == "SUGGEST")
            feedback = str(review.get("feedback", "")) if review else ""
            lgtm = _has_lgtm(run_dir)
            score = e.get("score") or {}
            perfect = bool(score.get("total")
                           and score.get("passed") == score.get("total"))
            partial = str(e.get("status", "")).startswith("OK (partial")

            def note(kind: str, detail: str) -> dict:
                return {"t": e.get("t"), "run": run, "kind": kind,
                        "idea": str(e.get("idea", ""))[:80],
                        "detail": detail[:DETAIL_MAX]}

            if lgtm and suggest:
                mistakes.append(note("false-lgtm", feedback))
            if perfect and suggest:
                mistakes.append(note("perfect-but-gap", feedback))
            if partial and lgtm:
                failed = ", ".join(str(c) for c in
                                   e.get("failed_criteria") or [])
                mistakes.append(note("partial-lgtm", failed or "(unknown)"))
            src = str(e.get("improved_from") or "")
            if src and suggest:
                src_review = _review(runs_dir / src)
                if (src_review and src_review.get("verdict") == "SUGGEST"
                        and _feedback_overlap(
                            feedback, str(src_review.get("feedback", "")))
                        >= REPEAT_OVERLAP):
                    mistakes.append(note(
                        "repeat-review",
                        f"(improve {src} 후에도) {feedback}"))
        Path(path or NOTES_PATH).write_text(
            json.dumps(mistakes, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return mistakes
    except Exception:  # noqa: BLE001
        return []


def promotion_candidates(mistakes: list[dict] | None = None,
                         min_count: int = PROMOTE_FLOOR,
                         path: Path | None = None) -> list[tuple[int, str]]:
    """프롬프트 승격 후보: min_count회 이상 반복된 유형 (빈도 내림차순)."""
    if mistakes is None:
        p = Path(path or NOTES_PATH)
        try:
            mistakes = json.loads(p.read_text(encoding="utf-8")) \
                if p.exists() else []
        except (json.JSONDecodeError, OSError):
            mistakes = []
    freq: dict[str, int] = {}
    for m in mistakes:
        kind = str(m.get("kind", ""))
        if kind:
            freq[kind] = freq.get(kind, 0) + 1
    out = [(n, kind) for kind, n in freq.items() if n >= min_count]
    out.sort(key=lambda x: -x[0])
    return out


def main() -> int:
    from config import force_utf8_stdout
    force_utf8_stdout()
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "runs"
    mistakes = harvest(runs_dir)
    print(f"[EVAL-NOTES] {len(mistakes)} mistake(s) harvested "
          f"-> {NOTES_PATH.name}")
    for m in mistakes:
        print(f"  {m['run']}  [{m['kind']}]  {m['detail'][:70]}")
    cands = promotion_candidates(mistakes)
    if cands:
        print("[EVAL-NOTES] prompt-promotion candidates "
              f"(>= {PROMOTE_FLOOR} repeats):")
        for n, kind in cands:
            print(f"  {kind}: {n}회 — critique/tests 프롬프트 보강 검토")
    return 0


if __name__ == "__main__":
    sys.exit(main())
