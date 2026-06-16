// 이동 명령을 받아 플레이어 좌표·턴·로그를 갱신한 새 상태를 돌려준다
const DELTA = {
  MOVE_EAST: [1, 0],
  MOVE_WEST: [-1, 0],
  MOVE_NORTH: [0, -1],
  MOVE_SOUTH: [0, 1],
};

function applyMove(state, move) {
  const d = DELTA[move] || [0, 0];
  state.player.x += d[0];
  state.player.y += d[1];
  state.turn += 1;
  state.log.push(move);
  return state;
}

exports.applyMove = applyMove;
