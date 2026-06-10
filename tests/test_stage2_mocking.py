"""2단계 신기능 테스트: 모의 응답 파일 / 키 하드코딩 탐지 / 화이트리스트 확장."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design, write_project

from design_validator import validate_design
from gates import external_imports, run_static_gate
from orchestrator import Orchestrator
from schema import validate_shape


# ------------------------------------------------- mock fixtures: 검증

def test_fixture_shape_requires_path_and_content():
    d = make_design()
    d["mock_fixtures"] = [{"path": "mock.json"}]  # content 없음
    assert any("content" in e for e in validate_shape(d))


def test_fixture_nested_path_rejected():
    d = make_design()
    d["mock_fixtures"] = [{"path": "data/mock.json", "content": "{}"}]
    assert any("flat" in e for e in validate_design(d))


def test_fixture_py_path_rejected():
    d = make_design()
    d["mock_fixtures"] = [{"path": "mock.py", "content": "{}"}]
    assert any(".py" in e for e in validate_design(d))


def test_fixture_collision_with_code_rejected():
    d = make_design()
    d["mock_fixtures"] = [{"path": "main.py", "content": "{}"}]
    assert validate_design(d)  # .py 규칙이든 충돌이든 어쨌든 거부


def test_valid_fixture_accepted():
    d = make_design()
    d["mock_fixtures"] = [{"path": "mock_response.json",
                           "content": {"rows": [1, 2]}}]
    assert validate_design(d) == []


# ------------------------------------------------- mock fixtures: 배치

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


def test_fixtures_written_to_workspace(tmp_path):
    d = make_design()
    d["mock_fixtures"] = [
        {"path": "mock_response.json", "content": {"items": ["a", "b"]}},
        {"path": "sample.txt", "content": "plain text"},
    ]
    llm = MockLLM(critic=[json.dumps(d), "LGTM"],
                  generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)])
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("api tool") is True
    ws = tmp_path / "run" / "workspace"
    saved = json.loads((ws / "mock_response.json").read_text(encoding="utf-8"))
    assert saved == {"items": ["a", "b"]}
    assert (ws / "sample.txt").read_text(encoding="utf-8") == "plain text"


def test_pingpong_errors_detected(tmp_path):
    """A->B->A 교대 에러도 진전 없음으로 잡아야 함 (연속 중복만이 아니라)."""
    broken_a = GOOD_MAIN.replace("from core import add_item",
                                 "from core import add_item_nope")
    broken_b = GOOD_MAIN.replace("import sys",
                                 "import sys\nimport json")  # json 미사용
    llm = MockLLM(
        critic=[json.dumps(make_design())],
        # 초기 A -> 수정 B -> 수정이 다시 A (핑퐁) -> 즉시 중단돼야 함
        generator=[fenced(GOOD_CORE), fenced(broken_a), fenced(broken_b),
                   fenced(broken_a)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("todo") is False
    events = (tmp_path / "run" / "events.jsonl").read_text(encoding="utf-8")
    assert "no-progress" in events
    assert llm.queues["generator"] == []  # 큐를 다 쓰고 더 부르지 않았어야 함


# ------------------------------------------------- hardcoded secrets

SECRET_MAIN = '''\
import sys

from core import add_item

API_KEY = "sk-1234567890abcdef1234"


def main() -> int:
    item = add_item("db.json", sys.argv[1])
    print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def test_hardcoded_key_flagged(tmp_path):
    write_project(tmp_path, {"core.py": GOOD_CORE, "main.py": SECRET_MAIN})
    kinds = {i["kind"] for i in run_static_gate(tmp_path)}
    assert "hardcoded-secret" in kinds


def test_env_key_not_flagged(tmp_path):
    ok = SECRET_MAIN.replace('API_KEY = "sk-1234567890abcdef1234"',
                             'import os\nAPI_KEY = os.environ.get("API_KEY", "")')
    write_project(tmp_path, {"core.py": GOOD_CORE, "main.py": ok})
    kinds = {i["kind"] for i in run_static_gate(tmp_path)}
    assert "hardcoded-secret" not in kinds


def test_short_default_not_flagged(tmp_path):
    ok = SECRET_MAIN.replace('"sk-1234567890abcdef1234"', '""')
    write_project(tmp_path, {"core.py": GOOD_CORE, "main.py": ok})
    kinds = {i["kind"] for i in run_static_gate(tmp_path)}
    assert "hardcoded-secret" not in kinds


# ------------------------------------------------- whitelist 확장

def test_new_packages_allowed(tmp_path):
    helper = ("import openpyxl\nimport pypdf\nfrom PIL import Image\n\n\n"
              "def use():\n    return openpyxl, pypdf, Image\n")
    main = ("from helper import use\n\n\nif __name__ == '__main__':\n"
            "    print(use())\n")
    write_project(tmp_path, {"helper.py": helper, "main.py": main})
    kinds = {i["kind"] for i in run_static_gate(tmp_path)}
    assert "non-stdlib-import" not in kinds
    assert external_imports(tmp_path) == {"openpyxl", "pypdf", "Pillow"}
