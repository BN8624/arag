"""측정도구 수리 테스트 (콜0): 계약 메서드 인식 / success_signal 리스트 / 스키마."""

import docker_gate
import schema
from gates import run_static_gate


# ---- Fix 1: 계약 체크가 클래스 메서드를 인정 (T-5 false contract-missing 수정) ----

CORE_WITH_METHOD = '''\
class Simulator:
    def __init__(self, budget: int):
        self.budget = budget

    def run(self) -> dict:
        return {"budget": self.budget}
'''

MAIN_USES = '''\
import sys

from core import Simulator


def main() -> int:
    sim = Simulator(100)
    print(sim.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _design_method():
    return {
        "project_name": "sim", "entrypoint": "main.py",
        "files": [
            {"path": "main.py", "role": "entry",
             "interfaces": [{"kind": "function", "name": "main",
                             "signature": "def main() -> int"}]},
            {"path": "core.py", "role": "logic",
             "interfaces": [
                 {"kind": "class", "name": "Simulator"},
                 {"kind": "method", "name": "__init__",
                  "signature": "def __init__(self, budget: int)"},
                 {"kind": "method", "name": "run",
                  "signature": "def run(self) -> dict"}]},
        ],
        "dependencies": {"main.py": ["core.py"], "core.py": []},
        "acceptance_criteria": ["runs"],
        "success_signal": {"command": "python main.py", "expect_substring": "budget"},
    }


def test_contract_accepts_class_methods(tmp_path):
    (tmp_path / "core.py").write_text(CORE_WITH_METHOD, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN_USES, encoding="utf-8")
    issues = run_static_gate(tmp_path, _design_method())
    missing = [i for i in issues if i["kind"] == "contract-missing"]
    assert missing == [], f"메서드를 못 찾아 false contract-missing: {missing}"


def _design_qualified_method():
    """계약이 메서드를 'Simulator.run'처럼 클래스명으로 정규화해 부르는 경우
    (T-000012 design.json이 'BattleSimulator.run'으로 부른 실제 케이스)."""
    d = _design_method()
    for f in d["files"]:
        if f["path"] == "core.py":
            f["interfaces"] = [
                {"kind": "class", "name": "Simulator"},
                {"kind": "function", "name": "Simulator.__init__",
                 "signature": "def __init__(self, budget: int)"},
                {"kind": "function", "name": "Simulator.run",
                 "signature": "def run(self) -> dict"}]
    return d


def test_contract_accepts_qualified_method_names(tmp_path):
    (tmp_path / "core.py").write_text(CORE_WITH_METHOD, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN_USES, encoding="utf-8")
    issues = run_static_gate(tmp_path, _design_qualified_method())
    missing = [i for i in issues if i["kind"] == "contract-missing"]
    assert missing == [], f"정규화 메서드명을 못 찾아 false contract-missing: {missing}"


# ---- Fix 2: success_signal substring 리스트(전부 포함) ----

def test_substr_missing_string_and_list():
    out = "Winner: Hero\nTurns: 4\nRemaining HP: 58"
    # brittle 연결 문자열은 없음 → 누락으로 잡힘
    assert docker_gate._substr_missing(out, "Winner: Turns: Remaining HP:") \
        == ["Winner: Turns: Remaining HP:"]
    # 토큰 리스트는 전부 존재 → 통과(빈 누락)
    assert docker_gate._substr_missing(
        out, ["Winner:", "Turns:", "Remaining HP:"]) == []
    # 일부 누락
    assert docker_gate._substr_missing(out, ["Winner:", "Score:"]) == ["Score:"]
    # 빈 기대값은 통과
    assert docker_gate._substr_missing(out, "") == []


def test_golden_diff_localizes_expected_vs_actual():
    """빠진 'key: value' 토큰을 실제 출력값과 대조해 국소화한다."""
    out = "winner: enemy\nturns: 25\nenemy2: 152\nturns: 17"
    diff = docker_gate._golden_diff(
        out, ["turns: 23", "enemy2: 160", "winner: hero"])
    # 어긋난 값이 expected↔got으로 보여야 한다
    assert "expected '23'" in diff and "'25'" in diff      # turns(여러 값)
    assert "enemy2: expected '160', got '152'" in diff     # 단일 값
    assert "winner: expected 'hero', got 'enemy'" in diff
    # 출력에 아예 없는 key는 그렇게 표시
    nd = docker_gate._golden_diff(out, ["score: 9"])
    assert "not present in output" in nd


# ---- Fix 2c: 스키마가 리스트 expect_substring 허용 ----

def test_schema_expect_ok():
    assert schema._expect_ok("added")
    assert schema._expect_ok(["a", "b"])
    assert not schema._expect_ok("")
    assert not schema._expect_ok([])
    assert not schema._expect_ok(["ok", ""])
    assert not schema._expect_ok(123)


def test_validate_accepts_list_expect(tmp_path):
    d = _design_method()
    d["success_signal"]["expect_substring"] = ["Winner:", "Turns:"]
    d["criteria_checks"] = [{"criterion": "c", "command": "python main.py",
                             "expect_substring": ["Winner:", "Turns:"]}]
    errors = schema.validate_design(d) if hasattr(schema, "validate_design") \
        else schema.validate_shape(d)
    assert not any("expect_substring" in e for e in errors), errors
