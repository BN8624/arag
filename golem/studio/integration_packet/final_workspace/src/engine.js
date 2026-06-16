const sm = require('./state_manager');

exports.processScenario = (initialState, actions, constants) => {
  let state = sm.checkWinCondition(initialState);

  for (const actionObj of actions) {
    if (state.gameStatus === 'WON') {
      break;
    }

    if (actionObj.action === 'WAIT') {
      state = sm.applyWait(state, constants);
    } else if (actionObj.action === 'UPGRADE') {
      state = sm.applyUpgrade(state, actionObj, constants);
    }

    state = sm.checkWinCondition(state);
  }

  return state;
};
