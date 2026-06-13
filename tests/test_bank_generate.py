# bank_generate 테스트: mock 설계자 주입(콜 0) — 밸런서·재요청·중복·검증
import copy
import json

import pytest

from bank_db import BankDB
from bank_generate import build_prompt, generate_cards, pick_targets
from test_bank_schema import EXAMPLE


@pytest.fixture
def db(tmp_path):
    d = BankDB(tmp_path / "gen.sqlite")
    yield d
    d.close()


def fence(card: dict) -> str:
    return "여기 설계입니다:\n```json\n" + json.dumps(card, ensure_ascii=False) + "\n```"


class SeqDesigner:
    """미리 정해둔 응답을 순서대로 돌려주는 mock. 콜 0."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def design(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responses.pop(0)


class UniqueDesigner:
    """매 호출 제목·goal이 다른 유효 카드를 찍어내는 mock."""

    def __init__(self):
        self.n = 0

    _WORDS = ["json validator", "csv merger", "log tailer",
              "config differ", "markdown linter"]

    def design(self, prompt: str) -> str:
        c = copy.deepcopy(EXAMPLE)
        c["title"] = self._WORDS[self.n % len(self._WORDS)] + " cli"
        c["goal"] = f"서로 다른 목표 {self._WORDS[self.n % len(self._WORDS)]}"
        self.n += 1
        return fence(c)


def test_generate_inserts_unique_cards(db):
    stats = generate_cards(db, UniqueDesigner(), 5)
    assert stats["inserted"] == 5
    assert stats["duplicate"] == 0 and stats["invalid"] == 0
    assert db.count() == 5


def test_duplicate_counted_not_inserted(db):
    # 같은 카드만 반복 → 첫 장만 적재, 나머지는 duplicate
    same = fence(EXAMPLE)
    stats = generate_cards(db, SeqDesigner([same, same, same]), 3)
    assert stats["inserted"] == 1 and stats["duplicate"] == 2
    assert db.count() == 1


def test_parse_retry_recovers(db):
    bad = "JSON 없이 잡담만"
    good = fence({**copy.deepcopy(EXAMPLE), "title": "recovered tool",
                  "goal": "복구된 목표"})
    d = SeqDesigner([bad, good])
    stats = generate_cards(db, d, 1, parse_retries=1)
    assert stats["inserted"] == 1
    assert len(d.calls) == 2  # 첫 실패 후 1회 재요청


def test_invalid_after_retries_counted(db):
    d = SeqDesigner(["쓰레기1", "쓰레기2"])
    stats = generate_cards(db, d, 1, parse_retries=1)
    assert stats["invalid"] == 1 and stats["inserted"] == 0
    assert stats["last_errors"]


def test_retry_prompt_includes_errors(db):
    bad_card = {**copy.deepcopy(EXAMPLE), "difficulty_tags": ["bogus_tag"]}
    good = fence({**copy.deepcopy(EXAMPLE), "title": "fixed", "goal": "고침"})
    d = SeqDesigner([fence(bad_card), good])
    generate_cards(db, d, 1, parse_retries=1)
    assert "bogus_tag" in d.calls[1]  # 재요청 프롬프트에 검증 에러가 들어감


def test_balancer_targets_emptiest_level(db):
    # 레벨 3만 채워두면 다음 목표는 3이 아니어야
    c = copy.deepcopy(EXAMPLE)
    c["difficulty_level"] = 3
    db.insert_task(c)
    level, tags = pick_targets(db)
    assert level != 3
    assert len(tags) == 3


def test_build_prompt_lists_fixed_vocab():
    p = build_prompt(2, ["cli_arg_surface", "parser_logic", "stateful_io"])
    assert "표준 라이브러리만" in p and "멀티파일" in p
    assert "cli_arg_surface" in p
