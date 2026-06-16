const fs = require('fs');
const engine = require('./src/engine');
const utils = require('./src/utils');

const args = process.argv.slice(2);
const scenarioFlagIndex = args.indexOf('--scenario');
const scenarioNum = scenarioFlagIndex !== -1 ? args[scenarioFlagIndex + 1] : null;

if (scenarioNum) {
  const scenariosData = JSON.parse(fs.readFileSync('scenarios.json', 'utf8'));
  const scenario = scenariosData[parseInt(scenarioNum, 10) - 1];

  if (scenario) {
    const constants = { ...utils.CONFIG, ...scenario.constants };
    
    const initialState = {
      turn: scenario.initialState?.turn ?? 0,
      energy: scenario.initialState?.energy ?? 0,
      levels: { ...(scenario.initialState?.levels || {}) },
      gameStatus: scenario.initialState?.gameStatus ?? 'PLAYING',
      logs: []
    };

    const actions = scenario.actions || [];
    const finalState = engine.processScenario(initialState, actions, constants);
    const finalProductionRate = utils.calculateProduction(finalState.levels, constants);

    process.stdout.write(`turn: ${finalState.turn}\n`);
    process.stdout.write(`energy: ${finalState.energy}\n`);
    process.stdout.write(`productionRate: ${finalProductionRate}\n`);
    process.stdout.write(`gameStatus: ${finalState.gameStatus}\n`);
    process.stdout.write(`logs: ${JSON.stringify(finalState.logs)}\n`);
  }
}
