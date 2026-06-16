# golem 로그라이크 부품2 카드 — 부품1(적 추격) 위에 전투(인접 공격·HP·사망) 확장
"""부품2 = 부품1 위에 전투 추가. 명령마다 플레이어 페이즈(적 칸으로 이동 시도 = 공격, 이동·step
없음) → 적 페이즈(플레이어와 직교 인접이면 공격, 아니면 부품1 추격). HP 0이면 사망: 적이 죽으면
그 칸은 그냥 바닥, 플레이어가 죽으면 남은 명령 무시. 출력 = x,y,steps,enemy_x,enemy_y,player_hp,
enemy_hp. 확장 런: driver --card rogue-p2 --base rogue-p1. 적재는 키 안 씀."""

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

SLUG = "rogue-p2"

RULES = """\
You are EXTENDING a DETERMINISTIC dungeon engine in JavaScript (Node.js) by adding COMBAT.
A working base (player movement + ONE chasing enemy on a walled grid) is provided to you; reuse it
and add combat. There is NO randomness anywhere: the same scenario always produces the same result.

== THE WORLD (unchanged from the base) ==
The dungeon is a rectangular grid of row strings; '#' = WALL, '.' = walkable FLOOR.
Coordinates are (x, y): x = column (0 = leftmost), y = row (0 = top). Cell at (x,y) is grid[y][x].

== PLAYER & ENEMY now have HP and ATK ==
Each scenario gives starting player_hp, enemy_hp, player_atk, enemy_atk (all integers).
HP is floored at 0 (never goes negative, never printed negative). An entity with hp 0 is DEAD.

== TURN ORDER (for EACH command in the move string, left to right) ==
Before processing a command: if the player is already DEAD (player_hp == 0), STOP — all remaining
commands are ignored (no further changes).
Otherwise process the command in two phases, in this exact order:

  PHASE 1 - PLAYER. Look at the command's TARGET cell (U: y-1, D: y+1, L: x-1, R: x+1):
    (a) If the enemy is ALIVE and the target cell IS the enemy's cell -> the player ATTACKS the enemy
        instead of moving: enemy_hp = max(0, enemy_hp - player_atk). The player does NOT move.
        This is NOT a step.
    (b) Else if the target cell is out of bounds OR a wall -> the command is IGNORED (player stays).
        Not a step.
    (c) Else -> the player MOVES onto the target floor cell. steps += 1.
    (Note: if the enemy is DEAD, its old cell is just floor — case (a) does not apply, so the player
     may walk onto it via case (c).)

  PHASE 2 - ENEMY (only if the enemy is ALIVE after phase 1):
    Let the enemy and player current cells be orthogonally ADJACENT iff their Manhattan distance
    |player_x - enemy_x| + |player_y - enemy_y| == 1.
    (d) If they are adjacent -> the enemy ATTACKS the player instead of moving:
        player_hp = max(0, player_hp - enemy_atk). The enemy does NOT move.
    (e) Else -> the enemy takes exactly one chase step toward the player (UNCHANGED from the base):
        dx = player.x - enemy.x, dy = player.y - enemy.y. PRIMARY axis is HORIZONTAL if |dx| >= |dy|
        else VERTICAL (sign(n) = +1 if n>0, -1 if n<0, 0 if n==0; tie |dx|==|dy| -> HORIZONTAL).
        Try PRIMARY target cell then SECONDARY; a candidate is valid only if in bounds, not a wall,
        and not the player's current cell; a candidate whose axis delta is 0 is skipped; move to the
        FIRST valid candidate, else stay.

The enemy phase happens after EVERY command (including commands where the player was blocked or
attacked), as long as the enemy is alive.

== OUTPUT CONTRACT (must match EXACTLY) ==
- Runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- Print EXACTLY these seven lines and NOTHING else, in this order:
      x: <final player x>
      y: <final player y>
      steps: <commands that actually moved the player>
      enemy_x: <final enemy x>
      enemy_y: <final enemy y>
      player_hp: <final player hp, floored at 0>
      enemy_hp: <final enemy hp, floored at 0>
  (enemy_x/enemy_y are the enemy's last position even if it is dead.)

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm, network, filesystem, stdin/prompts. No Math.random.
- Multi-file CommonJS (require / module.exports), entry point main.js, files must require each other.

== INPUT (per scenario; hardcode the scenarios below) ==
Each scenario input = { "grid": <row strings>, "start": [x,y], "enemy": [x,y], "moves": "<U/D/L/R>",
  "player_hp": <int>, "enemy_hp": <int>, "player_atk": <int>, "enemy_atk": <int> }.

== WORKED TRACE of Scenario 1 ==
grid = ["#####","#...#","#...#","#...#","#####"], start = [1,1], enemy = [2,1], moves = "RR",
player_hp = 10, enemy_hp = 5, player_atk = 3, enemy_atk = 2.
  command R #1:
    PHASE 1: target (2,1) IS the enemy's cell and enemy is alive -> player ATTACKS:
             enemy_hp = max(0, 5 - 3) = 2. Player stays at (1,1). Not a step (steps still 0).
    PHASE 2: enemy alive. adjacency |1-2|+|1-1| = 1 -> enemy ATTACKS:
             player_hp = max(0, 10 - 2) = 8. Enemy stays at (2,1).
  command R #2:
    PHASE 1: target (2,1) IS the enemy's cell, enemy alive -> player ATTACKS:
             enemy_hp = max(0, 2 - 3) = 0. Enemy is now DEAD. Player stays at (1,1). steps still 0.
    PHASE 2: enemy is dead -> skipped.
  Output: x:1 / y:1 / steps:0 / enemy_x:2 / enemy_y:1 / player_hp:8 / enemy_hp:0.

== FILES (multi-file required) ==
Keep dungeon.js (grid/wall helpers) from the base. Extend engine.js to carry HP/ATK and resolve the
two combat cases (player attacks by moving into the enemy; enemy attacks when adjacent), and main.js
to carry the per-scenario HP/ATK and print the two new hp lines. main.js requires the others.
"""

# 레퍼런스: dungeon.js는 부품1 그대로, engine.js에 전투 추가, main.js에 HP 출력 추가.
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
// 플레이어 이동 + 적 추격(부품1) + 전투(부품2) — 인접 공격·HP·사망. 결정적.
const { isBlocked } = require('./dungeon');
const DELTA = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] };
const sign = n => (n > 0 ? 1 : (n < 0 ? -1 : 0));

// 적이 플레이어(px,py)를 향해 한 칸(부품1 그대로). 1차축(|dx|>=|dy|=수평) 막히면 2차축.
function chaseStep(grid, ex, ey, px, py) {
  const dx = px - ex, dy = py - ey;
  const horiz = [sign(dx), 0], vert = [0, sign(dy)];
  const primary = Math.abs(dx) >= Math.abs(dy) ? horiz : vert;
  const secondary = primary === horiz ? vert : horiz;
  for (const [mx, my] of [primary, secondary]) {
    if (mx === 0 && my === 0) continue;
    const nx = ex + mx, ny = ey + my;
    if (isBlocked(grid, nx, ny)) continue;
    if (nx === px && ny === py) continue;
    return { x: nx, y: ny };
  }
  return { x: ex, y: ey };
}

function run(grid, start, enemyStart, moves, stats) {
  let x = start[0], y = start[1], steps = 0;
  let ex = enemyStart[0], ey = enemyStart[1];
  let php = stats.player_hp, ehp = stats.enemy_hp;
  const patk = stats.player_atk, eatk = stats.enemy_atk;

  for (const m of moves) {
    if (php <= 0) break;                 // 플레이어 사망 → 남은 명령 무시
    const d = DELTA[m];
    // PHASE 1: 플레이어
    if (d) {
      const nx = x + d[0], ny = y + d[1];
      if (ehp > 0 && nx === ex && ny === ey) {
        ehp = Math.max(0, ehp - patk);   // 적 칸으로 이동 시도 = 공격(이동·step 없음)
      } else if (!isBlocked(grid, nx, ny)) {
        x = nx; y = ny; steps += 1;
      }
    }
    // PHASE 2: 적 (살아있을 때만)
    if (ehp > 0) {
      const manhattan = Math.abs(x - ex) + Math.abs(y - ey);
      if (manhattan === 1) {
        php = Math.max(0, php - eatk);    // 인접 → 공격(이동 없음)
      } else {
        const e = chaseStep(grid, ex, ey, x, y);
        ex = e.x; ey = e.y;
      }
    }
  }
  return { x, y, steps, ex, ey, php, ehp };
}
module.exports = { run, chaseStep };
""",
"main.js": """\
// 던전 부품2 진입점 — 시나리오(지도+시작+적+이동+HP/ATK)를 결정적 실행해 위치·걸음·HP 출력
const { run } = require('./engine');

const SCENARIOS = {
  "1": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], enemy: [2,1], moves: "RR",
         player_hp: 10, enemy_hp: 5, player_atk: 3, enemy_atk: 2 },
  "2": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], enemy: [3,3], moves: "DD",
         player_hp: 10, enemy_hp: 10, player_atk: 2, enemy_atk: 3 },
  "3": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], enemy: [2,1], moves: "RR",
         player_hp: 10, enemy_hp: 3, player_atk: 3, enemy_atk: 1 },
  "4": { grid: ["#####","#...#","#...#","#...#","#####"], start: [1,1], enemy: [2,1], moves: "DDDDDD",
         player_hp: 5, enemy_hp: 10, player_atk: 1, enemy_atk: 2 }
};

function main() {
  const args = process.argv.slice(2);
  let idx = null;
  const eq = args.find(a => a.startsWith('--scenario='));
  if (eq) idx = eq.split('=')[1];
  else { const k = args.indexOf('--scenario'); if (k >= 0) idx = args[k + 1]; }
  const s = SCENARIOS[idx];
  if (!s) return;
  const r = run(s.grid, s.start, s.enemy, s.moves, s);
  process.stdout.write(
    `x: ${r.x}\\ny: ${r.y}\\nsteps: ${r.steps}\\nenemy_x: ${r.ex}\\nenemy_y: ${r.ey}\\n` +
    `player_hp: ${r.php}\\nenemy_hp: ${r.ehp}\\n`);
}
main();
""",
}

SCENARIO_INPUTS = {
    "1": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "enemy": [2,1], "moves": "RR",
          "player_hp": 10, "enemy_hp": 5, "player_atk": 3, "enemy_atk": 2},
    "2": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "enemy": [3,3], "moves": "DD",
          "player_hp": 10, "enemy_hp": 10, "player_atk": 2, "enemy_atk": 3},
    "3": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "enemy": [2,1], "moves": "RR",
          "player_hp": 10, "enemy_hp": 3, "player_atk": 3, "enemy_atk": 1},
    "4": {"grid": ["#####","#...#","#...#","#...#","#####"], "start": [1,1], "enemy": [2,1], "moves": "DDDDDD",
          "player_hp": 5, "enemy_hp": 10, "player_atk": 1, "enemy_atk": 2},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "로그라이크 부품2 — 전투(인접 공격·HP·사망)",
        "genre": "roguelike",
        "mechanics": "grid,movement,enemy,chase,combat,hp,death,turn-order",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},
        "reference": REF,
        "notes": "부품1(rogue-p1) 확장 = 전투. 확장 런: --base rogue-p1.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): "
              f"x={g.get('x')} y={g.get('y')} steps={g.get('steps')} "
              f"enemy=({g.get('enemy_x')},{g.get('enemy_y')}) "
              f"php={g.get('player_hp')} ehp={g.get('enemy_hp')}")

    with tempfile.TemporaryDirectory(prefix="golem_rogue2_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
