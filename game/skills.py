# 스킬/콤보 — 점화·폭발·준비·연계타 (PAMPHLET §2.3). 콤보는 actor.last_skill로 판정
"""resolve_skill이 피해 계산(감전 배수 포함)·콤보 강화·상태부여·last_skill 갱신을 처리한다."""

from entities import Entity
from status import apply_status, incoming_multiplier


def _ev(kind, actor, target, value, detail) -> dict:
    return {"kind": kind, "actor": actor, "target": target, "value": value,
            "detail": detail}


def _hit(actor: Entity, target: Entity, base: int) -> int:
    raw = max(1, actor.atk + base - target.defense)
    dmg = int(raw * incoming_multiplier(target))  # 감전 ×1.25 내림
    dealt = min(target.hp, dmg)
    target.hp -= dealt
    if dealt > 0:
        target.last_skill = None  # 피격으로 콤보 사슬 끊김(PAMPHLET §2.3)
    return dealt


def resolve_skill(actor: Entity, target: Entity, skill: str) -> list:
    events: list = []
    prev = actor.last_skill
    if skill == "ignite":
        d = _hit(actor, target, 5)
        events.append(_ev("skill", actor.id, target.id, d, "ignite"))
        events += apply_status(target, "burn", 3)
    elif skill == "detonate":
        if prev == "ignite":
            d = _hit(actor, target, 50)
            events.append(_ev("combo", actor.id, target.id, d, "detonate after ignite"))
            events += apply_status(target, "burn", 3)
        else:
            d = _hit(actor, target, 20)
            events.append(_ev("skill", actor.id, target.id, d, "detonate"))
    elif skill == "charge":
        events.append(_ev("skill", actor.id, actor.id, 0, "charge"))
    elif skill == "combo_strike":
        hits = 2 if prev == "charge" else 1
        for i in range(hits):
            d = _hit(actor, target, 12)
            tag = "combo_strike x2" if hits == 2 else "combo_strike"
            events.append(_ev("combo" if hits == 2 else "skill",
                              actor.id, target.id, d, tag))
    else:
        events.append(_ev("skill", actor.id, target.id, 0, f"unknown:{skill}"))
    actor.last_skill = skill
    return events
