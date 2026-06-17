const gameLogic = require('./game_logic');
const { CONFIG } = require('./config');

exports.processTurn = function(actionType, gameState) {
  const config = gameState.config || CONFIG;
  
  // 1. Handle Action
  let state = gameLogic.handleAction(gameState, actionType, config);

  // 2. End-of-Turn Physics (Energy then Heat)
  const { newState, actualProd } = gameLogic.applyEndTurnEffects(state, config);
  state = newState;

  // 3. Evaluate Status
  state.status = gameLogic.checkStatus(state, actualProd, config);
  
  // 4. Increment Turn
  state.turn += 1;

  return state;
};
