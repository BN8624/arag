const fs = require('fs');
const { processTurn } = require('./src/engine');

function main() {
  const args = process.argv.slice(2);
  const scenarioIdxArg = args.indexOf('--scenario');
  if (scenarioIdxArg === -1) return;

  const scenarioNum = parseInt(args[scenarioIdxArg + 1], 10);
  const scenarios = JSON.parse(fs.readFileSync('./scenarios.json', 'utf8'));
  const scenario = scenarios[scenarioNum - 1];

  if (!scenario) return;

  const setup = scenario.setup;
  let gameState = {
    energy: setup.energy,
    heat: setup.heat,
    generatorLevel: setup.generatorLevel,
    config: setup.config,
    status: 'RUNNING',
    turn: 0,
    logs: []
  };

  const inputs = scenario.input || [];
  for (const action of inputs) {
    gameState = processTurn(action, gameState);
    if (gameState.status === 'WON' || gameState.status === 'STALLED') {
      break;
    }
  }

  console.log(`turn: ${gameState.turn}`);
  console.log(`energy: ${gameState.energy}`);
  console.log(`heat: ${gameState.heat}`);
  console.log(`generatorLevel: ${gameState.generatorLevel}`);
  console.log(`status: ${gameState.status}`);
  console.log(`logs: ${JSON.stringify(gameState.logs)}`);
}

main();
