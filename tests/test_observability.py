"""observability(관측 0단계) 테스트 — limit_type 분류 + artifact_score + 요약."""

import json

import observability as obs


def _mk_run(tmp_path, name, events=(), design=False, calls=False):
    d = tmp_path / name
    d.mkdir(parents=True)
    if events:
        (d / "events.jsonl").write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in events),
            encoding="utf-8")
    if design:
        (d / "design.json").write_text(json.dumps(
            {"files": [{"path": "main.py"}], "entrypoint": "main.py"}),
            encoding="utf-8")
    if calls:
        (d / "llm_calls.jsonl").write_text("{}", encoding="utf-8")
    return d


def test_success_run_has_no_limit_type(tmp_path):
    d = _mk_run(tmp_path, "r1")
    row = obs.classify_run(d, {"ok": True, "status": "OK"})
    assert row["ok"] is True
    assert "limit_type" not in row


def test_infra_failure_classified(tmp_path):
    d = _mk_run(tmp_path, "r1")
    row = obs.classify_run(d, {
        "ok": False,
        "status": "ERROR: API call failed after 4 retries: 500 INTERNAL."})
    assert row["limit_type"] == "INFRA_LIMIT"
    assert row["failure_class"] == "api-or-network"


def test_spec_failure_from_arbitration(tmp_path):
    d = _mk_run(tmp_path, "r1", events=[
        {"event": "arbitration", "blame": "test", "instruction": "relax"},
        {"event": "no-progress", "layer": "exec"},  # 스펙이 우선
    ])
    row = obs.classify_run(d, {"ok": False, "status": "ABORTED: gates"})
    assert row["limit_type"] == "SPEC_LIMIT"


def test_model_failure_no_progress(tmp_path):
    d = _mk_run(tmp_path, "r1", events=[
        {"event": "static-issues", "issues": [{"file": "a.py"}]},
        {"event": "no-progress", "layer": "static"},
    ])
    row = obs.classify_run(d, {"ok": False, "status": "ABORTED: gates"})
    assert row["limit_type"] == "MODEL_LIMIT"
    assert row["failure_class"] == "no-progress:static"


def test_improve_plan_failure_stays_unknown(tmp_path):
    # 모델 출력 불량일 수도, 프롬프트 비대(루프)일 수도 — 단정하지 않는다
    d = _mk_run(tmp_path, "r1")
    row = obs.classify_run(d, {
        "ok": False, "status": "ABORTED: --improve: 31B returned no usable plan"})
    assert row["limit_type"] == "UNKNOWN"
    assert row["quality"] in ("bad", "junk")


def test_artifact_score_full_marks(tmp_path):
    d = _mk_run(tmp_path, "r1", design=True, calls=True, events=[
        {"event": "static-issues", "issues": [{"file": "a.py", "line": 3}]},
        {"event": "no-progress", "layer": "static"},
        {"event": "lesson-recorded", "lesson": "x", "keywords": ["a"]},
    ])
    row = obs.classify_run(d, {"ok": False, "status": "ABORTED: gates"})
    assert row["artifact_score"] == 5
    assert row["quality"] == "good"
    assert set(row["earned"]) == {"design-valid", "failure-located",
                                  "taxonomy-mapped", "lesson-converted",
                                  "replayable"}


def test_artifact_score_junk(tmp_path):
    # 흔적 없는 실패 = junk (설계도 이벤트도 녹음도 없음, 원인 미분류)
    d = _mk_run(tmp_path, "r1")
    row = obs.classify_run(d, {"ok": False, "status": "???"})
    assert row["limit_type"] == "UNKNOWN"
    assert row["artifact_score"] == 0
    assert row["quality"] == "junk"


def test_summary_metrics(tmp_path):
    rows = [
        {"run": "a", "ok": True, "cost_usd": 0.02},
        {"run": "b", "ok": False, "cost_usd": 0.01,
         "limit_type": "INFRA_LIMIT", "failure_class": "api-or-network",
         "artifact_score": 4, "earned": [], "quality": "good"},
        {"run": "c", "ok": False, "cost_usd": 0.01,
         "limit_type": "UNKNOWN", "failure_class": "unclassified",
         "artifact_score": 0, "earned": [], "quality": "junk"},
    ]
    s = obs.summary(rows)
    assert s["ok"] == 1 and s["fails"] == 2
    assert s["by_limit"]["INFRA_LIMIT"] == 1
    assert s["by_quality"]["junk"] == 1
    assert s["junk_rate"] == 0.5
    # useful = 성공 1 + good 실패 1 = 2, 비용 0.04 -> 부산물당 0.02
    assert s["useful_artifacts"] == 2
    assert s["cost_per_useful_artifact"] == 0.02
