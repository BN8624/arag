# 08_questions — 질문 처리 (§6 분류)

## 해소된 결정(decisions) 9
- Support multiple generator types to resolve the conflict between 'Upgrade ID' and 'generatorLevel'.
- The game state will track levels in a map `stats.levels` where keys are Generator IDs and values are integers.
- The upgrade cost formula is: currentCost = floor(baseCost * (costMultiplier ^ currentLevel)).
- The total productionRate is calculated as: 1 (base) + sum(generatorLevel * power) for all generators.
- The 'turn' counter only increments during a 'WAIT' action; 'UPGRADE' actions do not advance the turn.
- Invalid actions or non-existent Upgrade IDs will be logged as 'Invalid action/ID' and skipped without changing state.
- The scenario runner will stop processing actions immediately once 'gameStatus' transitions to 'WON'.
- Scenario data will be stored in a `scenarios.json` file, where each key is a scenario ID and its value is an array of action objects.
- If the CLI argument '--scenario N' refers to a non-existent scenario, the program will log 'Scenario not found' and exit with process.exit(1).

## ASSUMED(가정 고정) 3
- The scenario sequence is provided as a JSON file read by main.js.
- Generator definitions (baseCost, costMultiplier, power) are hardcoded constants within engine.js.
- The base production rate before any upgrades is exactly 1.

## DEFERRED(후속 미룸) 2
- Adding multiple types of generators with different scaling curves.
- Implementing a more complex scenario language.
