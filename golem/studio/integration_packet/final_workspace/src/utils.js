exports.CONFIG = {
  gen1: { baseCost: 10, costMultiplier: 2, power: 1 }
};

exports.calculateCost = (baseCost, costMultiplier, level) => {
  return Math.floor(baseCost * Math.pow(costMultiplier, level));
};

exports.calculateProduction = (levels, constants) => {
  let totalPower = 0;
  for (const id in constants) {
    const level = levels[id] || 0;
    totalPower += level * constants[id].power;
  }
  return 1 + totalPower;
};
