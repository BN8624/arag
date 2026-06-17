# system_design

## main.js
- 책임: Entry point. Initializes global game state including unit attributes (HP, speed, energy, position) and triggers the game engine loop.
- 입력: Initial Config
- 출력: Initialized Global State
- 금지: Game loop orchestration, action logic, status effect calculations

## src/game_engine.js
- 책임: Orchestrates the game loop ticks. Manages gauge increments based on unit speed, applies state deltas from unit_logic, and monitors win conditions.
- 입력: Global State, Command Queue
- 출력: Updated Global State
- 금지: Direct implementation of action logic, direct status effect calculations

## src/unit_logic.js
- 책임: Pure logic provider. Calculates state deltas for status effect applications (Poison, Stun) and action execution (ATTACK, MOVE, WAIT).
- 입력: Unit State, Target State, Action Parameters
- 출력: State Delta Object { hpDelta: number, energyDelta: number, posDelta: number, gaugeDelta: number, stunDelta: number, log: string, success: boolean }
- 금지: Direct state mutation, External I/O, Tick orchestration

