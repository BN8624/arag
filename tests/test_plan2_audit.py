"""PLAN2 폰 감사 화면 렌더 테스트 (콜0)."""

import json

import plan2_audit


def _make_run(tmp_path, *, ok, board):
    run_dir = tmp_path / "run1"
    ws = run_dir / "workspace"
    ws.mkdir(parents=True)
    (ws / "main.py").write_text("print('hi')", encoding="utf-8")
    (ws / "game.py").write_text("def play(): ...", encoding="utf-8")
    (run_dir / "design.json").write_text(
        json.dumps({"files": [{"path": "main.py"}, {"path": "game.py"}]}),
        encoding="utf-8")
    (run_dir / "llm_calls.jsonl").write_text("{}\n", encoding="utf-8")
    events = [
        {"t": "2026-06-14T01:00:00", "event": "phase", "name": "design"},
        {"t": "2026-06-14T01:05:00", "event": "scoreboard",
         "passed": sum(r["passed"] for r in board), "total": len(board),
         "results": board},
    ]
    if not ok:
        events.append({"t": "2026-06-14T01:06:00", "event": "static-issues"})
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return run_dir


def test_render_pass(tmp_path):
    board = [{"criterion": "스트라이크 계산", "passed": True, "detail": "ok"},
             {"criterion": "잘못된 입력 처리", "passed": True, "detail": "ok"}]
    run_dir = _make_run(tmp_path, ok=True, board=board)
    entry = {"run": "run1", "task_id": "T-000001", "idea": "숫자 야구",
             "ok": True, "status": "OK", "mode": "cold", "notes_enabled": False,
             "score": {"passed": 2, "total": 2}, "cost_usd": 0.01,
             "critique_rounds": 0, "prompt_version": "p2-prompt-v1"}
    out = plan2_audit.render_audit(run_dir, entry)
    assert "[T-000001] 숫자 야구 / cold" in out
    assert "결과: PASS" in out
    assert "- main.py" in out and "- game.py" in out
    assert "- 스트라이크 계산" in out
    assert "[ ] 판정 맞음" in out
    assert "prototype 5/5" in out


def test_render_fail_with_detail(tmp_path):
    board = [{"criterion": "전투 종료", "passed": False,
              "detail": "HP 0 이하인데 계속 공격"}]
    run_dir = _make_run(tmp_path, ok=False, board=board)
    entry = {"run": "run1", "task_id": "T-000006", "idea": "자동 전투",
             "ok": False, "status": "ABORTED: x", "mode": "warm",
             "notes_enabled": True, "score": {"passed": 0, "total": 1},
             "cost_usd": 0.02, "critique_rounds": 1,
             "prompt_version": "p2-prompt-v1"}
    out = plan2_audit.render_audit(run_dir, entry)
    assert "결과:" in out
    assert "전투 종료 (HP 0 이하인데 계속 공격)" in out
    assert "실패 위치 특정 가능" in out  # static-issues → failure-located
