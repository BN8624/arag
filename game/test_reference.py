# 레퍼런스 구현 자체 검증 — 골든 오라클의 출처가 PAMPHLET 규칙과 맞는지 (사람 검증 = oracle_verified)
"""이 테스트가 통과해야 game/이 신뢰할 골든이 된다. PAMPHLET §2 규칙을 직접 단언."""

from entities import make_entity, get_status
from status import apply_status, tick_start, tick_end, incoming_multiplier
from skills import resolve_skill
from combat import run_battle
from main import build_party


def _e(hp=100, atk=20, df=5, spd=10):
    return make_entity("x", "X", "hero", hp, atk, df, spd)


def test_burn_tick_5pct_floor():
    e = _e(hp=100)
    apply_status(e, "burn", 3)
    tick_start(e)
    assert e.hp == 95            # 5% of 100 = 5
    assert get_status(e, "burn").turns == 2


def test_poison_stack_and_decay():
    e = _e(hp=100)
    apply_status(e, "poison", 3, stacks=2)
    tick_end(e)
    assert e.hp == 100 - 16      # 8*2
    assert get_status(e, "poison").stacks == 1


def test_poison_cap_5():
    e = _e()
    apply_status(e, "poison", 3, stacks=4)
    apply_status(e, "poison", 3, stacks=4)
    assert get_status(e, "poison").stacks == 5


def test_shock_multiplier():
    e = _e()
    assert incoming_multiplier(e) == 1.0
    apply_status(e, "shock", 2)
    assert incoming_multiplier(e) == 1.25


def test_freeze_blocked_by_burn():
    e = _e()
    apply_status(e, "burn", 3)
    apply_status(e, "freeze", 1)
    assert get_status(e, "freeze") is None      # 무효


def test_burn_removes_freeze():
    e = _e()
    apply_status(e, "freeze", 1)
    apply_status(e, "burn", 3)
    assert get_status(e, "freeze") is None
    assert get_status(e, "burn") is not None


def test_shock_doubles_poison():
    e = _e()
    apply_status(e, "shock", 2)
    apply_status(e, "poison", 3, stacks=2)
    assert get_status(e, "poison").stacks == 4   # 2 -> x2


def test_combo_detonate_after_ignite():
    a = _e(atk=20)
    t1 = make_entity("t1", "T", "enemy", 200, 0, 0, 5)
    t2 = make_entity("t2", "T", "enemy", 200, 0, 0, 5)
    resolve_skill(a, t1, "ignite")          # last_skill=ignite, t1 피격→last reset(무관)
    before = t2.hp
    resolve_skill(a, t2, "detonate")        # 콤보: base50 → 20+50-0=70
    assert before - t2.hp == 70


def test_combo_strike_double_after_charge():
    a = _e(atk=20)
    t = make_entity("t", "T", "enemy", 200, 0, 0, 5)
    resolve_skill(a, a, "charge")           # last_skill=charge
    before = t.hp
    resolve_skill(a, t, "combo_strike")     # 2회: (20+12-0)*2 = 64
    assert before - t.hp == 64


def test_battle_deterministic():
    h1, e1 = build_party(5)
    h2, e2 = build_party(5)
    r1 = run_battle(h1, e1, seed=5)
    r2 = run_battle(h2, e2, seed=5)
    assert r1["final_hp"] == r2["final_hp"]
    assert r1["winner"] == r2["winner"]
