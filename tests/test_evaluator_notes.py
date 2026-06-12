"""평가자 노트(31B 교정 자료) 수집 테스트 — 전부 콜 0, 합성 런 디렉토리."""

import json

import evaluator_notes as en


def _make_run(runs_dir, name, *, lgtm=False, review=None):
    d = runs_dir / name
    d.mkdir(parents=True, exist_ok=True)
    if lgtm:
        (d / "events.jsonl").write_text(
            json.dumps({"t": "x", "event": "critique-lgtm"}) + "\n",
            encoding="utf-8")
    if review is not None:
        (d / "auto_review.json").write_text(
            json.dumps(review, ensure_ascii=False), encoding="utf-8")


def _write_index(runs_dir, entries):
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "index.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def test_false_lgtm_and_perfect_gap(tmp_path):
    runs = tmp_path / "runs"
    _write_index(runs, [
        {"run": "r1", "t": "t1", "ok": True, "idea": "todo cli",
         "status": "OK", "score": {"passed": 3, "total": 3}},
    ])
    _make_run(runs, "r1", lgtm=True,
              review={"verdict": "SUGGEST", "feedback": "합계 요약이 없다"})
    mistakes = en.harvest(runs, path=tmp_path / "em.json")
    kinds = {m["kind"] for m in mistakes}
    # LGTM을 줬고 + 만점인데 총평이 지적 → 두 사례 모두 수집
    assert kinds == {"false-lgtm", "perfect-but-gap"}
    assert all(m["run"] == "r1" for m in mistakes)


def test_partial_lgtm_detected(tmp_path):
    runs = tmp_path / "runs"
    _write_index(runs, [
        {"run": "r1", "t": "t1", "ok": True, "idea": "todo cli",
         "status": "OK (partial - some acceptance tests still failing)",
         "score": {"passed": 4, "total": 5}, "failed_criteria": ["기준 X"]},
    ])
    _make_run(runs, "r1", lgtm=True)  # 총평 없음, 비평만 LGTM
    mistakes = en.harvest(runs, path=tmp_path / "em.json")
    assert [m["kind"] for m in mistakes] == ["partial-lgtm"]
    assert "기준 X" in mistakes[0]["detail"]


def test_repeat_review_needs_feedback_overlap(tmp_path):
    runs = tmp_path / "runs"
    _write_index(runs, [
        {"run": "r1", "t": "t1", "ok": True, "idea": "todo cli", "status": "OK",
         "score": {"passed": 3, "total": 3}},
        {"run": "r2", "t": "t2", "ok": True, "idea": "todo cli", "status": "OK",
         "score": {"passed": 4, "total": 4}, "improved_from": "r1"},
    ])
    same = "출력에 합계 요약이 없어 사용자가 결과를 한눈에 보기 어렵다"
    _make_run(runs, "r1", review={"verdict": "SUGGEST", "feedback": same})
    _make_run(runs, "r2", review={"verdict": "SUGGEST", "feedback": same})
    mistakes = en.harvest(runs, path=tmp_path / "em.json")
    kinds = [m["kind"] for m in mistakes]
    assert "repeat-review" in kinds  # 같은 지적 반복 → 수집

    # 다른 지적이면 repeat-review 아님
    _make_run(runs, "r2", review={"verdict": "SUGGEST",
                                  "feedback": "에러 메시지가 영어라 불친절하다"})
    mistakes = en.harvest(runs, path=tmp_path / "em.json")
    assert "repeat-review" not in [m["kind"] for m in mistakes]


def test_no_mistakes_on_clean_runs(tmp_path):
    runs = tmp_path / "runs"
    _write_index(runs, [
        {"run": "r1", "t": "t1", "ok": True, "idea": "todo", "status": "OK",
         "score": {"passed": 3, "total": 3}},
    ])
    _make_run(runs, "r1", lgtm=True,
              review={"verdict": "NOCHANGE", "feedback": ""})
    assert en.harvest(runs, path=tmp_path / "em.json") == []


def test_harvest_is_idempotent_full_rebuild(tmp_path):
    runs = tmp_path / "runs"
    _write_index(runs, [
        {"run": "r1", "t": "t1", "ok": True, "idea": "todo", "status": "OK",
         "score": {"passed": 2, "total": 2}},
    ])
    _make_run(runs, "r1", lgtm=True,
              review={"verdict": "SUGGEST", "feedback": "지적"})
    out = tmp_path / "em.json"
    first = en.harvest(runs, path=out)
    second = en.harvest(runs, path=out)
    assert first == second  # 두 번 돌려도 중복 누적 없음
    assert json.loads(out.read_text(encoding="utf-8")) == second


def test_promotion_candidates_threshold():
    mistakes = ([{"kind": "false-lgtm"}] * 3
                + [{"kind": "perfect-but-gap"}] * 2)
    cands = en.promotion_candidates(mistakes, min_count=3)
    assert cands == [(3, "false-lgtm")]  # 3회 미만 유형은 후보 아님
