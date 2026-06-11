"""테스트 책임 경로 + 몽키패치 게이트 + tests_prompt 규칙 테스트."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design, write_project

from gates import run_static_gate
from orchestrator import Orchestrator
import prompts
from test_orchestrator_mock import MockLLM, fenced


# ------------------------------------------------------------ monkeypatch gate

def test_monkeypatch_stdlib_flagged(tmp_path):
    write_project(tmp_path, {
        "main.py": ("import json\n"
                    "import core\n"
                    "json.load = lambda fp: {}\n"
                    "if __name__ == '__main__':\n"
                    "    core.run(json.load)\n"),
        "core.py": "def run(loader):\n    return loader\n",
    })
    issues = run_static_gate(tmp_path)
    kinds = {i["kind"] for i in issues}
    assert "monkeypatch" in kinds
    msg = next(i for i in issues if i["kind"] == "monkeypatch")["message"]
    assert "json.load" in msg


def test_monkeypatch_local_module_flagged(tmp_path):
    # 실전 관측: main.py가 processor.process_expenses를 패치해 비평까지 살아감
    write_project(tmp_path, {
        "main.py": ("import core\n"
                    "core.run = lambda: 'patched'\n"
                    "if __name__ == '__main__':\n"
                    "    print(core.run())\n"),
        "core.py": "def run():\n    return 'ok'\n",
    })
    issues = run_static_gate(tmp_path)
    assert "monkeypatch" in {i["kind"] for i in issues}


def test_monkeypatch_sys_stdout_exempt(tmp_path):
    write_project(tmp_path, {
        "main.py": ("import io\n"
                    "import sys\n"
                    "import core\n"
                    "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n"
                    "if __name__ == '__main__':\n"
                    "    print(core.run())\n"),
        "core.py": "def run():\n    return 'ok'\n",
    })
    issues = run_static_gate(tmp_path)
    assert "monkeypatch" not in {i["kind"] for i in issues}


def test_normal_attribute_assign_not_flagged(tmp_path):
    write_project(tmp_path, {
        "main.py": ("import core\n"
                    "obj = core.Thing()\n"
                    "obj.value = 3\n"
                    "if __name__ == '__main__':\n"
                    "    print(obj.value)\n"),
        "core.py": "class Thing:\n    def __init__(self):\n        self.value = 0\n",
    })
    issues = run_static_gate(tmp_path)
    assert "monkeypatch" not in {i["kind"] for i in issues}


# ------------------------------------------------------------ prompts

def test_tests_prompt_has_clirunner_rules():
    p = prompts.tests_prompt(make_design())
    assert "CliRunner with NO arguments" in p
    assert "isolated_filesystem" in p


def test_tests_fix_prompt_contains_evidence():
    p = prompts.tests_fix_prompt(make_design(), "def test_x(): pass",
                         "E   TypeError: unexpected keyword argument")
    assert "def test_x(): pass" in p
    assert "unexpected keyword argument" in p
    assert "Fix ONLY the broken test code" in p


# ------------------------------------------------------------ blame heuristic

BROKEN_TEST_LOG = """\
=================================== FAILURES ===================================
______________________________ test_cli_live_no_key ___________________________
test_acceptance.py:106: in test_cli_live_no_key
    result = runner.invoke(main.main, [
/deps/click/testing.py:648: in invoke
    prog_name = self.get_default_prog_name(cli)
/deps/click/testing.py:351: in get_default_prog_name
    return cli.name or "root"
E   AttributeError: 'function' object has no attribute 'name'
______________________________ test_cli_init_samples __________________________
test_acceptance.py:132: in test_cli_init_samples
    runner = CliRunner(current_working_dir=tmp_path)
E   TypeError: CliRunner.__init__() got an unexpected keyword argument
"""

CODE_FAIL_LOG = """\
=================================== FAILURES ===================================
______________________________ test_add_item __________________________________
test_acceptance.py:20: in test_add_item
    assert item["text"] == "buy milk"
E   AssertionError: assert 'milk' == 'buy milk'
"""

CODE_CRASH_LOG = """\
=================================== FAILURES ===================================
______________________________ test_add_item __________________________________
test_acceptance.py:20: in test_add_item
    item = core.add_item(str(p), "buy milk")
core.py:7: in add_item
    items.append(item)
E   TypeError: 'NoneType' object has no attribute 'append'
"""


def _orch(tmp_path):
    llm = MockLLM(critic=[], generator=[])
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    orch.design = make_design()
    return orch


def test_blame_detects_test_bug(tmp_path):
    assert _orch(tmp_path)._tests_look_broken(BROKEN_TEST_LOG) is True


def test_blame_ignores_assertion_failure(tmp_path):
    assert _orch(tmp_path)._tests_look_broken(CODE_FAIL_LOG) is False


def test_blame_ignores_project_crash(tmp_path):
    assert _orch(tmp_path)._tests_look_broken(CODE_CRASH_LOG) is False


def test_blame_mixed_prefers_code(tmp_path):
    # 테스트 버그와 프로젝트 에러가 섞이면 코드 쪽 책임 -> 재생성 안 함
    mixed = BROKEN_TEST_LOG + CODE_CRASH_LOG
    assert _orch(tmp_path)._tests_look_broken(mixed) is False


def test_regenerate_tests_writes_fixed_file(tmp_path):
    fixed = "def test_ok():\n    assert True\n"
    llm = MockLLM(critic=[fenced(fixed)], generator=[])
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    orch.design = make_design()
    test_path = orch.workspace / "test_acceptance.py"
    test_path.write_text("def test_broken():\n    CliRunner(bad=1)\n",
                         encoding="utf-8")
    orch.last_exec_log = BROKEN_TEST_LOG
    orch._regenerate_tests()
    assert test_path.read_text(encoding="utf-8") == fixed


def test_regenerate_keeps_old_on_syntax_error(tmp_path):
    llm = MockLLM(critic=[fenced("def broken(:\n")], generator=[])
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    orch.design = make_design()
    original = "def test_broken():\n    CliRunner(bad=1)\n"
    test_path = orch.workspace / "test_acceptance.py"
    test_path.write_text(original, encoding="utf-8")
    orch.last_exec_log = BROKEN_TEST_LOG
    orch._regenerate_tests()
    assert test_path.read_text(encoding="utf-8") == original
