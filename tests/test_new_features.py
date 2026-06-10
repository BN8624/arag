"""신규 기능 테스트: 패키지 화이트리스트 / criteria_checks 검증 / 오답노트."""

import json

from conftest import make_design, write_project

import lessons as lessons_mod
from design_validator import validate_design
from gates import external_imports, run_static_gate

HELPER_REQUESTS = '''\
import requests


def fetch(url):
    return requests.get(url)
'''

MAIN_USES_HELPER = '''\
from helper import fetch


def main():
    print(fetch("http://example.com"))


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------- whitelist

def test_whitelisted_package_allowed(tmp_path):
    write_project(tmp_path, {"helper.py": HELPER_REQUESTS,
                             "main.py": MAIN_USES_HELPER})
    kinds = {i["kind"] for i in run_static_gate(tmp_path)}
    assert "non-stdlib-import" not in kinds


def test_unknown_package_rejected(tmp_path):
    bad = HELPER_REQUESTS.replace("requests", "leftpadx")
    write_project(tmp_path, {"helper.py": bad, "main.py": MAIN_USES_HELPER})
    kinds = {i["kind"] for i in run_static_gate(tmp_path)}
    assert "non-stdlib-import" in kinds


def test_external_imports_maps_pip_names(tmp_path):
    helper = ('import yaml\n\n\n'
              'def load(text):\n    return yaml.safe_load(text)\n')
    main = ('from helper import load\n\n\n'
            'def main():\n    print(load("x: 1"))\n\n\n'
            'if __name__ == "__main__":\n    main()\n')
    write_project(tmp_path, {"helper.py": helper, "main.py": main})
    assert external_imports(tmp_path) == {"PyYAML"}


def test_stdlib_only_project_has_no_external_imports(tmp_path):
    write_project(tmp_path, {"a.py": "import json\nprint(json.dumps({}))\n"})
    assert external_imports(tmp_path) == set()


# ---------------------------------------------------------------- checks

def test_criteria_checks_command_must_be_python():
    d = make_design()
    d["criteria_checks"] = [{"criterion": "x", "command": "echo hi",
                             "expect_substring": "hi"}]
    assert any("criteria_checks" in e for e in validate_design(d))


def test_criteria_checks_valid_command_accepted():
    d = make_design()
    d["criteria_checks"] = [{"criterion": "adds item",
                             "command": "python main.py add x",
                             "expect_substring": "x"}]
    assert not any("criteria_checks" in e for e in validate_design(d))


def test_design_without_checks_still_valid():
    assert validate_design(make_design()) == []


def test_chained_python_commands_allowed():
    d = make_design()
    d["success_signal"]["command"] = (
        "python main.py add \"x\" && python main.py add \"y\"")
    assert validate_design(d) == []
    d["criteria_checks"] = [{"criterion": "c",
                             "command": "python main.py add a && python main.py list",
                             "expect_substring": "a"}]
    assert validate_design(d) == []


def test_chained_command_with_shell_step_rejected():
    d = make_design()
    d["success_signal"]["command"] = "echo hi > f.csv && python main.py add x"
    assert any("&&" in e for e in validate_design(d))


def test_chain_final_step_must_run_entrypoint():
    d = make_design()
    d["success_signal"]["command"] = (
        "python main.py add x && python core.py add y")
    assert any("entrypoint" in e for e in validate_design(d))


# ---------------------------------------------------------------- lessons

def _write_lessons(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_find_relevant_matches_by_keywords(tmp_path):
    path = tmp_path / "lessons.json"
    _write_lessons(path, [
        {"idea": "csv to markdown table converter",
         "keywords": ["csv", "markdown", "table"],
         "lesson": "do not depend on pre-existing input files"},
        {"idea": "binary search tree",
         "keywords": ["tree", "balance"],
         "lesson": "avoid impossible height constraints"},
    ])
    lessons = lessons_mod.load_lessons(path)
    found = lessons_mod.find_relevant("markdown 표 생성기 csv 변환", lessons)
    assert found and "input files" in found[0]


def test_find_relevant_no_match_returns_empty(tmp_path):
    path = tmp_path / "lessons.json"
    _write_lessons(path, [{"idea": "binary tree", "keywords": ["tree"],
                           "lesson": "x"}])
    lessons = lessons_mod.load_lessons(path)
    assert lessons_mod.find_relevant("weather dashboard", lessons) == []


def test_load_lessons_missing_or_corrupt(tmp_path):
    assert lessons_mod.load_lessons(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert lessons_mod.load_lessons(bad) == []


class _OneShotLLM:
    call_count = 0

    def generate(self, role, prompt, temperature=None):
        assert role == "critic"
        return ('{"keywords": ["csv", "table"], '
                '"lesson": "generate input files inside the check command"}')


def test_record_lesson_appends(tmp_path):
    path = tmp_path / "lessons.json"
    entry = lessons_mod.record_lesson(_OneShotLLM(), "csv tool",
                                      "failed: missing test.csv", path=path)
    assert entry is not None
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["lesson"].startswith("generate input")
    assert saved[0]["keywords"] == ["csv", "table"]


class _BrokenLLM:
    def generate(self, role, prompt, temperature=None):
        raise RuntimeError("api down")


def test_record_lesson_never_raises(tmp_path):
    path = tmp_path / "lessons.json"
    assert lessons_mod.record_lesson(_BrokenLLM(), "x", "y", path=path) is None
    assert not path.exists()
