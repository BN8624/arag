# 상태이상 엔진 — 화상·빙결·중독·감전 + 임의 상호작용 매트릭스(PAMPHLET §2.1)
"""부여(apply_status)는 매트릭스를 적용하고, tick_start/tick_end가 지속피해·감쇠를 처리한다.
모든 변화는 Event(dict)로 기록. HP는 0 미만으로 내려가지 않는다."""

from entities import Entity, Status, get_status, has_status


def _ev(kind, target=None, value=0, detail="", actor=None) -> dict:
    return {"kind": kind, "actor": actor, "target": target, "value": value,
            "detail": detail}


def _damage(e: Entity, amount: int) -> int:
    """HP 감소(0 하한). 실제 들어간 피해 반환."""
    dealt = min(e.hp, max(0, amount))
    e.hp -= dealt
    return dealt


def apply_status(target: Entity, stype: str, turns: int, stacks: int = 1) -> list:
    events: list = []
    # 매트릭스 (부여 시점 판정)
    if stype == "freeze" and has_status(target, "burn"):
        events.append(_ev("status_apply", target.id, detail="freeze blocked by burn"))
        return events
    if stype == "burn" and has_status(target, "freeze"):
        target.statuses = [s for s in target.statuses if s.type != "freeze"]
        events.append(_ev("status_apply", target.id, detail="freeze removed by burn"))

    existing = get_status(target, stype)
    if stype == "poison":
        if existing:
            existing.stacks = min(5, existing.stacks + stacks)
            existing.turns = max(existing.turns, turns)
        else:
            target.statuses.append(Status("poison", turns, min(5, stacks)))
        events.append(_ev("status_apply", target.id, detail="poison",
                          value=get_status(target, "poison").stacks))
        # 감전 보유 중 중독 부여 → 스택 즉시 ×2(상한 5)
        if has_status(target, "shock"):
            p = get_status(target, "poison")
            p.stacks = min(5, p.stacks * 2)
            events.append(_ev("combo", target.id, value=p.stacks,
                              detail="shock x2 poison"))
    else:
        if existing:
            existing.turns = max(existing.turns, turns)
        else:
            target.statuses.append(Status(stype, turns, 1))
        events.append(_ev("status_apply", target.id, detail=stype))

    # 증발: 부여 후 화상+빙결 동시 보유 시 둘 다 제거 + 즉발 30
    if has_status(target, "burn") and has_status(target, "freeze"):
        target.statuses = [s for s in target.statuses
                           if s.type not in ("burn", "freeze")]
        d = _damage(target, 30)
        events.append(_ev("evaporate", target.id, value=d, detail="burn+freeze"))
    return events


def tick_start(e: Entity) -> list:
    """턴 시작 처리: 화상."""
    events: list = []
    burn = get_status(e, "burn")
    if burn:
        d = _damage(e, e.hp * 5 // 100)
        burn.turns -= 1
        if burn.turns <= 0:
            e.statuses = [s for s in e.statuses if s.type != "burn"]
        events.append(_ev("status_tick", e.id, value=d, detail="burn"))
    return events


def tick_end(e: Entity) -> list:
    """턴 끝 처리: 중독(피해+스택감쇠), 감전(턴감쇠)."""
    events: list = []
    poison = get_status(e, "poison")
    if poison:
        d = _damage(e, 8 * poison.stacks)
        poison.stacks -= 1
        if poison.stacks <= 0:
            e.statuses = [s for s in e.statuses if s.type != "poison"]
        events.append(_ev("status_tick", e.id, value=d, detail="poison"))
    shock = get_status(e, "shock")
    if shock:
        shock.turns -= 1
        if shock.turns <= 0:
            e.statuses = [s for s in e.statuses if s.type != "shock"]
        events.append(_ev("status_tick", e.id, value=0, detail="shock decay"))
    return events


def incoming_multiplier(e: Entity) -> float:
    return 1.25 if has_status(e, "shock") else 1.0
