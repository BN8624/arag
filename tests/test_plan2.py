"""PLAN2 파생 레이어 테스트 (콜0): 라벨 5종 + 점수 _auto + fingerprint."""

import plan2


def _row(limit="MODEL_LIMIT", artifact=0, quality="junk"):
    return {"ok": False, "limit_type": limit,
            "artifact_score": artifact, "quality": quality}


def test_label_pass():
    e = {"ok": True, "score": {"passed": 5, "total": 5}}
    assert plan2.run_label(e, {"ok": True}) == "PASS"


def test_label_infra():
    assert plan2.run_label({"ok": False}, _row(limit="INFRA_LIMIT")) == "INFRA_FAIL"


def test_label_harness_spec_and_loop():
    assert plan2.run_label({"ok": False}, _row(limit="SPEC_LIMIT")) == "HARNESS_FAIL"
    assert plan2.run_label({"ok": False}, _row(limit="LOOP_LIMIT")) == "HARNESS_FAIL"


def test_label_partial_useful_vs_model_fail():
    # MODEL_LIMIT인데 관측가능한 좋은 실패 → PARTIAL_USEFUL
    assert plan2.run_label({"ok": False},
                           _row(artifact=4, quality="good")) == "PARTIAL_USEFUL"
    # 관측 안 되는 실패 → MODEL_FAIL
    assert plan2.run_label({"ok": False},
                           _row(artifact=1, quality="junk")) == "MODEL_FAIL"


def test_prototype_score_auto():
    full = {"ok": True, "score": {"passed": 5, "total": 5}}
    partial = {"ok": True, "score": {"passed": 3, "total": 5}}
    some = {"ok": False, "score": {"passed": 2, "total": 5}}
    nothing = {"ok": False, "score": {"passed": 0, "total": 0}}
    assert plan2.prototype_score_auto(full, {"ok": True}) == 5
    assert plan2.prototype_score_auto(partial, {"ok": True}) == 3
    assert plan2.prototype_score_auto(some, _row()) == 2
    assert plan2.prototype_score_auto(nothing, _row(quality="junk")) == 0


def test_failure_usefulness_auto():
    # 성공 런은 0, 실패 런은 artifact_score 재사용
    assert plan2.failure_usefulness_auto({"ok": True}, {"ok": True}) == 0
    assert plan2.failure_usefulness_auto({"ok": False},
                                         _row(artifact=4, quality="good")) == 4


def test_fingerprint_and_record():
    e = {"run": "r1", "ok": True, "score": {"passed": 5, "total": 5},
         "prompt_version": "p2-prompt-v1", "mode": "cold", "notes_enabled": False,
         "task_id": "T-000001", "level": 1, "critique_rounds": 0, "cost_usd": 0.02}
    fp = plan2.protocol_fingerprint(e)
    assert fp["prompt_version"] == "p2-prompt-v1"
    assert fp["card_pool_version"] == plan2.CARD_POOL_VERSION
    assert fp["notes_mode"] == "cold"
    assert fp["repair_budget"] == 3
    rec = plan2.build_record(e)  # run_dir 없이도 동작
    assert rec["final_label"] == "PASS"
    assert rec["mode"] == "cold"
    assert rec["prototype_score_auto"] == 5
    assert rec["prototype_score_user"] is None
    assert rec["human_audit_status"] == "pending"
    assert rec["protocol_version"] == "p2.0"
