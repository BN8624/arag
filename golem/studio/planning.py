# Golem Studio Step 2 — Planning 단계 A/B/C 측정 하니스 (독립 리뷰가 self-review를 이기나)
"""아이디어 한 줄 → lead가 기획 초안 → ambiguity 리뷰 → 메트릭(unique_issue_count 등).

세 arm 비교(§15):
  A = lead가 초안 + 자기검토(self-review, 출제=채점 같은 모델 → 편향).
  B = lead 초안 + 독립 리뷰어 3 (서로 다른 review_axis).
  C = lead 초안 + 독립 리뷰어 10.
핵심 질문: 독립 리뷰어가 self-review보다 unique ambiguity를 충분히 더 잡나(§19 PENDING-004 임계).

사용:
  python golem/studio/planning.py --replay <fixture.json>     # 키 안 씀(plumbing 검증)
  python golem/studio/planning.py --idea "..." [--arms A,B,C] # ★키 씀(사용자 go 뒤에만)

31B(critic 역할)만 쓴다(31solo). 리뷰어는 키 11개에 병렬(워커=키). 산출물은 studio/에 저장.
"""

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))         # golem
sys.path.insert(0, str(HERE.parent.parent))  # arag 루트(llm, config)

MODEL_31 = "gemma-4-31b-it"

# 리뷰어 10축(§2.2). 각 리뷰어는 단 하나의 축에서만 ambiguity를 사냥한다(다양성 강제).
AXES = [
    "rule ambiguity: rules that can be read two different ways",
    "missing failure cases: inputs/edge cases the spec never says what happens",
    "rules not reflected in the state object: rules with no place to live in state",
    "hard-to-test rules: rules with no clear observable expected output",
    "overly complex features: features too big for a small deterministic prototype",
    "duplicate rules: rules that say the same thing twice or overlap",
    "term conflicts: the same word used with two different meanings",
    "implementation-difficulty risk: rules likely to be implemented wrong",
    "out-of-scope features: features beyond the stated goal/non-goals",
    "handoff risk: things the next team (design) will misread from this spec",
]

ISSUE_KEYS = ["ambiguous_terms", "missing_rules", "conflicting_rules",
              "underspecified_outputs", "risky_assumptions"]

_LEAD_PROMPT = """You are the PLANNING LEAD for a small DETERMINISTIC game prototype (Node.js, CommonJS,
stdlib only, no Math.random, no graphics, no real-time input, CLI/log output). The product owner gave ONE idea:

IDEA: {idea}

Write a concise planning draft someone else can implement and test. Use EXACT section markers:

=== CONCEPT ===
2-4 sentences: the core loop and what the player does.

=== GDD ===
- Player actions (each: input, state change, failure case, log output)
- Entities (enemies/items/tiles) with their rules
- Win/lose conditions
- NON-GOALS (what we will NOT build)

=== STATE ===
A JSON object: the full game state shape (turn, player, entities, log, ...).

=== REQUIREMENTS ===
A JSON array of requirements: [{{"id":"REQ-001","text":"..."}}, ...]. One rule each, testable.
"""

_REVIEW_INSTRUCTIONS = """Do NOT add features or rewrite the spec. ONLY hunt for problems on your assigned axis.
Output ONE JSON object EXACTLY in this shape (each a list of short strings, [] if none):
{{
  "ambiguous_terms": [],
  "missing_rules": [],
  "conflicting_rules": [],
  "underspecified_outputs": [],
  "risky_assumptions": [],
  "questions_for_lead": [{{"q": "...", "class": "BLOCKING|ASSUMED|DEFERRED"}}]
}}
Put each problem you find under the most fitting key. questions_for_lead: only real questions, classified.
Output the JSON object only, no prose."""

_REVIEWER_PROMPT = """You are a PLANNING REVIEWER. Your single review axis is:
AXIS: {axis}

Here is the planning draft to review:
{draft}

{instructions}
"""

_SELF_REVIEW_PROMPT = """You are the PLANNING LEAD reviewing YOUR OWN draft for ambiguity before handoff.
Here is your draft:
{draft}

{instructions}
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text):
    """모델 응답에서 첫 JSON 객체를 뽑는다(코드펜스 우선, 없으면 첫 { ~ 균형 }). 실패 시 {}."""
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _norm(s):
    """이슈 문자열 정규화(중복 판정용): 소문자·영숫자만·공백 단일화."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s).lower())).strip()


def _issues_of(review):
    """리뷰 dict에서 5개 카테고리의 이슈를 (category, text) 리스트로 평탄화."""
    out = []
    for k in ISSUE_KEYS:
        for item in (review.get(k) or []):
            out.append((k, str(item)))
    return out


def _blocking_count(review):
    return sum(1 for q in (review.get("questions_for_lead") or [])
               if str(q.get("class", "")).upper() == "BLOCKING")


def _metrics(reviews):
    """여러 리뷰의 이슈를 합쳐 total/unique/duplicate_rate/blocking 계산."""
    flat = [t for r in reviews for (_c, t) in _issues_of(r)]
    seen, unique = set(), []
    for t in flat:
        n = _norm(t)
        if n and n not in seen:
            seen.add(n)
            unique.append(t)
    total = len(flat)
    dup_rate = 0.0 if total == 0 else round(1 - len(unique) / total, 3)
    return {
        "reviewer_count": len(reviews),
        "total_issues": total,
        "unique_issue_count": len(unique),
        "duplicate_issue_rate": dup_rate,
        "blocking_count": sum(_blocking_count(r) for r in reviews),
        "unique_issues": unique,
    }


# ---- caller: fake(녹음 재생, 키X) / real(LLMClient, 키O) ----

class FakeCaller:
    """fixture JSON에서 lead 초안과 리뷰를 재생한다(콜0)."""

    def __init__(self, fixture):
        self.fx = fixture

    def draft(self, idea):
        return self.fx["lead_draft"]

    def self_review(self, idea, draft):
        return [self.fx["self_review"]]

    def reviews(self, idea, draft, axes):
        return [self.fx["reviews"][i] for i in range(len(axes))]


class RealCaller:
    """31B(critic)로 실제 호출. 리뷰어는 키풀에 병렬(워커=키). ★키 씀."""

    def __init__(self):
        import os
        os.environ["GENERATOR_MODEL"] = MODEL_31
        os.environ["CRITIC_MODEL"] = MODEL_31
        from config import get_api_keys
        from llm import KeyPool
        self.pool = KeyPool(get_api_keys(), models=[MODEL_31])

    def _one(self, prompt):
        from llm import LLMClient
        with self.pool.checkout() as key:
            return LLMClient(api_key=key).generate("critic", prompt)

    def draft(self, idea):
        return self._one(_LEAD_PROMPT.format(idea=idea))

    def self_review(self, idea, draft):
        text = self._one(_SELF_REVIEW_PROMPT.format(draft=draft, instructions=_REVIEW_INSTRUCTIONS))
        return [_extract_json(text)]

    def reviews(self, idea, draft, axes):
        out = [None] * len(axes)
        with ThreadPoolExecutor(max_workers=min(len(axes), self.pool.size)) as ex:
            futs = {ex.submit(self._one, _REVIEWER_PROMPT.format(
                axis=ax, draft=draft, instructions=_REVIEW_INSTRUCTIONS)): i
                for i, ax in enumerate(axes)}
            for fut in futs:
                i = futs[fut]
                out[i] = _extract_json(fut.result())
        return out


ARM_REVIEWERS = {"A": 0, "B": 3, "C": 10}


def run(idea, arms, caller):
    draft = caller.draft(idea)
    results = {}
    for arm in arms:
        if arm == "A":
            reviews = caller.self_review(idea, draft)
            mode = "self-review"
        else:
            n = ARM_REVIEWERS[arm]
            reviews = caller.reviews(idea, draft, AXES[:n])
            mode = f"{n} independent reviewers"
        m = _metrics(reviews)
        m["mode"] = mode
        results[arm] = m
    return draft, results


def _verdict(results):
    """§19 PENDING-004: B가 A보다 unique +30%, C가 B보다 +20% 못 늘리면 기본값 승격 안 함."""
    out = []
    a = results.get("A", {}).get("unique_issue_count")
    b = results.get("B", {}).get("unique_issue_count")
    c = results.get("C", {}).get("unique_issue_count")
    if a is not None and b is not None:
        gain = None if a == 0 else round((b - a) / a, 3)
        ok = (a == 0 and b > 0) or (gain is not None and gain >= 0.30)
        out.append(f"B vs A: unique {a}->{b} (gain={gain}) → {'독립리뷰 채택 근거 있음' if ok else '기준 미달(B 기본값 보류)'}")
    if b is not None and c is not None:
        gain = None if b == 0 else round((c - b) / b, 3)
        ok = (b == 0 and c > 0) or (gain is not None and gain >= 0.20)
        out.append(f"C vs B: unique {b}->{c} (gain={gain}) → {'10리뷰어 채택 근거 있음' if ok else '기준 미달(3리뷰어 기본 유지)'}")
    return out


def _write_outputs(idea, draft, results, api_calls):
    summary = {"idea": idea, "api_calls": api_calls, "arms": results,
               "verdict": _verdict(results)}
    (HERE / "planning_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Planning A/B/C 비교", "", f"- 아이디어: {idea}", f"- API 호출: {api_calls}회", ""]
    lines.append("| arm | 모드 | total | unique | dup_rate | blocking |")
    lines.append("|---|---|---|---|---|---|")
    for arm in ("A", "B", "C"):
        if arm in results:
            r = results[arm]
            lines.append(f"| {arm} | {r['mode']} | {r['total_issues']} | "
                         f"{r['unique_issue_count']} | {r['duplicate_issue_rate']} | {r['blocking_count']} |")
    lines += ["", "## 판정(§19 PENDING-004)"]
    lines += [f"- {v}" for v in summary["verdict"]]
    (HERE / "planning_compare.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=None, help="fixture JSON으로 키 없이 재생")
    ap.add_argument("--idea", default=None, help="기획할 아이디어 한 줄(★키 씀)")
    ap.add_argument("--arms", default="A,B,C")
    args = ap.parse_args(argv)
    arms = [a.strip().upper() for a in args.arms.split(",") if a.strip()]

    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass

    if args.replay:
        fx = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        idea = fx.get("idea", "(fixture)")
        draft, results = run(idea, arms, FakeCaller(fx))
        api_calls = 0
    elif args.idea:
        caller = RealCaller()
        draft, results = run(args.idea, arms, caller)
        api_calls = None  # 실호출(키 씀) — 정확 집계는 향후 ledger 연동
        idea = args.idea
    else:
        ap.error("--replay 또는 --idea 중 하나 필요")

    summary = _write_outputs(idea, draft, results, 0 if args.replay else api_calls)
    print(f"[PLANNING] idea={idea!r} arms={arms} api_calls={summary['api_calls']}")
    for arm in ("A", "B", "C"):
        if arm in results:
            r = results[arm]
            print(f"  [{arm}] {r['mode']}: total={r['total_issues']} "
                  f"unique={r['unique_issue_count']} dup={r['duplicate_issue_rate']} "
                  f"blocking={r['blocking_count']}")
    for v in summary["verdict"]:
        print(f"  {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
