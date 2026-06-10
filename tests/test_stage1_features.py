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
