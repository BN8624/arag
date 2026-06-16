# 08_questions — 질문 처리 (§6 분류)

## 해소된 결정(decisions) 9
- Every player action (UPGRADE, COOL, WAIT) constitutes exactly one turn.
- The precise sequence of a turn is: 1. Execute Action (subtract cost, modify level/heat), 2. End-of-Turn Heat Increase, 3. Energy Production Calculation (throttled based on current heat), 4. Win/Loss Condition Check.
- Energy production for a turn uses the generator level after an UPGRADE action is processed.
- The heat threshold check occurs AFTER the end-of-turn heat increase has been applied to the current state.
- UPGRADE cost is calculated using the generator level at the start of the action (before the increment).
- A 'STALLED' state (loss condition) is triggered if the game is not won, energy production floors to 0, and the current energy is less than the cost of any available action (COOL or UPGRADE).
- The 'stalling' output is reflected by setting the state status to 'STALLED' and adding a log entry.
- All multipliers (Energy production: 2, Heat generation: 1, Throttle: 0.1) are moved into the config object for full determinism and visibility.
- Logs are stored as a simple array of strings.

## ASSUMED(가정 고정) 2
- The player starts with 0 energy and Level 1, requiring WAIT actions to begin.
- The 'floor' operation for throttled production refers to Math.floor().

## DEFERRED(후속 미룸) 2
- UI/UX improvements for the CLI output.
- Customizable scenario files beyond basic CLI flags.
