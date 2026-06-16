# gemma 워커에게 줄 지시문(JS 전투엔진 스펙) 조립 — PAMPHLET 규칙 + 고정 시나리오 + 출력계약
"""build_prompt(self_fix_hint=None) -> str.
파이썬 T-000012 워커가 받았던 것과 동일 수준의 스펙(PAMPHLET §1~3)을 JS로 옮긴다.
정답 수치(winner/turns/hp)는 절대 넣지 않는다 — 모델이 계산해야 한다. 시나리오 파티만 준다.
self_fix_hint를 주면 직전 시도의 첫 불일치를 덧붙여 표적 수정을 유도한다."""

import json
from pathlib import Path

GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "golden" / "scenarios.json").read_text(encoding="utf-8"))

RULES = """\
You are implementing a DETERMINISTIC tempo-based RPG battle engine in JavaScript (Node.js).
There is NO randomness anywhere: the same scenario always produces the same result.

== OUTPUT CONTRACT (must match EXACTLY) ==
- The program must be runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- It must print EXACTLY these lines and nothing else:
      winner: <hero|enemy|draw>
      turns: <integer>
      <entityId>: <finalHp>      (one line per entity, in registration order: ALL heroes first, then ALL enemies)
- Final HP printed must floor at 0 (never print a negative number).

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm packages, no network, no filesystem, no stdin/prompts.
- Multi-file using CommonJS (require / module.exports). At minimum: models.js, skills.js, engine.js, main.js.
  The files MUST actually require each other (no dead files). Entry point is main.js.
- Use Math.floor for the burn 5% damage and for the shock x1.25 multiplier (integer results).

== DATA MODEL ==
Entity: { id, name, team ("hero"|"enemy"), max_hp, hp, atk, defense, spd,
          gauge (start 0), statuses (start []), last_skill (start null),
          skills (array of skill names), rotation_index (start 0) }
Status: { type ("burn"|"freeze"|"poison"|"shock"), turns, stacks (default 1) }
At battle start every entity's hp = max_hp.

== STATUS EFFECTS ==
A status ticks ONLY on the entity whose turn it is (not globally every tick):
- burn:   at the START of that entity's turn, deal floor(hp * 0.05) damage to it; then burn.turns -= 1
          (remove at 0). Lasts 3 turns when applied. Burn ticks EVEN IF the entity is frozen.
- freeze: makes the entity skip its next action (handled in the turn, see below). Applied for 1 turn.
- poison: at the END of that entity's turn, deal 8 * stacks fixed damage; then stacks -= 1
          (remove at 0). Applied with the stacks given by the skill; max 5 stacks.
- shock:  damage this entity RECEIVES is multiplied by 1.25 (floored). Lasts 2 turns; at the END of
          that entity's turn, shock.turns -= 1 (remove at 0).

== STATUS INTERACTION MATRIX (judged at the moment a status is applied) ==
- Applying freeze to a target that already has burn  -> the freeze is NULLIFIED (not applied).
- Applying burn to a target that already has freeze  -> remove the freeze first, then apply the burn.
- If, after applying, a target ends up holding BOTH burn AND freeze -> remove both and deal an
  immediate 30 damage ("evaporate"). (Edge cleanup; usually prevented by the two rules above.)
- Applying poison to a target that already has shock  -> after applying, immediately double the
  poison stacks (capped at 5).

== TEMPO TURN SYSTEM ==
- Each tick: every ALIVE entity does gauge += spd.
- Any entity with gauge >= 100 may act this tick. Among all ready (>=100) entities pick ONE by:
  (1) higher spd, then (2) lower hp, then (3) registration order (heroes list first, then enemies, by index).
- Keep resolving ready entities (re-picking each time) until none have gauge >= 100, then go to the next tick.
- Battle ends when one entire team is dead (the other team wins), or when turns reach max_turns (=100) -> "draw".

== TURN PROCESSING (for the acting entity, in this exact order) ==
1. turns += 1.  (EVERY action attempt counts: normal actions, frozen skips, AND burn-deaths.)
2. tick_start: apply burn (as above).
3. If the entity just died from burn: it is dead, do gauge -= 100, end this turn.
4. Else if the entity has freeze: SKIP the action; set gauge = 0; freeze.turns -= 1 (remove at 0);
   set last_skill = null. (Do NOT subtract 100 in this case.)
5. Else (normal action): gauge -= 100; choose target = the LIVING enemy with the lowest hp
   (tie -> lower registration index); choose skill = skills[rotation_index % skills.length];
   rotation_index += 1; resolve that skill.
6. tick_end: apply poison, then shock (as above).
7. Apply any resulting deaths.

== COMBO CHAIN ==
- Each entity remembers last_skill (the skill name it last used). After resolving a skill, set the
  actor's last_skill to that skill name.
- last_skill is CLEARED to null whenever the entity TAKES skill damage, or when it is frozen-skipped.

== DAMAGE & SKILLS ==
Base damage of a damaging hit: dmg = max(1, attacker.atk + skill_base - target.defense).
If the target currently has shock, multiply by 1.25 and floor. Apply damage, THEN apply any status the
skill grants (so a skill that grants shock does NOT shock-boost its own hit).
Skill table (skill_base in parentheses):
- ignite (5):        deal damage, then apply burn to target.
- detonate (20):     deal damage. If actor.last_skill == "ignite": use base 50 instead AND apply burn to target.
- charge (0):        no target damage; it just sets up a combo (its effect is via last_skill == "charge").
- combo_strike (12): deal damage. If actor.last_skill == "charge": strike TWICE (two separate damage applications).
- frost (4):         deal damage, then apply freeze (1 turn) to target.
- venom (3):         deal damage, then apply poison (turns 3, stacks 2) to target.
- shock_bolt (6):    deal damage, then apply shock (2 turns) to target.
"""

RESPONSE_FORMAT = """\
== RESPONSE FORMAT ==
Output ONLY the files, each introduced by a marker line exactly like this, with nothing else outside:
=== FILE: models.js ===
<file content>
=== FILE: skills.js ===
<file content>
=== FILE: engine.js ===
<file content>
=== FILE: main.js ===
<file content>
"""


def _party_block(scenarios):
    lines = ["== SCENARIOS (fixed parties — hardcode them; --scenario N picks one) ==",
             "Each entity: id, name, max_hp, atk, defense, spd, skills. (hp starts at max_hp.)"]
    for sc in sorted(scenarios, key=int):
        party = scenarios[sc]["party"]
        lines.append(f"Scenario {sc}:")
        lines.append("  heroes  = " + json.dumps(party["heroes"], ensure_ascii=False))
        lines.append("  enemies = " + json.dumps(party["enemies"], ensure_ascii=False))
    return "\n".join(lines)


def build_prompt(self_fix_hint=None, card=None):
    """card 주면 그 카드의 규칙·시나리오로, 없으면 모듈 기본(RULES + golden/scenarios.json)."""
    rules = card["rules"] if card else RULES
    scenarios = card["scenarios"] if card else GOLDEN
    parts = [rules, _party_block(scenarios), RESPONSE_FORMAT]
    if self_fix_hint:
        parts.append(
            "== PREVIOUS ATTEMPT FAILED ==\n"
            f"Your last attempt produced a wrong result. First divergence from the correct answer:\n"
            f"  {self_fix_hint}\n"
            "Find the rule you implemented wrong that causes this, fix it, and resend ALL files.")
    return "\n\n".join(parts)


if __name__ == "__main__":
    # 점검용: 프롬프트 길이·머리 출력(키 안 씀)
    p = build_prompt()
    print(f"[prompt chars={len(p)}]")
    print(p[:1200])
