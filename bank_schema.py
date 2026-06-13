# Design Bank task_card v1 스키마: 고정 어휘 + 구조 검증 (콜 0)
"""task_card v1 — 실험 가능한 과제를 구조화한 단위.

설계자(31B/Gemini)가 내놓는 카드의 형태는 PLAN.md §2.2 참조.
검증 원칙: 고정 어휘(아래 3개 집합) 밖의 값은 거부한다. 동의어 자동 매핑 안 함.
validate_card는 schema.validate_shape와 같은 관례 — 에러 문자열 리스트를 돌려준다
(빈 리스트 = 통과).
"""

import re

SCHEMA_VERSION = "task_card.v1"

# 난이도 태그 (12종, PLAN §2.3) — level 숫자보다 조합이 중요
DIFFICULTY_TAGS = frozenset({
    "multi_file_contract", "stateful_io", "numeric_precision",
    "cli_arg_surface", "regression_sensitive", "parser_logic",
    "external_mock", "test_generation", "schema_validation",
    "error_handling", "refactor_required", "context_heavy",
})

# 예상 실패모드 (13종, PLAN §2.3) — 실행 결과와 비교할 기준
FAILURE_MODES = frozenset({
    "import_mismatch", "signature_drift", "missing_edge_case",
    "argument_parsing_error", "test_contract_mismatch",
    "state_persistence_error", "numeric_tolerance_error",
    "parser_boundary_error", "regression_introduced", "mocking_failure",
    "schema_violation", "overengineering", "under_specification",
})

DIFFICULTY_LEVELS = frozenset({1, 2, 3, 4, 5})

# 설계자가 반드시 채워야 하는 내용 키 (task_id·created_at은 DB가 채움)
CONTENT_KEYS = (
    "source_model", "title", "goal", "difficulty_level",
    "difficulty_tags", "expected_failure_modes", "acceptance_criteria",
    "required_files", "test_oracle", "anti_goals", "notes_for_evaluator",
)

# DB가 자동 채우는 키 (없거나 "AUTO"여도 검증 통과)
AUTO_KEYS = ("task_id", "created_at")

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+", re.UNICODE)


def normalize_goal(goal: str) -> str:
    """goal을 중복 감지용으로 정규화 — 소문자·구두점제거·공백압축."""
    text = _PUNCT.sub(" ", goal.lower())
    return _WS.sub(" ", text).strip()


def validate_card(card: dict) -> list[str]:
    """task_card 구조 + 고정 어휘 검증. 빈 리스트면 통과."""
    errors: list[str] = []
    if not isinstance(card, dict):
        return ["card must be an object"]

    for key in CONTENT_KEYS:
        if key not in card:
            errors.append(f"missing required key: {key!r}")
    if errors:
        return errors

    # schema_version: 있으면 v1이어야 한다 (DB가 채워도 됨)
    sv = card.get("schema_version")
    if sv is not None and sv != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}, got {sv!r}")

    for key in ("source_model", "title", "goal", "test_oracle",
                "notes_for_evaluator"):
        if not isinstance(card.get(key), str) or not card[key].strip():
            errors.append(f"{key!r} must be a non-empty string")

    level = card.get("difficulty_level")
    if level not in DIFFICULTY_LEVELS:
        errors.append("difficulty_level must be an integer 1~5, "
                      f"got {level!r}")

    tags = card.get("difficulty_tags")
    if not isinstance(tags, list) or not tags:
        errors.append("difficulty_tags must be a non-empty list")
    else:
        for t in tags:
            if t not in DIFFICULTY_TAGS:
                errors.append(f"unknown difficulty_tag: {t!r} "
                              "(fixed vocabulary only, no synonyms)")

    modes = card.get("expected_failure_modes")
    if not isinstance(modes, list) or not modes:
        errors.append("expected_failure_modes must be a non-empty list")
    else:
        for m in modes:
            if m not in FAILURE_MODES:
                errors.append(f"unknown failure_mode: {m!r} "
                              "(fixed vocabulary only, no synonyms)")

    for key in ("acceptance_criteria", "required_files", "anti_goals"):
        v = card.get(key)
        if key == "anti_goals":
            ok = isinstance(v, list) and all(isinstance(x, str) for x in v)
        else:
            ok = (isinstance(v, list) and bool(v)
                  and all(isinstance(x, str) and x.strip() for x in v))
        if not ok:
            need = "list of strings" if key == "anti_goals" \
                else "non-empty list of strings"
            errors.append(f"{key!r} must be a {need}")

    # 멀티파일 강제 (CLAUDE.md: 단일파일은 실패) — 과제도 2개 이상 요구
    files = card.get("required_files")
    if isinstance(files, list) and 0 < len(files) < 2:
        errors.append("required_files must list at least 2 files "
                      "(single-file tasks are out of scope)")

    score = card.get("design_quality_score")
    if score is not None and not isinstance(score, (int, float)):
        errors.append("design_quality_score must be a number or null")

    return errors
