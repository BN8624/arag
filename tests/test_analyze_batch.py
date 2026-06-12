"""analyze_batch의 컨텍스트 계측 테스트 (콜 0, 합성 녹음)."""

import json

from analyze_batch import _phase_of_call, context_report


def test_phase_of_call_classification():
    assert _phase_of_call("You are the architect of a small multi-file "
                          "Python CLI prototype.") == "설계"
    assert _phase_of_call("You are implementing ONE file of a multi-file") == "구현"
    assert _phase_of_call("A multi-file Python project failed automated "
                          "checks.") == "수리(fix)"
    assert _phase_of_call("You are the examiner for a small") == "시험지/중재"
    assert _phase_of_call("완전히 모르는 머리") == "기타"


def _make_run(runs_dir, name, calls):
    d = runs_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "llm_calls.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in calls),
        encoding="utf-8")


def test_context_report_phases_and_outcome_split(tmp_path):
    runs = tmp_path / "runs"
    _make_run(runs, "ok-run", [
        {"role": "critic", "prompt_chars": 9000,
         "prompt_head": "You are the architect of a small multi-file ..."},
        {"role": "generator", "prompt_chars": 5000,
         "prompt_head": "You are implementing ONE file of a multi-file ..."},
    ])
    _make_run(runs, "fail-run", [
        {"role": "generator", "prompt_chars": 15000,
         "prompt_head": "A multi-file Python project failed automated checks."},
    ])
    entries = [
        {"run": "ok-run", "ok": True},
        {"run": "fail-run", "ok": False},
    ]
    text = "\n".join(context_report(entries, runs))
    assert "설계" in text and "구현" in text and "수리(fix)" in text
    assert "성공 런 평균 5,000자" in text
    assert "실패 런 평균 15,000자" in text


def test_context_report_without_recordings(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    assert context_report([{"run": "x", "ok": True}], runs) == ["녹음 있는 런 없음"]
