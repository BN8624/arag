from conftest import make_design

from design_validator import implementation_order, validate_design


def test_valid_design_passes():
    assert validate_design(make_design()) == []


def test_single_file_rejected():
    d = make_design()
    d["files"] = [d["files"][0]]
    d["dependencies"] = {"main.py": []}
    errors = validate_design(d)
    assert any("at least 2" in e for e in errors)


def test_cycle_rejected():
    d = make_design()
    d["dependencies"] = {"main.py": ["core.py"], "core.py": ["main.py"]}
    assert any("circular" in e for e in validate_design(d))


def test_missing_entrypoint_rejected():
    d = make_design()
    d["entrypoint"] = "app.py"
    assert any("entrypoint" in e for e in validate_design(d))


def test_nested_path_rejected():
    d = make_design()
    d["files"][1]["path"] = "pkg/core.py"
    assert any("flat layout" in e for e in validate_design(d))


def test_no_import_edges_rejected():
    d = make_design()
    d["dependencies"] = {"main.py": [], "core.py": []}
    assert any("import edges" in e for e in validate_design(d))


def test_command_must_run_entrypoint():
    d = make_design()
    d["success_signal"]["command"] = "python core.py add x"
    assert any("entrypoint" in e for e in validate_design(d))


def test_implementation_order_deps_first():
    order = implementation_order(make_design())
    assert order.index("core.py") < order.index("main.py")
