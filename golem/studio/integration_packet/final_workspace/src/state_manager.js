const utils = require('./utils');

exports.checkWinCondition = (state) => {
  if (state.energy >= 1000) {
    return { ...state, gameStatus: 'WON' };
  }
  return state;
};

exports.applyWait = (state, constants) => {
  const productionRate = utils.calculateProduction(state.levels, constants);
  return {
    ...state,
    turn: state.turn + 1,
    energy: state.energy + productionRate
  };
};

exports.applyUpgrade = (state, action, constants) => {
  const id = action.id;
  if (!constants[id]) {
    return {
      ...state,
      logs: [...state.logs, 'Invalid generator ID']
    };
  }

  const config = constants[id];
  const currentLevel = state.levels[id] || 0;
  const cost = utils.calculateCost(config.baseCost, config.costMultiplier, currentLevel);

  if (state.energy >= cost) {
    const newLevels = { ...state.levels };
    newLevels[id] = currentLevel + 1;
    return {
      ...state,
      energy: state.energy - cost,
      levels: newLevels
    };
  } else {
    return {
      ...state,
      logs: [...state.logs, 'Insufficient energy']
    };
  }
};
