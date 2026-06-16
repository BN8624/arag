# golem 로그라이크 부품1 카드 — 부품0(던전+이동) 위에 적 엔티티 + 결정적 추격 이동 확장
"""부품1 = 부품0 위에 적 하나 추가. 매 명령마다 플레이어가 먼저 한 칸(부품0 규칙) 후 적이
플레이어 쪽으로 한 칸 결정적 추격. 적은 플레이어 칸·벽·경계엔 못 들어감(전투는 부품2).
출력 = x,y,steps + enemy_x,enemy_y. 확장 런: driver --card rogue-p1 --base rogue-p0. 키 안 씀."""

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
try:
    from config import force_utf8_stdout
    force_utf8_stdout()
except Exception:  # noqa: BLE001
    pass

import game_bank
import oracle
from grade import grade

SLUG = "rogue-p1"

RULES = """\
You are EXTENDING a DETERMINISTIC dungeon engine in JavaScript (Node.js) by adding ONE enemy.
A working base (player movement on a walled grid) is provided to you; reuse it and add the enemy.
There is NO randomness anywhere: the same scenario always produces the same result.

== THE WORLD (unchanged from the base) ==
The dungeon is a rectangular grid of row strings; '#' = WALL, '.' = walkable FLOOR.
Coordinates are (x, y): x = column (0 = leftmost), y = row (0 = top). Cell at (x,y) is grid[y][x].

== PLAYER MOVE (unchanged from the base) ==
The player processes a string of commands U/D/L/R, left to right, one cell each:
U: y-1, D: y+1, L: x-1, R: x+1. If the target cell is out of bounds OR a wall, the command is
IGNORED (player stays). `steps` counts only commands that actually moved the player.

== NEW: THE ENEMY (deterministic chase) ==
There is exactly one enemy at a given start cell. The turn order for EACH command is:
  1. The player processes that one command (move or be blocked), exactly as above.
  2. THEN the enemy takes exactly one chase step toward the player's NEW position.
The enemy takes a chase step after EVERY command, including commands where the player was blocked.

A single enemy chase step (deterministic):
  Let dx = player.x - enemy.x and dy = player.y - enemy.y.
  PRIMARY axis: if |dx| >= |dy| the primary axis is HORIZONTAL (move one cell by sign(dx) in x);
               otherwise the primary axis is VERTICAL (move one cell by sign(dy) in y).
               (sign(n) is +1 if n>0, -1 if n<0, 0 if n==0. On a tie |dx|==|dy|, primary is HORIZONTAL.)
  SECONDARY axis is the other axis (move one cell by the sign of that axis's delta).
  Try the PRIMARY target cell first, then the SECONDARY:
    - A candidate move is valid only if the target cell is in bounds, is NOT a wall, and is NOT the
      player's current cell (the enemy may never step onto the player — combat comes later).
    - A candidate whose axis delta is 0 (sign 0, no movement) is skipped.
    - Move the enemy to the FIRST valid candidate. If neither is valid, the enemy stays in place.

== OUTPUT CONTRACT (must match EXACTLY) ==
- Runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- Print EXACTLY these five lines and NOTHING else, in this order:
      x: <final player x>
      y: <final player y>
      steps: <commands that actually moved the player>
      enemy_x: <final enemy x>
      enemy_y: <final enemy y>

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm, network, filesystem, stdin/prompts. No Math.random.
- Multi-file CommonJS (require / module.exports), entry point main.js, files must require each other.

== INPUT (per scenario; hardcode the scenarios below) ==
Each scenario input = { "grid": <row strings>, "start": [x,y], "enemy": [x,y], "moves": "<U/D/L/R>" }.

== WORKED TRACE of Scenario 1 ==
grid = ["#####","#...#","#...#","#...#","#####"], start = [1,1], enemy = [3,3], moves = "DD".
  command D #1: player target (1,2) is floor -> player moves to (1,2), steps=1.
                enemy chase toward (1,2): dx=1-3=-2, dy=2-3=-1, |dx|>=|dy| -> horizontal, sign(dx)=-1,
                target (2,3) is floor and not the player's cell -> enemy moves to (2,3).
  command D #2: player target (1,3) is floor -> player moves to (1,3), steps=2.
                enemy chase toward (1,3): dx=1-2=-1, dy=3-3=0, |dx|>=|dy| -> horizontal, sign(dx)=-1,
                target (1,3) IS the player's cell -> invalid. secondary axis delta dy=0 -> skipped.
                enemy stays at (2,3).
  Output: x:1 / y:3 / steps:2 / enemy_x:2 / enemy_y:3.

== FILES (multi-file required) ==
Keep dungeon.js (grid/wall helpers) from the base. Extend engine.js to also move the enemy each
command, and main.js to carry the enemy start and print the two enemy lines. main.js requires the others.
"""

# 레퍼런스: dungeon.js는 부품0 그대로, engine.js에 추격 추가, main.js에 적 출력 추가.
REF = {
"dungeon.js": """\
// 던전 격자 유틸 — 경계 판정 + 벽('#')/경계밖 판정 ('.'=바닥, 격자 밖은 벽 취급)
function inBounds(grid, x, y) {
  return y >= 0 && y < grid.length && x >= 0 && x < grid[y].length;
}
function isBlocked(grid, x, y) {
  if (!inBounds(grid, x, y)) return true;
  return grid[y][x] === '#';
}
module.exports = { inBounds, isBlocked };
""",
"engine.js": """\
// 플레이어 이동(부품0) + 적 결정적 추격 — 명령마다 플레이어 한 칸 후 적이 플레이어 쪽 한 칸. 결정적.
const { isBlocked } = require('./dungeon');
const DELTA = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] };
const sign = n => (n > 0 ? 1 : (n < 0 ? -1 : 0));

// 적이 플레이어(px,py)를 향해 한 칸. 1차축(|dx|>=|dy|=수평) 막히면 2차축. 플레이어칸/벽/경계 불가.
function chaseStep(grid, ex, ey, px, py) {
  const dx = px - ex, dy = py - ey;
  const horiz = [sign(dx), 0], vert = [0, sign(dy)];
  const primary = Math.abs(dx) >= Math.abs(dy) ? horiz : vert;
  const secondary = primary === horiz ? vert : horiz;
  for (const [mx, my] of [primary, secondary]) {
    if (mx === 0 && my === 0) continue;
    const nx = ex + mx, ny = ey + my;
    if (isBlocked(grid, nx, ny)) continue;
    if (nx === px && ny === py) continue;   // 플레이어 칸엔 못 들어감(전투는 부품2)
    return { x: nx, y: ny };
  }
  return { x: ex, y: ey };
}

function run(grid, start, enemyStart, moves) {
  let x = start[0], y = start[1], steps = 0;
  let ex = enemyStart[0], ey = enemyStart[1];
  for (const m of moves) {
    const d = DELTA[m];
    if (d) {
      const nx = x + d[0], ny = y + d[1];
      if (!isBlocked(grid, nx, ny)) { x = nx; y = ny; steps += 1; }
    }
    const e = chaseStep(grid, ex, ey, x, y);   // 플레이어 새 위치 기준 추격
    ex = e.x; ey = e.y;
  }
  return { x, y, steps, ex, ey };
}
module.exports = { run, chaseStep };
""",
"main.js": """\
// 던전 부품1 진입점 — 시나리오(지도+시작+적+이동)를 결정적 실행해 플레이어·적 최종위치 출력
const { run } = require('./engine');

const SCENARIOS = {
  "1": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], enemy: [3,3], moves: "DD" },
  "2": { grid: ["#####","#...#","#.#.#","#...#","#####"], start: [1,1], enemy: [3,3], moves: "RRDD" },
  "3": { grid: ["#####","#...#","#...#","#...#","#####"], start: [3,3], enemy: [1,1], moves: "UULL" },
  "4": { grid: ["######","#....#","#.##.#","#....#","#....#","######"], start: [1,1], enemy: [4,4], moves: "RRDD" }
};

function main() {
  const args = process.argv.slice(2);
  let idx = null;
  const eq = args.find(a => a.startsWith('--scenario='));
  if (eq) idx = eq.split('=')[1];
  else { const k = args.indexOf('--scenario'); if (k >= 0) idx = args[k + 1]; }
  const s = SCENARIOS[idx];
  if (!s) return;
  const r = run(s.grid, s.start, s.enemy, s.moves);
  process.stdout.write(`x: ${r.x}\\ny: ${r.y}\\nsteps: ${r.steps}\\nenemy_x: ${r.ex}\\nenemy_y: ${r.ey}\\n`);
}
main();
""",
}

SCENARIO_INPUTS = {
    "1": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "enemy": [3,3], "moves": "DD"},
    "2": {"grid": ["#####","#...#","#.#.#","#...#","#####"], "start": [1,1], "enemy": [3,3], "moves": "RRDD"},
    "3": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [3,3], "enemy": [1,1], "moves": "UULL"},
    "4": {"grid": ["######","#....#","#.##.#","#....#","#....#","######"], "start": [1,1], "enemy": [4,4], "moves": "RRDD"},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "로그라이크 부품1 — 적 엔티티 + 결정적 추격",
        "genre": "roguelike",
        "mechanics": "grid,movement,enemy,deterministic-chase,turn-order",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},
        "reference": REF,
        "notes": "부품0(rogue-p0) 확장 = 적 추격. 전투는 부품2. 확장 런: --base rogue-p0.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): "
              f"x={g.get('x')} y={g.get('y')} steps={g.get('steps')} "
              f"enemy=({g.get('enemy_x')},{g.get('enemy_y')})")

    with tempfile.TemporaryDirectory(prefix="golem_rogue1_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
