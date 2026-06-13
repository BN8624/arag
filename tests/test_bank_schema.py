# bank_schema 검증 테스트: 예시 통과 + 외부어휘·레벨·스키마누락 거부
import copy

from bank_schema import normalize_goal, validate_card

EXAMPLE = {
    "source_model": "gemma-31b",
    "title": "CSV log summarizer with CLI options",
    "goal": "작은 CSV 로그를 읽고 상태별 요약을 출력하는 CLI 도구.",
    "difficulty_level": 2,
    "difficulty_tags": ["cli_arg_surface", "parser_logic", "stateful_io"],
    "expected_failure_modes": ["argument_parsing_error", "missing_edge_case"],
    "acceptance_criteria": ["--input 경로를 받는다", "status별 개수를 출력한다",
                            "빈 파일과 잘못된 컬럼을 처리한다"],
    "required_files": ["main.py", "parser.py", "tests/test_cli.py"],
    "test_oracle": "pytest 기준 전체 통과",
    "anti_goals": ["웹 서버 금지", "외부 DB 금지"],
    "notes_for_evaluator": "파일 I/O와 CLI 인자 표면을 동시에 보는 과제",
    "design_quality_score": None,
}


def card(**overrides) -> dict:
    c = copy.deepcopy(EXAMPLE)
    c.update(overrides)
    return c


def test_example_card_passes():
    assert validate_card(EXAMPLE) == []


def test_external_difficulty_tag_rejected():
    errors = validate_card(card(difficulty_tags=["cli_arg_surface", "fancy_tag"]))
    assert any("unknown difficulty_tag" in e and "fancy_tag" in e for e in errors)


def test_external_failure_mode_rejected():
    errors = validate_card(card(expected_failure_modes=["made_up_mode"]))
    assert any("unknown failure_mode" in e for e in errors)


def test_bad_difficulty_level_rejected():
    assert any("difficulty_level" in e for e in validate_card(card(difficulty_level=7)))
    assert any("difficulty_level" in e for e in validate_card(card(difficulty_level="2")))


def test_missing_key_rejected():
    c = card()
    del c["goal"]
    assert any("missing required key" in e and "goal" in e for e in validate_card(c))


def test_single_file_task_rejected():
    assert any("at least 2 files" in e
               for e in validate_card(card(required_files=["main.py"])))


def test_empty_tags_rejected():
    assert any("difficulty_tags" in e for e in validate_card(card(difficulty_tags=[])))


def test_wrong_schema_version_rejected():
    assert any("schema_version" in e
               for e in validate_card(card(schema_version="task_card.v2")))


def test_score_may_be_null_or_number():
    assert validate_card(card(design_quality_score=None)) == []
    assert validate_card(card(design_quality_score=4.5)) == []
    assert any("design_quality_score" in e
               for e in validate_card(card(design_quality_score="high")))


def test_normalize_goal_collapses_punct_and_case():
    assert normalize_goal("Read a CSV, summarize!") == normalize_goal("read a csv summarize")
