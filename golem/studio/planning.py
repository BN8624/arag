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

_SYNTHESIS_PROMPT = """You are the PLANNING LEAD doing SYNTHESIS. You wrote this draft:
{draft}

Independent reviewers found these issues (JSON):
{issues}

Resolve them and FREEZE the planning contract for a small DETERMINISTIC game
(Node.js, CommonJS, stdlib only, no Math.random, CLI `node main.js --scenario N`).
Output ONE JSON object EXACTLY in this shape:
{{
  "decisions": ["concrete resolution of an ambiguity", "..."],
  "terms": {{"term": "definition"}},
  "scope": {{"goals": ["..."], "non_goals": ["..."]}},
  "data_contract": {{"state_shape": {{}}, "rules": ["..."]}},
  "interface_contract": {{"entry": "main.js", "files": [{{"path": "main.js", "exports": [], "imports": ["src/engine.js"]}}]}},
  "acceptance_tests": [{{"id": "SCN-001", "setup": "...", "input": "...", "expect": "..."}}],
  "assumed": ["assumption you fix to proceed"],
  "deferred": ["question pushed to a later version"]
}}
HARD RULE: every BLOCKING reviewer question MUST be either answered in decisions OR moved to assumed/deferred.
Leave NO blocking question open. interface_contract must be >=2 files. JSON only, no prose."""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_SECTION_RE = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)


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


_STOP = {"the", "and", "for", "are", "not", "что", "when", "with", "this", "that",
         "will", "may", "via", "per", "into", "from", "does", "between"}


def _norm(s):
    """이슈 문자열 정규화(중복 판정용): 소문자·영숫자만·공백 단일화."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s).lower())).strip()


def _tokens(s):
    """의미어 토큰 집합(3글자 이상, 불용어 제거) — 어순 무관 중복 판정용."""
    return {w for w in _norm(s).split() if len(w) > 2 and w not in _STOP}


def _similar(a, b, th):
    """두 이슈가 같은 문제를 가리키나(토큰 Jaccard ≥ th). 토큰 없으면 정규화 동일성."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return _norm(a) == _norm(b)
    return len(ta & tb) / len(ta | tb) >= th


def _dedup(items, th=0.5):
    """어휘 유사도 클러스터링으로 의미중복을 접는다(stdlib only, 키X).
    완전한 의미 dedup은 임베딩/LLM 필요 — 여긴 어휘기반 휴리스틱으로 과대계상만 줄인다."""
    reps = []
    for it in items:
        if not any(_similar(it, r, th) for r in reps):
            reps.append(it)
    return reps


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
    flat = [t for r in reviews for (_c, t) in _issues_of(r) if str(t).strip()]
    unique = _dedup(flat)
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


def _split_sections(draft):
    """초안의 '=== NAME ===' 마커로 섹션 분리. {name_upper: body}."""
    parts = _SECTION_RE.split(draft)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip().upper()] = parts[i + 1].strip()
    return out


def _aggregate_issues(reviews):
    """C arm 리뷰들을 카테고리별로 합치고 BLOCKING 질문도 모은다(synthesis 입력)."""
    agg = {k: [] for k in ISSUE_KEYS}
    blocking = []
    for r in reviews:
        for k in ISSUE_KEYS:
            agg[k].extend(r.get(k) or [])
        for q in (r.get("questions_for_lead") or []):
            if str(q.get("class", "")).upper() == "BLOCKING":
                blocking.append(q.get("q", ""))
    agg["BLOCKING_questions"] = blocking
    return agg


def run_synthesis(idea, caller):
    """전체 Planning 단계: 초안 → 리뷰어 10 → synthesis(BLOCKING→0 + 계약 패킷)."""
    draft = caller.draft(idea)
    reviews = caller.reviews(idea, draft, AXES)
    issues = _aggregate_issues(reviews)
    packet = caller.synth(idea, draft, issues)
    return draft, reviews, issues, packet


def _write_packet(idea, draft, reviews, issues, packet, outdir):
    """Golem Contract Relay 패킷(§4 핵심)을 파일로 굳힌다. BLOCKING이 0이면 FROZEN."""
    outdir.mkdir(parents=True, exist_ok=True)
    sec = _split_sections(draft)
    (outdir / "concept.md").write_text(sec.get("CONCEPT", "(없음)") + "\n", encoding="utf-8")
    (outdir / "gdd.md").write_text(sec.get("GDD", "(없음)") + "\n", encoding="utf-8")
    (outdir / "ambiguity_review.json").write_text(
        json.dumps({"reviews": reviews, "aggregated": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (outdir / "contract.json").write_text(
        json.dumps({"data_contract": packet.get("data_contract", {}),
                    "interface_contract": packet.get("interface_contract", {})},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "acceptance_tests.json").write_text(
        json.dumps(packet.get("acceptance_tests", []), ensure_ascii=False, indent=2),
        encoding="utf-8")

    n_block = len(issues.get("BLOCKING_questions", []))
    decisions = packet.get("decisions", [])
    assumed = packet.get("assumed", [])
    deferred = packet.get("deferred", [])
    q = ["# 08_questions — 질문 처리 (§6 분류)", "",
         f"## 해소된 결정(decisions) {len(decisions)}", *[f"- {d}" for d in decisions], "",
         f"## ASSUMED(가정 고정) {len(assumed)}", *[f"- {a}" for a in assumed], "",
         f"## DEFERRED(후속 미룸) {len(deferred)}", *[f"- {d}" for d in deferred]]
    (outdir / "questions.md").write_text("\n".join(q) + "\n", encoding="utf-8")

    # BLOCKING은 synthesis가 decisions/assumed/deferred로 흡수해야 0이 된다.
    resolved = bool(decisions or assumed or deferred)
    frozen = resolved
    status = ["# STATUS", "",
              f"- 아이디어: {idea}",
              f"- 리뷰어가 올린 BLOCKING 원본: {n_block}",
              f"- 흡수: decisions {len(decisions)} / assumed {len(assumed)} / deferred {len(deferred)}",
              f"- 미해소 BLOCKING: {0 if resolved else n_block}",
              f"- interface_contract 파일 수: {len(packet.get('interface_contract', {}).get('files', []))}",
              f"- acceptance_tests 수: {len(packet.get('acceptance_tests', []))}",
              "",
              f"CONTRACT_STATUS: {'FROZEN' if frozen else 'OPEN (BLOCKING 미해소)'}"]
    (outdir / "STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")
    return {"frozen": frozen, "blocking_original": n_block,
            "decisions": len(decisions), "assumed": len(assumed), "deferred": len(deferred),
            "interface_files": len(packet.get("interface_contract", {}).get("files", [])),
            "acceptance_tests": len(packet.get("acceptance_tests", []))}


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

    def synth(self, idea, draft, issues):
        return self.fx["synthesis"]


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

    def synth(self, idea, draft, issues):
        text = self._one(_SYNTHESIS_PROMPT.format(
            draft=draft, issues=json.dumps(issues, ensure_ascii=False)))
        return _extract_json(text)


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
    ap.add_argument("--synthesize", action="store_true",
                    help="A/B/C 측정 대신 전체 Planning 단계(초안→리뷰10→synthesis→계약 패킷)")
    ap.add_argument("--out", default=None, help="패킷 출력 폴더(기본 studio/planning_packet)")
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
        caller = FakeCaller(fx)
        api_calls = 0
    elif args.idea:
        caller = RealCaller()
        idea = args.idea
        api_calls = None  # 실호출(키 씀) — 정확 집계는 향후 ledger 연동
    else:
        ap.error("--replay 또는 --idea 중 하나 필요")

    if args.synthesize:
        outdir = Path(args.out) if args.out else (HERE / "planning_packet")
        draft, reviews, issues, packet = run_synthesis(idea, caller)
        st = _write_packet(idea, draft, reviews, issues, packet, outdir)
        print(f"[SYNTHESIS] idea={idea!r} api_calls={api_calls if not args.replay else 0}")
        print(f"  BLOCKING 원본 {st['blocking_original']} → 흡수 "
              f"decisions {st['decisions']}/assumed {st['assumed']}/deferred {st['deferred']}")
        print(f"  interface 파일 {st['interface_files']}, acceptance {st['acceptance_tests']}")
        print(f"  CONTRACT_STATUS: {'FROZEN' if st['frozen'] else 'OPEN'}  → {outdir}")
        return 0 if st["frozen"] else 1

    draft, results = run(idea, arms, caller)
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
