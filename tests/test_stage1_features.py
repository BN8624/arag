"""1단계 신기능 테스트: 요구사항 커버리지 / 테스트 출제 / README / pyproject."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design, write_project

from design_validator import validate_design
from gates import run_static_gate
from orchestrator import Orchestrator
from prompts import extract_markdown


# ------------------------------------------------- requirements coverage

def test_requirements_missing_rejected():
    d = make_design()
    del d["requirements"]
    assert any("requirements" in e for e in validate_design(d))


def test_requirements_empty_rejected():
    d = make_design()
    d["requirements"] = []
    assert any("requirements" in e for e in validate_design(d))


def test_requirement_without_coverage_rejected():
    d = make_design()
    d["requirements"] = [{"text": "user can add an item", "covered_by": []}]
    assert any("covered_by" in e for e in validate_design(d))


def test_requirement_with_bad_index_rejected():
    d = make_design()
    d["requirements"] = [{"text": "user can add an item", "covered_by": [7]}]
    assert any("invalid index" in e for e in validate_design(d))


def test_valid_requirements_accepted():
    assert validate_design(make_design()) == []


# ------------------------------------------------- static gate vs tests

def test_static_gate_skips_test_files(tmp_path):
    # 테스트 파일은 pytest를 import하고 아무도 import 안 해도 게이트가 안 잡아야 함
    test_code = ("import pytest\nfrom core import add_item\n\n\n"
                 "def test_add(tmp_path):\n"
                 "    item = add_item(str(tmp_path / 'db.json'), 'x')\n"
                 "    assert item['text'] == 'x'\n")
    write_project(tmp_path, {"core.py": GOOD_CORE, "main.py": GOOD_MAIN,
                             "test_acceptance.py": test_code})
    issues = run_static_gate(tmp_path, make_design())
    assert issues == []


# ------------------------------------------------- markdown extraction

def test_extract_markdown_fenced():
    text = "Here you go:\n```markdown\n# Tool\n\nUsage...\n```\nthanks"
    assert extract_markdown(text) == "# Tool\n\nUsage...\n"


def test_extract_markdown_bare_heading():
    assert extract_markdown("# Tool\n\nUsage").startswith("# Tool")


def test_extract_markdown_garbage_returns_none():
    assert extract_markdown("sorry, I cannot do that") is None


# ------------------------------------------------- orchestrator wiring

class MockLLM:
    def __init__(self, critic, generator):
        self.queues = {"critic": list(critic), "generator": list(generator)}
        self.call_count = 0
        self.max_calls = None

    def generate(self, role, prompt, temperature=None):
        self.call_count += 1
        assert self.queues[role], f"unexpected extra {role} call:\n{prompt[:200]}"
        return self.queues[role].pop(0)


def fenced(code):
    return f"```python\n{code}```"


def test_happy_path_writes_pyproject(tmp_path):
    llm = MockLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is True
    pyproject = tmp_path / "run" / "workspace" / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text(encoding="utf-8")
    assert 'name = "todo-cli"' in content
    assert '"main", "core"' in content or '"core", "main"' in content
    # 진입점에 main()이 있으므로 실행 스크립트도 등록돼야 함
    assert 'todo-cli = "main:main"' in content


def test_report_lists_requirements(tmp_path):
    llm = MockLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is True
    report = (tmp_path / "run" / "REPORT.md").read_text(encoding="utf-8")
    assert "user can add a todo item" in report


def test_salvage_delivers_last_passing_build(tmp_path):
    """비평 도중 예산 소진 -> 마지막 통과 스냅샷을 결과물로 내고 OK."""
    from llm import CallBudgetExceeded

    class BudgetLLM(MockLLM):
        def generate(self, role, prompt, temperature=None):
            if role == "critic" and not self.queues["critic"]:
                raise CallBudgetExceeded("call budget exhausted")
            return super().generate(role, prompt, temperature)

    llm = BudgetLLM(
        critic=[json.dumps(make_design())],  # 비평 콜에서 예산 초과 발생
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is True  # FAIL이 아니라 부분 성공
    report = (tmp_path / "run" / "REPORT.md").read_text(encoding="utf-8")
    assert "salvaged" in report
    assert (tmp_path / "run" / "workspace" / "main.py").exists()


def test_scoreboard_regression_rolls_back(tmp_path, monkeypatch):
    """수정본이 게이트는 통과해도 채점표가 후퇴하면 rollback."""
    import orchestrator as om
    monkeypatch.setattr(om, "run_exec_gate", lambda *a, **k: ([], "ok"))

    def score(passed):
        return [{"criterion": "c1", "command": "x", "passed": passed,
                 "detail": "ok" if passed else "regressed", "output_tail": ""}]

    scores = iter([score(True),    # 최초 빌드: 1/1
                   score(False),   # 비평 수정 후: 0/1 -> 후퇴
                   score(True)])   # rollback 후 재채점: 1/1
    monkeypatch.setattr(om, "run_criteria_checks", lambda *a, **k: next(scores))

    revised = GOOD_MAIN.replace("usage: python main.py add <text>", "USAGE???")
    critique = json.dumps({"verdict": "revise",
                           "files": [{"path": "main.py", "issues": ["x"]}]})
    design = make_design()
    design["criteria_checks"] = [{"criterion": "c1",
                                  "command": "python main.py add x",
                                  "expect_substring": "x"}]
    llm = MockLLM(
        # 설계 -> 테스트 출제 실패 2회(건너뜀) -> 비평 1회
        critic=[json.dumps(design), "no code here", "still no code",
                critique],
        # 구현 2개 -> 비평 수정본 -> README
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN), fenced(revised),
                   "```markdown\n# todo\n```"],
    )
    orch = Orchestrator(llm, tmp_path / "run", critique_rounds=2,
                        skip_exec=False)
    assert orch.run("tiny todo cli") is True
    text = (tmp_path / "run" / "workspace" / "main.py").read_text(encoding="utf-8")
    assert "USAGE???" not in text  # 후퇴한 수정본은 rollback으로 사라져야 함
    events = (tmp_path / "run" / "events.jsonl").read_text(encoding="utf-8")
    assert "score-regression" in events


def test_critique_prompt_receives_idea(tmp_path):
    """비평 프롬프트에 원 아이디어가 들어가는지 (커버리지 2차 방어선)."""
    captured = {}

    class SpyLLM(MockLLM):
        def generate(self, role, prompt, temperature=None):
            if role == "critic" and "ORIGINAL IDEA" in prompt:
                captured["prompt"] = prompt
            return super().generate(role, prompt, temperature)

    llm = SpyLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("아주 특별한 할일 관리 도구") is True
    assert "아주 특별한 할일 관리 도구" in captured["prompt"]
