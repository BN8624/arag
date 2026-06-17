exports.handleAction = function(state, action, config) {
  const newState = { ...state, logs: [...state.logs] };

  if (action === 'UPGRADE') {
    const cost = newState.generatorLevel * config.upgradeBaseCost;
    if (newState.energy >= cost) {
      newState.energy -= cost;
      newState.generatorLevel += 1;
    }
  } else if (action === 'COOL') {
    const cost = config.coolCost;
    if (newState.energy >= cost) {
      newState.energy -= cost;
      newState.heat = Math.max(0, newState.heat - config.coolAmount);
    }
  } else if (action === 'WAIT') {
    // No immediate state change
  }

  return newState;
};

exports.applyEndTurnEffects = function(state, config) {
  const baseProd = state.generatorLevel * config.energyMultiplier;
  let actualProd;

  if (state.heat > config.heatThreshold) {
    actualProd = Math.floor(baseProd * config.throttleMultiplier);
  } else {
    actualProd = baseProd;
  }

  const newState = { ...state };
  newState.energy += actualProd;
  newState.heat += state.generatorLevel * config.heatMultiplier;

  return { newState, actualProd };
};

exports.checkStatus = function(state, actualProd, config) {
  if (state.energy >= config.winCondition) {
    return 'WON';
  }

  const upgradeCost = state.generatorLevel * config.upgradeBaseCost;
  const minCost = Math.min(config.coolCost, upgradeCost);

  if (actualProd === 0 && state.energy < minCost) {
    return 'STALLED';
  }

  return 'RUNNING';
};
