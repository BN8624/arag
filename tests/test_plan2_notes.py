"""PLAN2 warm 노트 품질 필터 테스트 (콜0): USE/HOLD/DROP."""

import plan2_notes


def test_use_general_actionable_rule():
    # 일반적·실행가능 규칙 → USE
    assert plan2_notes.classify_note(
        "Always validate input formats before processing them.") == "USE"
    assert plan2_notes.classify_note(
        "Ensure malformed lines are ignored instead of partially parsed.") == "USE"


def test_drop_card_specific():
    # 특정 파일명 → DROP
    assert plan2_notes.classify_note(
        "battle.py imports Character from player.py instead of character.py") == "DROP"
    # 특정 함수 호출 → DROP
    assert plan2_notes.classify_note(
        "cli.py calls run_fight() but it should call run_battle()") == "DROP"


def test_drop_trivial():
    assert plan2_notes.classify_note("fix it") == "DROP"
    assert plan2_notes.classify_note("") == "DROP"


def test_hold_ambiguous():
    # 동사도 없고 카드전용도 아닌 애매한 서술 → HOLD
    assert plan2_notes.classify_note(
        "The scoreboard sometimes shows confusing output to the reader") == "HOLD"


def test_partition_dedup_and_counts():
    notes = [
        "Always validate input before parsing.",          # USE
        "Always validate input before parsing.",          # 중복 → 제거
        "main.py has a bug",                              # DROP (파일명)
        "The output is occasionally unclear overall here",  # HOLD
    ]
    parts = plan2_notes.partition(notes)
    assert len(parts["USE"]) == 1
    assert len(parts["DROP"]) == 1
    assert len(parts["HOLD"]) == 1


def test_render_note_audit():
    out = plan2_notes.render_note_audit(["Always validate input before parsing."])
    assert "USE만 warm" in out
    assert "[ ] USE" in out
    assert "합계: USE 1" in out
