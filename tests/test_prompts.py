"""프롬프트 회귀 테스트: 실관측 패턴에서 나온 핵심 규칙이 빠지지 않게 고정."""

from prompts import design_prompt, improve_prompt


def test_design_prompt_demands_promise_coverage():
    """perfect-but-gap 8/8 대응: 수용기준이 약속(단위·형식·범위)을 검증해야 한다."""
    p = design_prompt("시간 기록을 합산해 hours로 리포트하는 CLI")
    assert "PROMISES" in p
    assert "unit or format" in p
    assert "non-default input" in p
    assert "silently narrows a stated promise" in p


def test_improve_prompt_demands_python_only_checks():
    """improve ABORT 2건 대응: 신규 채점 커맨드는 python 스텝만."""
    p = improve_prompt({"files": []}, {"main.py": "pass"}, "", "(scoreboard)")
    assert "ONLY of steps starting with" in p
    assert "NO shell redirection" in p
