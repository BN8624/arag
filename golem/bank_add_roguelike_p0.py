# golem 로그라이크 부품0 카드 적재 — 던전 격자 + 결정적 이동(벽/경계 막힘). 큰 게임의 씨앗 부품
"""부품0 = 격자 던전에서 플레이어가 고정 명령 시퀀스대로 이동, 벽/경계면 무시(제자리).
출력 = 최종 위치(x,y) + steps(실제 이동 수). 다음 부품(적·전투·아이템·층)이 이 위에 --base로 얹힌다.
레퍼런스(REF, Claude)로 골든을 구성적 생성(golden_from_reference) + self-채점 검증. 키 안 씀."""

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

SLUG = "rogue-p0"

# G12 교훈 적용: 좌표계·방향·막힘·steps·출력형식을 빈틈없이 명시 + 시나리오1 워크드 트레이스.
RULES = """\
You are implementing a DETERMINISTIC dungeon movement engine in JavaScript (Node.js).
There is NO randomness anywhere: the same scenario always produces the same result.

== THE WORLD ==
The dungeon is a rectangular grid given as an array of equal-length strings (the rows).
Each character is either '#' (a WALL) or '.' (walkable FLOOR).
Coordinates are (x, y): x = column index (0 = leftmost), y = row index (0 = top row).
So the character at position (x, y) is grid[y][x]. The player always starts on a floor cell.

== A MOVE ==
The player is given a string of move commands, each one of: U, D, L, R. Process them LEFT TO RIGHT,
one command at a time. Each command tries to move the player exactly one cell:
- U = decrease y by 1 (up).   D = increase y by 1 (down).
- L = decrease x by 1 (left). R = increase x by 1 (right).
For each command, look at the TARGET cell the player would move into:
- If the target cell is OUTSIDE the grid (out of bounds) OR is a WALL ('#'), the command is IGNORED:
  the player does NOT move and stays exactly where it was.
- Otherwise the player moves onto the target floor cell.

== STEPS ==
`steps` counts the number of commands that resulted in an ACTUAL move. Commands that were ignored
(blocked by a wall or the grid boundary) are NOT counted.

== OUTPUT CONTRACT (must match EXACTLY) ==
- The program must be runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- It must print EXACTLY these three lines and NOTHING else, in this order:
      x: <final x>
      y: <final y>
      steps: <number of commands that actually moved the player>

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm packages, no network, no filesystem, no stdin/prompts. No Math.random.
- Multi-file using CommonJS (require / module.exports). At minimum: dungeon.js, engine.js, main.js.
  The files MUST actually require each other (no dead files). Entry point is main.js.

== INPUT (per scenario; hardcode the scenarios given below) ==
Each scenario input = { "grid": <array of row strings>, "start": [x, y], "moves": "<string of U/D/L/R>" }.

== WORKED TRACE of Scenario 1 (so the semantics are unambiguous) ==
grid = ["#####","#...#","#...#","#...#","#####"], start = [1,1], moves = "RRDD".
  start at (1,1).
  R -> target (2,1) = grid[1][2] = '.' floor -> move. now (2,1), steps 1.
  R -> target (3,1) = grid[1][3] = '.' floor -> move. now (3,1), steps 2.
  D -> target (3,2) = grid[2][3] = '.' floor -> move. now (3,2), steps 3.
  D -> target (3,3) = grid[3][3] = '.' floor -> move. now (3,3), steps 4.
  Output: x: 3 / y: 3 / steps: 4.

== FILES (multi-file required) ==
At minimum: dungeon.js (grid helpers: bounds check, wall check), engine.js (apply the move sequence
and count steps), main.js (the hardcoded scenarios + run + printing). main.js must require the others.
"""

REF = {
"dungeon.js": """\
// 던전 격자 유틸 — 경계 판정 + 벽('#')/경계밖 판정 ('.'=바닥, 격자 밖은 벽 취급)
function inBounds(grid, x, y) {
  return y >= 0 && y < grid.length && x >= 0 && x < grid[y].length;
}
function isBlocked(grid, x, y) {
  if (!inBounds(grid, x, y)) return true;   // 격자 밖 = 막힘
  return grid[y][x] === '#';                // 벽 = 막힘
}
module.exports = { inBounds, isBlocked };
""",
"engine.js": """\
// 플레이어 이동 적용 — 명령마다 한 칸, 막히면 무시(제자리), steps=실제 이동 수. 결정적.
const { isBlocked } = require('./dungeon');
const DELTA = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] };

function run(grid, start, moves) {
  let x = start[0], y = start[1], steps = 0;
  for (const m of moves) {
    const d = DELTA[m];
    if (!d) continue;
    const nx = x + d[0], ny = y + d[1];
    if (isBlocked(grid, nx, ny)) continue;   // 벽/경계 = 명령 무시
    x = nx; y = ny; steps += 1;
  }
  return { x, y, steps };
}
module.exports = { run };
""",
"main.js": """\
// 던전 부품0 진입점 — 시나리오(지도+시작+이동)를 결정적 실행해 최종 위치·steps 출력
const { run } = require('./engine');

const SCENARIOS = {
  "1": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], moves: "RRDD" },
  "2": { grid: ["#####","#...#","#.#.#","#...#","#####"], start: [1,1], moves: "RDLD" },
  "3": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], moves: "UULL" },
  "4": { grid: ["######","#....#","#.##.#","#....#","#....#","######"], start: [1,1], moves: "RRDDLLU" }
};

function main() {
  const args = process.argv.slice(2);
  let idx = null;
  const eq = args.find(a => a.startsWith('--scenario='));
  if (eq) idx = eq.split('=')[1];
  else { const k = args.indexOf('--scenario'); if (k >= 0) idx = args[k + 1]; }
  const s = SCENARIOS[idx];
  if (!s) return;
  const r = run(s.grid, s.start, s.moves);
  process.stdout.write(`x: ${r.x}\\ny: ${r.y}\\nsteps: ${r.steps}\\n`);
}
main();
""",
}

SCENARIO_INPUTS = {
    "1": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "moves": "RRDD"},
    "2": {"grid": ["#####","#...#","#.#.#","#...#","#####"], "start": [1,1], "moves": "RDLD"},
    "3": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "moves": "UULL"},
    "4": {"grid": ["######","#....#","#.##.#","#....#","#....#","######"], "start": [1,1], "moves": "RRDDLLU"},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "로그라이크 부품0 — 던전 격자 + 결정적 이동",
        "genre": "roguelike",
        "mechanics": "grid,movement,wall-collision,bounds,deterministic,steps",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},
        "reference": REF,
        "notes": "로그라이크 부품0(씨앗). 다음 부품(적·전투·아이템·층)이 --base로 이 위에 얹힌다.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): "
              f"x={g.get('x')} y={g.get('y')} steps={g.get('steps')}")

    with tempfile.TemporaryDirectory(prefix="golem_rogue0_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
