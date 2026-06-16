// 시나리오의 이동 명령을 초기 상태에 순차 적용해 최종 상태를 돌려준다
const { createInitialState, cloneState } = require("./state");
const applyMove = require("./movement");

function runScenario(scenario) {
  let state = createInitialState();
  for (const move of scenario.moves) {
    state = applyMove(cloneState(state), move);
  }
  return state;
}

exports.runScenario = runScenario;
