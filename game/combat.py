# 템포 턴제 전투 리졸버 — 행동게이지·타이브레이크·빙결스킵 + run_battle (PAMPHLET §2.2, §3 AI)
"""매 틱 gauge += spd, 100 도달 시 행동(초과분 이월). 동시 도달은 3단 타이브레이크.
AI 정책(결정적): 대상=생존 적 중 HP 최저(동률 인덱스), 스킬=로테이션 순환."""

from entities import Entity, get_status
from status import tick_start, tick_end
from skills import resolve_skill


def _ev(kind, actor=None, target=None, value=0, detail="") -> dict:
    return {"kind": kind, "actor": actor, "target": target, "value": value,
            "detail": detail}


def next_actor(entities: list) -> Entity | None:
    """gauge>=100 생존자 중 우선순위 1명. 타이브레이크: spd↓ → hp↑ → 등록순서."""
    ready = [(i, e) for i, e in enumerate(entities) if e.alive and e.gauge >= 100]
    if not ready:
        return None
    ready.sort(key=lambda t: (-t[1].spd, t[1].hp, t[0]))
    return ready[0][1]


def _pick_target(actor: Entity, foes: list) -> Entity | None:
    living = [(i, e) for i, e in enumerate(foes) if e.alive]
    if not living:
        return None
    living.sort(key=lambda t: (t[1].hp, t[0]))
    return living[0][1]


def run_battle(heroes: list, enemies: list, seed: int = 0,
               max_turns: int = 100) -> dict:
    order = list(heroes) + list(enemies)   # 등록 순서: heroes 먼저
    events: list = []
    dead: set = set()
    turns = 0

    def check_deaths():
        for e in order:
            if e.hp <= 0 and e.id not in dead:
                dead.add(e.id)
                events.append(_ev("death", target=e.id, detail=e.team))

    while turns < max_turns:
        if all(not h.alive for h in heroes) or all(not x.alive for x in enemies):
            break
        for e in order:                    # 틱: 게이지 충전
            if e.alive:
                e.gauge += e.spd
        # 이 틱에 준비된(>=100) 엔티티들을 우선순위대로 처리
        while True:
            if all(not h.alive for h in heroes) or all(not x.alive for x in enemies):
                break
            actor = next_actor(order)
            if actor is None:
                break
            turns += 1
            events.append(_ev("turn", actor=actor.id, value=turns,
                              detail=f"hp{actor.hp}"))
            events += tick_start(actor)
            if not actor.alive:
                check_deaths()
                actor.gauge -= 100
                continue
            frozen = get_status(actor, "freeze")
            if frozen:
                actor.gauge = 0
                frozen.turns -= 1
                if frozen.turns <= 0:
                    actor.statuses = [s for s in actor.statuses if s.type != "freeze"]
                actor.last_skill = None
                events.append(_ev("turn", actor=actor.id, detail="frozen skip"))
            else:
                actor.gauge -= 100
                foes = enemies if actor.team == "hero" else heroes
                target = _pick_target(actor, foes)
                if target is not None:
                    skill = (actor.skills[actor.rotation_index % len(actor.skills)]
                             if actor.skills else "combo_strike")
                    actor.rotation_index += 1
                    events += resolve_skill(actor, target, skill)
            events += tick_end(actor)
            check_deaths()
            if turns >= max_turns:
                break

    hero_alive = any(h.alive for h in heroes)
    enemy_alive = any(x.alive for x in enemies)
    winner = ("hero" if hero_alive and not enemy_alive else
              "enemy" if enemy_alive and not hero_alive else "draw")
    return {
        "winner": winner,
        "turns": turns,
        "survivors": {e.id: e.hp for e in order if e.alive},
        "final_hp": {e.id: e.hp for e in order},
        "events": events,
    }
