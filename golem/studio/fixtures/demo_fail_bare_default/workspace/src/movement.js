// (의도적 결함) named export가 아니라 module.exports=function (bare default) 사용
module.exports = function applyMove(state, move) {
  const delta = { MOVE_EAST: [1, 0], MOVE_WEST: [-1, 0] };
  const d = delta[move] || [0, 0];
  state.player.x += d[0];
  state.player.y += d[1];
  state.turn += 1;
  state.log.push(move);
  return state;
};
