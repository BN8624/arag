// 데모 워크스페이스 진입점 — engine.runScenario를 호출해 최종 상태를 출력한다
const { runScenario } = require("./src/engine");

const result = runScenario({ moves: ["MOVE_EAST", "MOVE_EAST", "MOVE_SOUTH"] });
console.log(JSON.stringify(result));
