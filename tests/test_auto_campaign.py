"""무인 순차 캠페인 테스트 (콜0): run_phase + wait_for_whole."""

import json

import auto_campaign


def test_run_phase_resume_and_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_campaign, "LEDGER", tmp_path / "auto.jsonl")
    calls = []

    def runner(idea, env_models, extra, resume_dir=None, task_id=None):
        calls.append({"idea": idea, "env": env_models, "extra": extra,
                      "resume": resume_dir, "task_id": task_id})
        return 0

    dirs = {"T-1": "run_a", "T-2": "run_b"}
    cards = {"T-1": {"goal": "goal1"}, "T-2": {"goal": "goal2"}}

    # resume 페이즈: resume_dir 채워지고 task_id 없음
    st = auto_campaign.run_phase("p-resume", {"GENERATOR_MODEL": "m26"},
                                 ["--mode", "cold"], True, dirs, cards, runner)
    assert st == {"ok": 2, "fail": 0}
    assert calls[0]["resume"] == "run_a" and calls[0]["task_id"] is None
    assert calls[0]["extra"] == ["--mode", "cold"]

    # fresh 페이즈: resume 없음, task_id 채워짐
    calls.clear()
    auto_campaign.run_phase("p-fresh", {"GENERATOR_MODEL": "m26"},
                            ["--mode", "cold"], False, dirs, cards, runner)
    assert calls[0]["resume"] is None and calls[0]["task_id"] == "T-1"

    # 장부 기록 확인
    lines = [json.loads(x) for x in
             (tmp_path / "auto.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {l["phase"] for l in lines} == {"p-resume", "p-fresh"}


def test_run_phase_continues_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_campaign, "LEDGER", tmp_path / "a.jsonl")
    st = auto_campaign.run_phase("p", {}, [], False,
                                 {}, {"T-1": {"goal": "g"}, "T-2": {"goal": "g"}},
                                 lambda *a, **k: 1)
    assert st == {"ok": 0, "fail": 2}  # 실패해도 둘 다 시도


def test_wait_for_whole(tmp_path, monkeypatch):
    led = tmp_path / "whole.jsonl"
    monkeypatch.setattr(auto_campaign, "WHOLE_LEDGER", led)
    led.write_text("\n".join(["{}"] * 6), encoding="utf-8")
    clock = {"t": 0.0}
    assert auto_campaign.wait_for_whole(
        target=6, now=lambda: clock["t"],
        sleep=lambda s: clock.__setitem__("t", clock["t"] + s)) is True


def test_wait_for_whole_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_campaign, "WHOLE_LEDGER", tmp_path / "none.jsonl")
    clock = {"t": 0.0}
    assert auto_campaign.wait_for_whole(
        target=6, now=lambda: clock["t"],
        sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
        max_wait=100) is False
