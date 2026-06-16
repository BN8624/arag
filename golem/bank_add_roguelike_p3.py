# golem 로그라이크 부품3 카드 — 부품2(전투) 위에 아이템·포션·함정·계단을 한 번에(큰 걸음) 확장
"""부품3 = 부품2 위에 던전 요소 묶음 추가(여러 메카닉 동시 = 통합 frontier 직격). 격자에 새 칸:
$=골드(10), !=포션(줍기), ^=함정(밟으면 3뎀, 1회성), >=계단(올라서면 하강·런 종료). 새 명령 Q=포션
마시기(HP +5, 최대치 캡). 전부 한 칸 단위로 전투(부품2)와 동시에 돈다. 출력에 gold/potions/descended
추가. 확장 런: driver --card rogue-p3 --base rogue-p2. 적재는 키 안 씀."""

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

SLUG = "rogue-p3"

RULES = """\
You are EXTENDING a DETERMINISTIC dungeon engine in JavaScript (Node.js) by adding ITEMS, TRAPS,
a POTION action, and STAIRS. A working base (player movement + chasing enemy + COMBAT) is provided;
reuse it and add the new mechanics. NO randomness: same scenario always produces the same result.

== THE WORLD (extended) ==
The dungeon is a rectangular grid of row strings. Cell characters:
  '#' = WALL (blocks movement)            '.' = plain walkable FLOOR
  '$' = GOLD pickup (walkable)            '!' = POTION pickup (walkable)
  '^' = TRAP (walkable)                   '>' = STAIRS DOWN (walkable)
Everything EXCEPT '#' is walkable (for both player and enemy). Coordinates (x,y): x=column, y=row,
cell at (x,y) is grid[y][x]. Only '#' (and out of bounds) blocks movement.

== PLAYER, ENEMY, COMBAT (unchanged from the base) ==
Player & enemy have hp/atk. HP floors at 0; hp 0 = DEAD. Per command: PLAYER phase then ENEMY phase.
PLAYER moving into the enemy's cell = ATTACK (enemy_hp -= player_atk, no move, not a step).
ENEMY phase (only if enemy alive): if orthogonally adjacent (Manhattan dist == 1) it ATTACKS
(player_hp -= enemy_atk, no move); else it takes one chase step (base rule: primary axis HORIZONTAL
if |dx|>=|dy| else VERTICAL, tie->HORIZONTAL; try primary then secondary; valid = in bounds, not '#',
not the player's cell; skip an axis with delta 0; first valid, else stay).

== NEW: COMMANDS, ITEMS, TRAPS, STAIRS ==
The move string may now contain U/D/L/R AND 'Q'. Fixed constants: GOLD '$' = 10 gold each;
TRAP '^' deals 3 damage; POTION heal = 5; the player's MAX hp = its starting player_hp.

For EACH command, before processing: if the player is DEAD (player_hp == 0) OR has already
descended the stairs, STOP — all remaining commands are ignored.
  PHASE 1 - PLAYER:
    - 'Q' (quaff): if the player holds >= 1 potion, consume one (potions -= 1) and heal:
      player_hp = min(max_hp, player_hp + 5). If no potion, nothing happens. Q is NOT a move
      (no step, no position change).
    - U/D/L/R: look at the target cell.
        (a) enemy ALIVE and target IS the enemy's cell -> ATTACK (as above). Not a step.
        (b) target out of bounds or '#' -> IGNORED (player stays). Not a step.
        (c) else -> MOVE onto the target cell. steps += 1. Then resolve the cell the player landed on:
              '$' -> gold += 10, the cell becomes '.' (consumed).
              '!' -> potions += 1, the cell becomes '.' (consumed).
              '^' -> player_hp = max(0, player_hp - 3), the cell becomes '.' (consumed, one-shot).
              '>' -> descended = true (the player has taken the stairs down).
  After PHASE 1: if the player just descended ('>'), STOP immediately (no enemy phase, remaining
  commands ignored).
  PHASE 2 - ENEMY: unchanged (only if enemy alive; attack if adjacent, else chase). Items/traps/
  stairs affect the PLAYER only; the enemy walks over them with no effect and never consumes them.

== OUTPUT CONTRACT (must match EXACTLY) ==
- Runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- Print EXACTLY these ten lines and NOTHING else, in this order:
      x: <final player x>
      y: <final player y>
      steps: <commands that actually moved the player>
      enemy_x: <final enemy x>
      enemy_y: <final enemy y>
      player_hp: <final player hp, floored at 0>
      enemy_hp: <final enemy hp, floored at 0>
      gold: <total gold collected>
      potions: <potions currently held>
      descended: <true|false>

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm, network, filesystem, stdin/prompts. No Math.random.
- Multi-file CommonJS (require / module.exports), entry point main.js, files must require each other.

== INPUT (per scenario; hardcode the scenarios below) ==
Each scenario input = { "grid": <row strings>, "start": [x,y], "enemy": [x,y], "moves": "<U/D/L/R/Q>",
  "player_hp": <int>, "enemy_hp": <int>, "player_atk": <int>, "enemy_atk": <int> }.

== WORKED TRACE of Scenario 1 ==
grid = ["########","#.^!$>.#","#......#","#......#","########"], start = [1,1], enemy = [6,3],
moves = "RRQRR", player_hp = 10, enemy_hp = 10, player_atk = 3, enemy_atk = 2. (max_hp = 10)
  R #1: move to (2,1) '^' -> trap: player_hp = 10-3 = 7, cell -> '.'. steps=1.
        enemy at (6,3), not adjacent -> chase toward (2,1): dx=-4,dy=-2 -> horizontal -> (5,3).
  R #2: move to (3,1) '!' -> potion: potions = 1, cell -> '.'. steps=2.
        enemy (5,3) chase toward (3,1): dx=-2,dy=-2 tie -> horizontal -> (4,3).
  Q #3: quaff: potions 1->0, player_hp = min(10, 7+5) = 10. Not a step (steps still 2).
        enemy (4,3) chase toward (3,1): dx=-1,dy=-2 -> vertical -> (4,2).
  R #4: move to (4,1) '$' -> gold = 10, cell -> '.'. steps=3.
        enemy (4,2) is adjacent to (4,1) (dist 1) -> ATTACK: player_hp = 10-2 = 8.
  R #5: move to (5,1) '>' (moving onto the stairs IS a move) -> steps=4, then descended = true.
        STOP (no enemy phase; nothing remains anyway).
  Output: x:5 / y:1 / steps:4 / enemy_x:4 / enemy_y:2 / player_hp:8 / enemy_hp:10 /
          gold:10 / potions:0 / descended:true.

== FILES (multi-file required) ==
Keep dungeon.js (only '#' blocks). Extend engine.js to carry gold/potions/descended and resolve the
new cells, the Q command, and the descend-stop; and main.js to print the three new lines. Requires.
"""

# 레퍼런스: dungeon.js는 부품2 그대로('#'만 차단), engine.js에 아이템/함정/계단/Q 추가.
REF = {
"dungeon.js": """\
// 던전 격자 유틸 — 경계 판정 + 벽('#')만 차단('.'·'$'·'!'·'^'·'>'는 모두 통행 가능)
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
// 이동+추격+전투(부품2) + 아이템($/!)·함정(^)·계단(>)·포션(Q) — 모두 한 칸 단위로 동시에. 결정적.
const { isBlocked } = require('./dungeon');
const DELTA = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] };
const sign = n => (n > 0 ? 1 : (n < 0 ? -1 : 0));
const GOLD = 10, TRAP = 3, HEAL = 5;

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
  const g = grid.map(r => r.split(''));     // 가변 사본(아이템·함정 소모용)
  let x = start[0], y = start[1], steps = 0;
  let ex = enemyStart[0], ey = enemyStart[1];
  const maxhp = stats.player_hp;
  let php = stats.player_hp, ehp = stats.enemy_hp;
  const patk = stats.player_atk, eatk = stats.enemy_atk;
  let gold = 0, potions = 0, descended = false;

  for (const m of moves) {
    if (php <= 0 || descended) break;        // 사망/하강 → 남은 명령 무시
    // PHASE 1: 플레이어
    if (m === 'Q') {
      if (potions > 0) { potions -= 1; php = Math.min(maxhp, php + HEAL); }
    } else {
      const d = DELTA[m];
      if (d) {
        const nx = x + d[0], ny = y + d[1];
        if (ehp > 0 && nx === ex && ny === ey) {
          ehp = Math.max(0, ehp - patk);      // 적 칸 = 공격
        } else if (!isBlocked(g, nx, ny)) {
          x = nx; y = ny; steps += 1;
          const c = g[y][x];                  // 밟은 칸 처리
          if (c === '$') { gold += GOLD; g[y][x] = '.'; }
          else if (c === '!') { potions += 1; g[y][x] = '.'; }
          else if (c === '^') { php = Math.max(0, php - TRAP); g[y][x] = '.'; }
          else if (c === '>') { descended = true; }
        }
      }
    }
    if (descended) break;                     // 계단 → 즉시 종료(적 페이즈 없음)
    // PHASE 2: 적
    if (ehp > 0) {
      const man = Math.abs(x - ex) + Math.abs(y - ey);
      if (man === 1) { php = Math.max(0, php - eatk); }
      else { const e = chaseStep(g, ex, ey, x, y); ex = e.x; ey = e.y; }
    }
  }
  return { x, y, steps, ex, ey, php, ehp, gold, potions, descended };
}
module.exports = { run, chaseStep };
""",
"main.js": """\
// 던전 부품3 진입점 — 시나리오(지도+시작+적+이동+HP/ATK)를 결정적 실행해 위치·HP·골드·포션·하강 출력
const { run } = require('./engine');

const SCENARIOS = {
  "1": { grid: ["########","#.^!$>.#","#......#","#......#","########"], start: [1,1], enemy: [6,3],
         moves: "RRQRR", player_hp: 10, enemy_hp: 10, player_atk: 3, enemy_atk: 2 },
  "2": { grid: ["######","#.^^.#","#....#","######"], start: [1,1], enemy: [4,2],
         moves: "RRRR", player_hp: 5, enemy_hp: 10, player_atk: 1, enemy_atk: 2 },
  "3": { grid: ["######","#.$$.#","#..!.#","######"], start: [1,1], enemy: [4,2],
         moves: "RRDD", player_hp: 10, enemy_hp: 6, player_atk: 3, enemy_atk: 2 },
  "4": { grid: ["######","#..>.#","#....#","######"], start: [1,1], enemy: [2,1],
         moves: "RRR", player_hp: 10, enemy_hp: 5, player_atk: 5, enemy_atk: 2 }
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
    `player_hp: ${r.php}\\nenemy_hp: ${r.ehp}\\ngold: ${r.gold}\\npotions: ${r.potions}\\n` +
    `descended: ${r.descended}\\n`);
}
main();
""",
}

SCENARIO_INPUTS = {
    "1": {"grid": ["########","#.^!$>.#","#......#","#......#","########"], "start": [1,1], "enemy": [6,3],
          "moves": "RRQRR", "player_hp": 10, "enemy_hp": 10, "player_atk": 3, "enemy_atk": 2},
    "2": {"grid": ["######","#.^^.#","#....#","######"], "start": [1,1], "enemy": [4,2],
          "moves": "RRRR", "player_hp": 5, "enemy_hp": 10, "player_atk": 1, "enemy_atk": 2},
    "3": {"grid": ["######","#.$$.#","#..!.#","######"], "start": [1,1], "enemy": [4,2],
          "moves": "RRDD", "player_hp": 10, "enemy_hp": 6, "player_atk": 3, "enemy_atk": 2},
    "4": {"grid": ["######","#..>.#","#....#","######"], "start": [1,1], "enemy": [2,1],
          "moves": "RRR", "player_hp": 10, "enemy_hp": 5, "player_atk": 5, "enemy_atk": 2},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "로그라이크 부품3 — 아이템·함정·계단·포션(통합 확장)",
        "genre": "roguelike",
        "mechanics": "grid,combat,items,gold,potion,trap,stairs,inventory,turn-order",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},
        "reference": REF,
        "notes": "부품2(rogue-p2) 확장 = 아이템/함정/계단/포션 묶음(큰 걸음). 확장 런: --base rogue-p2.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): "
              f"pos=({g.get('x')},{g.get('y')}) steps={g.get('steps')} "
              f"enemy=({g.get('enemy_x')},{g.get('enemy_y')}) "
              f"php={g.get('player_hp')} ehp={g.get('enemy_hp')} "
              f"gold={g.get('gold')} pot={g.get('potions')} desc={g.get('descended')}")

    with tempfile.TemporaryDirectory(prefix="golem_rogue3_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
