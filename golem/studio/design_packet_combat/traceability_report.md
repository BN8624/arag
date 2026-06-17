# traceability_report (traceability.json에서 생성)

| REQ | text | modules | tests | status |
|---|---|---|---|---|
| RULE-01 | Poison deals 5 damage at the start of ev | src/unit_logic.js | SCN-001 | covered |
| RULE-02 | If not stunned, gauge increases by 'spee | src/game_engine.js | SCN-002 | covered |
| RULE-03 | Action triggers when gauge >= 100. Prior | src/game_engine.js | SCN-002 | covered |
| RULE-04 | ATTACK: If distance <= 1 and energy >= 2 | src/unit_logic.js | SCN-002 | covered |
| RULE-05 | MOVE: If 0 <= newPos <= 10 and energy >= | src/unit_logic.js | SCN-002 | covered |
| RULE-06 | WAIT: energy += 20 (capped at 100). | src/unit_logic.js | SCN-002 | covered |
| RULE-07 | Every action (Success or Fail) reduces g | src/unit_logic.js | SCN-002 | covered |
| RULE-08 | Stun prevents gauge gain and action exec | src/unit_logic.js, src/game_engine.js | SCN-001 | covered |
| RULE-09 | Game ends immediately when any unit's HP | src/game_engine.js | SCN-003 | covered |
