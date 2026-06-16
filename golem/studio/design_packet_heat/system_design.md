# system_design

## src/config.js
- 책임: Provides centralized, immutable game constants used for costs, multipliers, and thresholds.
- 입력: none
- 출력: CONFIG
- 금지: State mutation or business logic

## src/game_logic.js
- 책임: Pure functions implementing player actions, end-of-turn physics (heat/energy), and state status evaluation.
- 입력: gameState, CONFIG
- 출력: updatedGameState, actualProd
- 금지: I/O operations or orchestration of turn order

## src/engine.js
- 책임: Orchestrates the game loop: injects config, executes logic sequence (action -> mechanics -> rules), and manages state flow.
- 입력: actionType, gameState
- 출력: finalGameState
- 금지: Hardcoded game constants or direct physics calculations

