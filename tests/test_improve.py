"""1층: --improve 모드 테스트 (모의 LLM, Docker 불필요)."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design

from orchestrator import Orchestrator
from test_orchestrator_mock import MockLLM, fenced


def _base_design():
    """conftest 설계 + 채점표 커맨드 2개 (improve의 회귀 방지선 역할)."""
    d = make_design()
    d["criteria_checks"] = [
        {"criterion": "adding an item prints confirmation",
         "command": 'python main.py add "buy milk"',
         "expect_substring": "buy milk"},
        {"criterion": "usage shown without args",
         "command": "python main.py",
         "expect_substring": "usage", "expect_exit_code": 1},
    ]
    return d


def _make_prev_run(tmp_path, scoreboard_passed=2):
    """개선 대상이 될 이전 성공 런 디렉토리를 만든다."""
    prev = tmp_path / "runs" / "prev-run"
    ws = prev / "workspace"
    ws.mkdir(parents=True)
    (ws / "core.py").write_text(GOOD_CORE, encoding="utf-8")
    (ws / "main.py").write_text(GOOD_MAIN, encoding="utf-8")
    (prev / "design.json").write_text(json.dumps(_base_design()),
                                      encoding="utf-8")
    events = [
        {"t": "x", "event": "scoreboard", "passed": scoreboard_passed,
         "total": 2, "results": [
             {"criterion": "adds item", "passed": True, "detail": "ok"},
             {"criterion": "lists items", "passed": scoreboard_passed == 2,
              "detail": "ok"}]},
    ]
    (prev / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return prev


def _improved_design():
    d = _base_design()
    d["acceptance_criteria"] = d["acceptance_criteria"] + [
        "duplicate items are rejected"]
    d["criteria_checks"] = d["criteria_checks"] + [
        {"criterion": "duplicate items are rejected",
         "command": 'python main.py add "buy milk"',
         "expect_substring": "duplicate", "expect_exit_code": 1}]
    return d


def test_nochange_exits_early(tmp_path):
    prev = _make_prev_run(tmp_path)
    llm = MockLLM(critic=["NOCHANGE"], generator=[])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    assert orch.run("tiny todo cli") is True
    report = (tmp_path / "runs" / "imp" / "REPORT.md").read_text(encoding="utf-8")
    assert "NOCHANGE" in report
    assert llm.queues["critic"] == []


def test_improve_applies_changes(tmp_path):
    prev = _make_prev_run(tmp_path)
    revised_main = GOOD_MAIN.replace("usage: python main.py add <text>",
                                     "usage: improved")
    plan = json.dumps({
        "design": _improved_design(),
        "changes": [{"path": "main.py",
                     "instructions": ["reject duplicate items"]}],
    })
    llm = MockLLM(critic=[plan, "LGTM"], generator=[fenced(revised_main)])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    assert orch.run("tiny todo cli") is True
    ws = tmp_path / "runs" / "imp" / "workspace"
    assert "usage: improved" in (ws / "main.py").read_text(encoding="utf-8")
    assert (ws / "core.py").read_text(encoding="utf-8") == GOOD_CORE  # 복사됨
    saved = json.loads((tmp_path / "runs" / "imp" / "design.json")
                       .read_text(encoding="utf-8"))
    assert len(saved["criteria_checks"]) == 3  # 기존 2 + 신규 1


def test_improve_restores_dropped_criteria(tmp_path):
    """31B가 기존 기준을 빼먹어도 강제로 되살린다 (회귀 방지선)."""
    prev = _make_prev_run(tmp_path)
    dropped = _improved_design()
    dropped["criteria_checks"] = dropped["criteria_checks"][-1:]  # 신규만 남김
    dropped["acceptance_criteria"] = dropped["acceptance_criteria"][-1:]
    plan = json.dumps({"design": dropped,
                       "changes": [{"path": "main.py", "instructions": ["x"]}]})
    llm = MockLLM(critic=[plan, "LGTM"], generator=[fenced(GOOD_MAIN)])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    assert orch.run("tiny todo cli") is True
    saved = json.loads((tmp_path / "runs" / "imp" / "design.json")
                       .read_text(encoding="utf-8"))
    commands = [c["command"] for c in saved["criteria_checks"]]
    for old in _base_design()["criteria_checks"]:
        assert old["command"] in commands  # 기존 기준 전부 생존
    assert len(saved["criteria_checks"]) == 3


def test_improve_salvages_invalid_new_checks(tmp_path):
    """신규 기준의 커맨드가 검증에 걸리면 그 기준만 떨구고 진행 (ABORT 방지).

    실관측(2026-06-12 배치): 31B가 echo 리다이렉션을 쓴 채점 커맨드를 재시도에서도
    반복해 improve가 통째로 ABORT — 멀쩡한 나머지 계획까지 버려졌다.
    """
    prev = _make_prev_run(tmp_path)
    bad = _improved_design()
    bad["acceptance_criteria"] = bad["acceptance_criteria"] + [
        "broken input file is rejected"]
    bad["criteria_checks"] = bad["criteria_checks"] + [
        {"criterion": "broken input file is rejected",
         "command": "echo '{' > bad.json && python main.py bad.json",
         "expect_substring": "error", "expect_exit_code": 1}]
    plan = json.dumps({
        "design": bad,
        "changes": [{"path": "main.py", "instructions": ["x"]}]})
    llm = MockLLM(critic=[plan, "LGTM"], generator=[fenced(GOOD_MAIN)])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    assert orch.run("tiny todo cli") is True  # ABORT가 아니라 진행
    saved = json.loads((tmp_path / "runs" / "imp" / "design.json")
                       .read_text(encoding="utf-8"))
    commands = [c["command"] for c in saved["criteria_checks"]]
    assert all("echo" not in c for c in commands)  # 불량 기준만 제거
    assert len(saved["criteria_checks"]) == 3      # 기존 2 + 유효 신규 1
    assert "broken input file is rejected" not in saved["acceptance_criteria"]
    events = (tmp_path / "runs" / "imp" / "events.jsonl").read_text(
        encoding="utf-8")
    assert "improve-criteria-salvaged" in events


def test_salvage_refuses_when_old_criteria_flagged(tmp_path):
    """기존 기준(원본 그대로)이 검증에 걸리면 구제하지 않는다.

    merge가 원본을 이미 되살린 상태이므로, 검증에 걸린 항목이 원본과
    동일하다 = 떨구면 회귀 방지선이 사라진다 → 통째로 재요청 경로로.
    """
    old = _base_design()
    same = json.loads(json.dumps(old))  # 기존 기준 그대로
    errs = ["criteria_checks[0].command: every '&&' step must start "
            "with 'python ': 'python main.py'"]
    assert Orchestrator._salvage_new_checks(old, same, errs) is None


def test_salvage_refuses_non_check_errors():
    """채점 커맨드 외 에러가 섞여 있으면 구제 불가."""
    old = _base_design()
    design = _improved_design()
    errs = ["criteria_checks[2].command: ...", "entrypoint 'x.py' is not in 'files'"]
    assert Orchestrator._salvage_new_checks(old, design, errs) is None


def test_improve_prompt_excludes_test_file(tmp_path):
    """다이어트: improve 비평 입력에 시험지(test_acceptance.py)는 안 들어간다."""
    prev = _make_prev_run(tmp_path)
    (prev / "workspace" / "test_acceptance.py").write_text(
        "def test_marker_sentinel():\n    assert True\n", encoding="utf-8")
    captured = {}

    class SpyLLM(MockLLM):
        def generate(self, role, prompt, temperature=None):
            captured.setdefault(role, []).append(prompt)
            return super().generate(role, prompt, temperature)

    llm = SpyLLM(critic=["NOCHANGE"], generator=[])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    assert orch.run("tiny todo cli") is True
    assert "test_marker_sentinel" not in captured["critic"][0]
    assert "core.py" in captured["critic"][0]  # 코드 파일은 들어감


def test_improve_new_file_implemented(tmp_path):
    """변경 계획에 새 파일이 있으면 구현 프롬프트로 생성."""
    prev = _make_prev_run(tmp_path)
    design = _improved_design()
    design["files"].append({"path": "dedup.py", "role": "duplicate detection",
                            "interfaces": [{"kind": "function", "name": "is_dup",
                                            "signature": "def is_dup(items: list, text: str) -> bool",
                                            "description": "check duplicate"}]})
    design["dependencies"]["main.py"] = ["core.py", "dedup.py"]
    design["dependencies"]["dedup.py"] = []
    new_main = GOOD_MAIN.replace(
        "from core import add_item",
        "from core import add_item\nfrom dedup import is_dup\n_ = is_dup")
    plan = json.dumps({
        "design": design,
        "changes": [
            {"path": "dedup.py", "instructions": ["implement is_dup"]},
            {"path": "main.py", "instructions": ["use is_dup"]},
        ],
    })
    dedup_code = "def is_dup(items: list, text: str) -> bool:\n    return any(i.get('text') == text for i in items)\n"
    llm = MockLLM(critic=[plan, "LGTM"],
                  generator=[fenced(dedup_code), fenced(new_main)])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    assert orch.run("tiny todo cli") is True
    ws = tmp_path / "runs" / "imp" / "workspace"
    assert (ws / "dedup.py").exists()
    assert "is_dup" in (ws / "main.py").read_text(encoding="utf-8")


def test_scoreboard_labels_regression_capability(tmp_path):
    """improve 모드 채점표는 기존 기준=[regression], 새 기준=[capability] 라벨."""
    prev = _make_prev_run(tmp_path)
    orch = Orchestrator(MockLLM(critic=[], generator=[]),
                        tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    orch._old_commands = {"old1"}
    orch._prev_score = 1
    orch.scoreboard = [
        {"criterion": "old1", "command": "c1", "passed": True, "detail": "ok"},
        {"criterion": "new1", "command": "c2", "passed": False, "detail": "boom"},
    ]
    text = orch._scoreboard_text()
    assert "[regression] old1" in text
    assert "[capability] new1" in text

    orch._record_index("아이디어", "OK")
    entries = json.loads((tmp_path / "runs" / "index.json")
                         .read_text(encoding="utf-8"))
    assert entries[-1]["score_split"] == {
        "regression": {"passed": 1, "total": 1},
        "capability": {"passed": 0, "total": 1}}
    assert "regression 1/1" in entries[-1]["improvement"]


def test_scoreboard_no_labels_outside_improve(tmp_path):
    """일반 런 채점표에는 라벨이 없다 (혼동 방지)."""
    orch = Orchestrator(MockLLM(critic=[], generator=[]),
                        tmp_path / "runs" / "r", skip_exec=True)
    orch.scoreboard = [{"criterion": "c", "command": "x",
                        "passed": True, "detail": "ok"}]
    assert "[regression]" not in orch._scoreboard_text()
    assert "[capability]" not in orch._scoreboard_text()


def test_prev_passed_reads_last_scoreboard(tmp_path):
    prev = _make_prev_run(tmp_path, scoreboard_passed=1)
    assert Orchestrator._prev_passed(prev) == 1
    assert Orchestrator._prev_passed(tmp_path / "nope") is None


def test_improvement_verdict_improved(tmp_path):
    prev = _make_prev_run(tmp_path)
    llm = MockLLM(critic=[], generator=[])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    orch._prev_score = 2
    orch._old_commands = {"old1"}
    orch.scoreboard = [
        {"criterion": "old1", "command": "python main.py old-check",
         "passed": True, "detail": "ok"},
        {"criterion": "new1", "command": "python main.py new-check",
         "passed": True, "detail": "ok"},
    ]
    v = orch._improvement_verdict()
    assert v.startswith("IMPROVED") is False or "IMPROVED" in v
    # old 1/1 (was 2) -> 회귀로 본다
    assert "REGRESSED" in v


def test_improvement_verdict_no_regression(tmp_path):
    prev = _make_prev_run(tmp_path)
    llm = MockLLM(critic=[], generator=[])
    orch = Orchestrator(llm, tmp_path / "runs" / "imp", skip_exec=True,
                        improve_from=prev)
    orch._prev_score = 1
    orch._old_commands = {"old1"}
    orch.scoreboard = [
        {"criterion": "old1", "command": "cmd-a", "passed": True, "detail": "ok"},
        {"criterion": "new1", "command": "cmd-b", "passed": True, "detail": "ok"},
    ]
    assert "IMPROVED" in orch._improvement_verdict()
