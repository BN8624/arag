# 08_questions — 질문 처리 (§6 분류)

## 해소된 결정(decisions) 12
- Tie-breaking: If multiple units reach gauge >= 100 in the same tick, the Player always executes first, followed by the Enemy.
- Gauge Handling: When an action triggers, subtract 100 from the gauge rather than resetting to 0 to preserve overflow.
- Action Failure: If an action fails (e.g., out of energy or range), the gauge is still reduced by 100, treating it as a wasted turn.
- Tick Order of Operations: 1. Process Poison (HP reduction) -> 2. Increment Gauges (by Speed) -> 3. Execute Actions (if gauge >= 100) -> 4. Decrement Status Durations (Stun).
- Map Boundaries: The game takes place on a 1D axis from 0 to 10. MOVE actions that would move a unit outside this range fail.
- Movement: A MOVE action changes position by exactly +1 or -1 based on the direction input.
- Numerical Values: ATTACK costs 20 Energy and deals 20 Damage. MOVE costs 10 Energy. WAIT restores 20 Energy. Poison deals 5 Damage per tick.
- Combat Range: ATTACK is successful only if absolute distance between units is <= 1.
- Energy System: The Energy system is confirmed as a core mechanic. Units start with 50 Energy.
- Input Mechanism: For CLI scenario execution, input is provided as a pre-defined queue of commands associated with the player's turns.
- Stun Logic: Stunned units do not gain gauge and cannot execute actions. Stun duration decrements by 1 at the end of every tick.
- Single Source of Truth: The 'data_contract.rules' section of this document supersedes all previous GDD and Requirement drafts.

## ASSUMED(가정 고정) 3
- Maximum energy capacity is hard-capped at 100.
- Input queue for scenarios is an array of commands mapped to Player action triggers.
- Unit speed is a constant integer and does not change during the game.

## DEFERRED(후속 미룸) 3
- Implementation of a more complex AI (currently simple deterministic distance-based AI).
- Multiple status effect types beyond Poison and Stun.
- Variable damage values or critical hits (requires RNG, out of scope).
