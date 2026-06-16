# traceability_report (traceability.json에서 생성)

| REQ | text | modules | tests | status |
|---|---|---|---|---|
| RULE-01 | WAIT action -> turn += 1, energy += prod | src/state_manager.js | SCN-001 | covered |
| RULE-02 | UPGRADE action -> check energy, deduct c | src/state_manager.js | SCN-002 | covered |
| RULE-03 | currentCost = floor(baseCost * (costMult | src/utils.js | SCN-002 | covered |
| RULE-04 | productionRate = 1 + sum(level * power). | src/utils.js | SCN-001 | covered |
| RULE-05 | If energy >= 1000, gameStatus = 'WON'. | src/state_manager.js | SCN-003 | covered |
| RULE-06 | If gameStatus == 'WON', no further actio | src/engine.js | SCN-003 | covered |
