import json

from conftest import make_design

from schema import extract_json, parse_design, validate_shape


def test_extract_json_fenced():
    text = "Here is the design:\n```json\n{\"a\": 1}\n```\nDone."
    assert json.loads(extract_json(text)) == {"a": 1}


def test_extract_json_bare_with_prose():
    text = 'Sure! {"a": {"b": [1, 2]}, "c": "x}y"} trailing words'
    assert json.loads(extract_json(text)) == {"a": {"b": [1, 2]}, "c": "x}y"}


def test_extract_json_none():
    assert extract_json("no json here") is None


def test_parse_design_roundtrip():
    design, errors = parse_design(json.dumps(make_design()))
    assert errors == []
    assert design["entrypoint"] == "main.py"


def test_parse_design_missing_key():
    d = make_design()
    del d["success_signal"]
    design, errors = parse_design(json.dumps(d))
    assert design is None
    assert any("success_signal" in e for e in errors)


def test_validate_shape_bad_types():
    d = make_design()
    d["acceptance_criteria"] = []
    assert validate_shape(d)
