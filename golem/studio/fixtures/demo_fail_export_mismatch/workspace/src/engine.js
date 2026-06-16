// (의도적 결함) export 이름이 매니페스트(runScenario)와 어긋난다 — runScene으로 내보냄
const { createInitialState, cloneState } = require("./state");
const { applyMove } = require("./movement");

function runScenario(scenario) {
  let state = createInitialState();
  for (const move of scenario.moves) {
    state = applyMove(cloneState(state), move);
  }
  return state;
}

exports.runScene = runScenario;
