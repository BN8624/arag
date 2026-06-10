from conftest import GOOD_CORE, GOOD_MAIN, make_design, write_project

from gates import run_static_gate


def kinds(issues):
    return {i["kind"] for i in issues}


def test_clean_project_passes(tmp_path):
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": GOOD_CORE})
    assert run_static_gate(tmp_path, make_design()) == []


def test_syntax_error(tmp_path):
    write_project(tmp_path, {"main.py": "def broken(:\n", "core.py": GOOD_CORE})
    assert "syntax-error" in kinds(run_static_gate(tmp_path, make_design()))


def test_broken_import(tmp_path):
    bad_main = GOOD_MAIN.replace("from core import add_item",
                                 "from core import add_item_nope")
    write_project(tmp_path, {"main.py": bad_main, "core.py": GOOD_CORE})
    issues = run_static_gate(tmp_path, make_design())
    assert "broken-import" in kinds(issues)


def test_missing_attr(tmp_path):
    main = (
        "import sys\nimport core\n\n"
        "def main() -> int:\n"
        "    print(core.add_item_nope('x', 'y'))\n"
        "    return 0\n\n"
        'if __name__ == "__main__":\n    sys.exit(main())\n'
    )
    write_project(tmp_path, {"main.py": main, "core.py": GOOD_CORE})
    assert "missing-attr" in kinds(run_static_gate(tmp_path, make_design()))


def test_unused_import(tmp_path):
    core = GOOD_CORE + "\nimport os\n"
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": core})
    issues = run_static_gate(tmp_path, make_design())
    assert "unused-import" in kinds(issues)


def test_undefined_name(tmp_path):
    core = GOOD_CORE + "\n\ndef extra():\n    return mystery_value + 1\n"
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": core})
    issues = run_static_gate(tmp_path, make_design())
    assert "undefined-name" in kinds(issues)
    assert any("mystery_value" in i["message"] for i in issues)


def test_undefined_skipped_with_dynamic_code(tmp_path):
    core = GOOD_CORE + "\n\ndef extra():\n    return eval('mystery_value')\n"
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": core})
    assert "undefined-name" not in kinds(run_static_gate(tmp_path, make_design()))


def test_stub_detected(tmp_path):
    core = GOOD_CORE + '\n\ndef todo_later():\n    """docstring only."""\n    pass\n'
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": core})
    assert "stub" in kinds(run_static_gate(tmp_path, make_design()))


def test_fake_multifile(tmp_path):
    main = ('import sys\n\ndef main() -> int:\n    print("hi")\n    return 0\n\n'
            'if __name__ == "__main__":\n    sys.exit(main())\n')
    write_project(tmp_path, {"main.py": main, "core.py": GOOD_CORE})
    issues = run_static_gate(tmp_path, None)
    assert "fake-multifile" in kinds(issues)


def test_orphan_file(tmp_path):
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": GOOD_CORE,
                             "extra.py": "VALUE = 1\n"})
    issues = run_static_gate(tmp_path, make_design())
    assert any(i["kind"] == "orphan-file" and i["file"] == "extra.py"
               for i in issues)


def test_missing_dependency_vs_design(tmp_path):
    design = make_design()
    design["dependencies"]["core.py"] = ["main.py"]  # 설계는 기대하지만 실제론 없음
    # (순환이지만 게이트는 설계 검증과 별개로 간선 존재만 본다)
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": GOOD_CORE})
    assert "missing-dependency" in kinds(run_static_gate(tmp_path, design))


def test_contract_missing(tmp_path):
    design = make_design()
    design["files"][1]["interfaces"].append(
        {"kind": "function", "name": "remove_item",
         "signature": "def remove_item(store_path: str, item_id: int) -> bool"})
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": GOOD_CORE})
    issues = run_static_gate(tmp_path, design)
    assert any(i["kind"] == "contract-missing" and "remove_item" in i["message"]
               for i in issues)


def test_contract_arg_mismatch(tmp_path):
    design = make_design()
    design["files"][1]["interfaces"][0]["signature"] = (
        "def add_item(store_path: str, text: str, priority: int) -> dict")
    write_project(tmp_path, {"main.py": GOOD_MAIN, "core.py": GOOD_CORE})
    assert "contract-mismatch" in kinds(run_static_gate(tmp_path, design))


def test_non_stdlib_import(tmp_path):
    core = "import requests\n\n\ndef fetch(url):\n    return requests.get(url)\n"
    main = GOOD_MAIN.replace("from core import add_item", "from core import fetch") \
                    .replace("add_item(\"todo.json\", sys.argv[2])",
                             "fetch(sys.argv[2])") \
                    .replace("item['text']", "item")
    write_project(tmp_path, {"main.py": main, "core.py": core})
    assert "non-stdlib-import" in kinds(run_static_gate(tmp_path, make_design()))


def test_no_entrypoint_block(tmp_path):
    main = "from core import add_item\n\n\ndef main() -> int:\n    return 0\n"
    write_project(tmp_path, {"main.py": main, "core.py": GOOD_CORE})
    issues = run_static_gate(tmp_path, make_design())
    assert "no-entrypoint" in kinds(issues)
