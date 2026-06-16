# 외부 리뷰 #2~#6 하네스 강화 테스트 (콜0). #1은 test_docker_sem(격리), #7·#8 보류.

import types

import design_validator
import phase_implement
import reporting
from gates import run_static_gate
from phase_gates import GatesPhase
from phase_common import TEST_FILE


# ---- #2 pass rate가 error를 분모에 포함 ----

def _rate(log: str):
    ns = types.SimpleNamespace(last_exec_log=log)
    return GatesPhase._pytest_pass_rate(ns)


def test_pass_rate_includes_errors():
    # 8 passed, 1 failed, 1 error → 8/10 (=0.8), 8/9(≈0.89) 아님
    assert _rate("8 passed, 1 failed, 1 error in 0.2s") == 0.8


def test_pass_rate_plain():
    assert _rate("9 passed, 1 failed in 0.1s") == 0.9


def test_pass_rate_none_without_summary():
    assert _rate("Traceback ...\nImportError") is None


# ---- #3 클래스 메서드 시그니처 mismatch 검출 ----

CORE_BAD_METHOD = '''\
class Battle:
    def run(self):          # 계약은 run(turns) = 인자 1개인데 0개
        return "x"
'''
MAIN = '''\
import sys
from core import Battle


def main() -> int:
    print(Battle().run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _design_method(sig):
    return {
        "project_name": "b", "entrypoint": "main.py",
        "files": [
            {"path": "main.py", "role": "entry", "interfaces": [
                {"kind": "function", "name": "main", "signature": "def main() -> int"}]},
            {"path": "core.py", "role": "logic", "interfaces": [
                {"kind": "class", "name": "Battle"},
                {"kind": "method", "name": "run", "signature": sig}]},
        ],
        "dependencies": {"main.py": ["core.py"], "core.py": []},
        "acceptance_criteria": ["runs"],
        "success_signal": {"command": "python main.py", "expect_substring": "x"},
    }


def test_method_signature_mismatch_detected(tmp_path):
    (tmp_path / "core.py").write_text(CORE_BAD_METHOD, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN, encoding="utf-8")
    issues = run_static_gate(tmp_path, _design_method("def run(self, turns: int) -> str"))
    assert any(i["kind"] == "contract-mismatch" for i in issues)


def test_method_signature_match_ok(tmp_path):
    # 계약이 self 없이 turns만 적어도 self 제외 비교라 0 args 코드와는 mismatch
    (tmp_path / "core.py").write_text(CORE_BAD_METHOD, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN, encoding="utf-8")
    issues = run_static_gate(tmp_path, _design_method("def run(turns: int) -> str"))
    assert any(i["kind"] == "contract-mismatch" for i in issues)


def test_method_signature_correct_no_issue(tmp_path):
    good = "class Battle:\n    def run(self, turns):\n        return turns\n"
    (tmp_path / "core.py").write_text(good, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN, encoding="utf-8")
    issues = run_static_gate(tmp_path, _design_method("def run(turns: int) -> str"))
    assert not any(i["kind"] == "contract-mismatch" for i in issues)


# ---- #4 노트 로더 실패를 침묵하지 않고 로그 ----

def test_note_loader_logs_on_error(monkeypatch):
    logged = []
    ns = types.SimpleNamespace(
        notes_enabled=True, idea="x", task_id="T-1", mode="warm",
        log=lambda ev, **k: logged.append((ev, k)),
        _say=lambda *a, **k: None)
    monkeypatch.setattr(phase_implement.critique_notes, "find_relevant",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    out = phase_implement.ImplementPhase._load_notes(ns)
    assert out == []
    assert any(ev == "critique-notes-load-error" for ev, _ in logged)


# ---- #5 oracle_strength 라벨 ----

def test_oracle_strength_strong_when_tests_exist(tmp_path):
    (tmp_path / TEST_FILE).write_text("def test_x(): assert True\n", encoding="utf-8")
    ns = types.SimpleNamespace(workspace=tmp_path)
    assert reporting.ReportingMixin._oracle_strength(ns) == "strong"


def test_oracle_strength_weak_when_no_tests(tmp_path):
    ns = types.SimpleNamespace(workspace=tmp_path)
    assert reporting.ReportingMixin._oracle_strength(ns) == "weak"


# ---- #6 python -c 인라인 코드 금지 ----

def _design_cmd(success_cmd, criteria_cmd=None):
    d = {
        "project_name": "p", "entrypoint": "main.py",
        "files": [
            {"path": "main.py", "role": "entry", "interfaces": []},
            {"path": "core.py", "role": "logic", "interfaces": []},
        ],
        "dependencies": {"main.py": ["core.py"], "core.py": []},
        "acceptance_criteria": ["a"],
        "success_signal": {"command": success_cmd, "expect_substring": "ok"},
    }
    if criteria_cmd:
        d["criteria_checks"] = [{"criterion": "c", "command": criteria_cmd,
                                 "expect_substring": "ok"}]
    return d


def test_success_signal_rejects_python_dash_c():
    errs = design_validator.validate_design(
        _design_cmd('python -c "import core"'))
    assert any("-c" in e for e in errs)


def test_criteria_checks_rejects_python_dash_c():
    errs = design_validator.validate_design(
        _design_cmd("python main.py", criteria_cmd='python -c "print(1)"'))
    assert any("-c" in e for e in errs)


def test_normal_entrypoint_command_ok():
    errs = design_validator.validate_design(_design_cmd("python main.py"))
    assert not any("-c" in e for e in errs)
