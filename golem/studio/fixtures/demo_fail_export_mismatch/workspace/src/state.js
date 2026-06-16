// 게임 초기 상태 생성과 상태 깊은 복제를 담당한다
function createInitialState() {
  return { turn: 0, player: { x: 1, y: 1 }, log: [] };
}

function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

exports.createInitialState = createInitialState;
exports.cloneState = cloneState;
