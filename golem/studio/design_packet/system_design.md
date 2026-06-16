# system_design

## src/utils.js
- 책임: Storage of static game configuration and pure functions for calculating costs (RULE-03) and total production rates (RULE-04).
- 입력: current levels (map/array), config constants
- 출력: number (cost or production)
- 금지: state mutation, I/O

## src/state_manager.js
- 책임: State transition logic for WAIT (RULE-01), UPGRADE (RULE-02), and victory detection (RULE-05).
- 입력: currentState, action, generatorId
- 출력: updatedState
- 금지: scenario sequencing, I/O

## src/engine.js
- 책임: Orchestrates the execution of a scenario sequence and enforces the stop-on-win rule (RULE-06).
- 입력: initialState, actionSequence
- 출력: finalState
- 금지: direct cost calculation, state transition logic

## main.js
- 책임: Entry point that initializes the game state and invokes the engine to process specific scenarios.
- 입력: none
- 출력: scenario results
- 금지: game logic, state transitions, cost calculation

