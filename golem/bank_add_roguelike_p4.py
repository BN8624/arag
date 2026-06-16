# golem 로그라이크 부품4 카드 — 부품3 위에 장비(무기·방어구·회복제단)를 묶어 확장(큰 걸음, 모듈 베이스)
"""부품4 = 부품3 위에 장비 3종 추가. 'W'무기(주우면 공격력 +2), 'A'방어구(주우면 방어 +1 → 적 피해 감소),
'+'회복제단(주우면 HP 최대치로 회복, 1회성). 적 피해 = max(1, 적공격 - 방어). 출력에 player_atk·defense
추가. 베이스(rogue-p3)는 모듈 구조라 워커는 주로 items 모듈 + 약간의 combat/engine만 바꾸면 된다.
확장 런: driver --card rogue-p4 --base rogue-p3. 적재는 키 안 씀."""

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

SLUG = "rogue-p4"

RULES = """\
You are EXTENDING a DETERMINISTIC dungeon engine in JavaScript (Node.js) by adding EQUIPMENT.
A working, MODULAR base (movement + chasing enemy + combat + items/traps/stairs/potion) is provided,
split into files. Reuse it and add equipment. NO randomness: same scenario -> same result.

== THE WORLD (extended from the base) ==
Grid cells, all walkable EXCEPT '#':
  '#' WALL   '.' FLOOR   '$' GOLD(=10)   '!' POTION   '^' TRAP(3 dmg)   '>' STAIRS(descend)
  NEW:  'W' WEAPON       'A' ARMOR       '+' HEAL ALTAR
Coordinates (x,y): x=column, y=row, cell at (x,y)=grid[y][x]. Only '#'/out-of-bounds block movement.

== UNCHANGED FROM THE BASE ==
Per command (U/D/L/R/Q), left to right. If the player is DEAD (hp 0) or has DESCENDED, stop (ignore
the rest). PHASE 1 player: 'Q' quaffs a potion (heal +5, capped at max hp; max hp = starting hp);
moving into the enemy's cell = ATTACK (enemy_hp -= player's CURRENT attack; not a step); out of bounds
or '#' = blocked (not a step); else MOVE (steps += 1) and resolve the landed cell. Then if descended,
stop. PHASE 2 enemy (if alive): if Manhattan-adjacent it ATTACKS, else it chase-steps (base rule).
Cell resolution from the base still applies: '$' -> gold+=10; '!' -> potions+=1; '^' -> hp-=3;
'>' -> descended=true. (Each consumed cell becomes '.'; traps/items are one-shot.)

== NEW: EQUIPMENT ==
The player has an ATTACK stat (starts = player_atk) and a DEFENSE stat (starts = 0).
When the player MOVES onto one of these cells, resolve it (the cell becomes '.'):
  'W' WEAPON: the player's attack += 2 (permanent). Future attacks into the enemy use the new attack.
  'A' ARMOR:  the player's defense += 1 (permanent).
  '+' HEAL ALTAR: the player's hp is restored to max hp (one-shot).
DEFENSE changes how hard the ENEMY hits: when the enemy attacks, player_hp -= max(1, enemy_atk - defense)
(at least 1 damage always gets through; floored at 0). The PLAYER's attack on the enemy is unchanged:
enemy_hp -= player's current attack (the enemy has no defense).

== OUTPUT CONTRACT (must match EXACTLY) ==
- Runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- Print EXACTLY these twelve lines and NOTHING else, in this order:
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
      player_atk: <final player attack stat>
      defense: <final player defense stat>

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm, network, filesystem, stdin/prompts. No Math.random.
- Multi-file CommonJS (require / module.exports), entry point main.js, files require each other.
- The base is modular; OUTPUT ONLY THE FILES YOU CHANGE OR ADD (unchanged base files are kept).

== INPUT (per scenario; hardcode the scenarios below) ==
input = { "grid": <rows>, "start": [x,y], "enemy": [x,y], "moves": "<U/D/L/R/Q>",
  "player_hp": <int>, "enemy_hp": <int>, "player_atk": <int>, "enemy_atk": <int> }.

== WORKED TRACE of Scenario 1 ==
grid = ["#######","#.WA..#","#.....#","#.....#","#######"], start=[1,1], enemy=[5,3], moves="RRRD",
player_hp=10, enemy_hp=10, player_atk=2, enemy_atk=3. (max hp=10, defense starts 0)
  R #1: move to (2,1) 'W' -> attack 2->4, cell '.'. steps=1.
        enemy (5,3) not adjacent -> chase toward (2,1): dx=-3,dy=-2 -> horizontal -> (4,3).
  R #2: move to (3,1) 'A' -> defense 0->1, cell '.'. steps=2.
        enemy (4,3) chase toward (3,1): dx=-1,dy=-2 -> vertical -> (4,2).
  R #3: move to (4,1) '.'. steps=3.
        enemy (4,2) adjacent to (4,1) -> ATTACK: player_hp -= max(1, 3-1)=2 -> 8.
  D #4: target (4,2) is the enemy -> ATTACK: enemy_hp -= 4 (boosted) -> 6. not a step.
        enemy (4,2) adjacent -> ATTACK: player_hp -= max(1, 3-1)=2 -> 6.
  Output: x:4 / y:1 / steps:3 / enemy_x:4 / enemy_y:2 / player_hp:6 / enemy_hp:6 /
          gold:0 / potions:0 / descended:false / player_atk:4 / defense:1.

== FILES ==
The base is split into dungeon/chase/combat/items/engine/main. Equipment fits mostly in the items
module (resolve 'W'/'A'/'+') plus the enemy-damage formula (defense) and two new output lines and the
new state fields. Output ONLY the files you actually change/add.
"""

# 레퍼런스(골든·데모용, 모노 스타일 run(grid,start,enemy,moves,stats)) — 부품3 + 장비.
REF = {
"dungeon.js": """\
// 던전 격자 유틸 — 경계 + 벽('#')만 차단(나머지 통행)
function inBounds(grid, x, y){ return y>=0 && y<grid.length && x>=0 && x<grid[y].length; }
function isBlocked(grid, x, y){ if(!inBounds(grid,x,y)) return true; return grid[y][x]==='#'; }
module.exports = { inBounds, isBlocked };
""",
"engine.js": """\
// 부품4 레퍼런스(모노) — 이동+추격+전투+아이템+장비. 적 피해=max(1,적공격-방어). 결정적.
const { isBlocked } = require('./dungeon');
const DELTA = { U:[0,-1], D:[0,1], L:[-1,0], R:[1,0] };
const sign = n => (n>0?1:(n<0?-1:0));
const GOLD=10, TRAP=3, HEAL=5, WEAPON=2, ARMOR=1;

function chaseStep(grid, ex, ey, px, py){
  const dx=px-ex, dy=py-ey; const horiz=[sign(dx),0], vert=[0,sign(dy)];
  const primary = Math.abs(dx)>=Math.abs(dy)?horiz:vert; const secondary = primary===horiz?vert:horiz;
  for(const [mx,my] of [primary,secondary]){
    if(mx===0&&my===0) continue;
    const nx=ex+mx, ny=ey+my;
    if(isBlocked(grid,nx,ny)) continue;
    if(nx===px&&ny===py) continue;
    return {x:nx,y:ny};
  }
  return {x:ex,y:ey};
}

function run(grid, start, enemyStart, moves, stats){
  const g = grid.map(r=>r.split(''));
  let x=start[0], y=start[1], steps=0;
  let ex=enemyStart[0], ey=enemyStart[1];
  const maxhp=stats.player_hp;
  let php=stats.player_hp, ehp=stats.enemy_hp;
  let patk=stats.player_atk; const eatk=stats.enemy_atk;
  let defense=0, gold=0, potions=0, descended=false;

  for(const m of moves){
    if(php<=0 || descended) break;
    if(m==='Q'){
      if(potions>0){ potions-=1; php=Math.min(maxhp, php+HEAL); }
    } else {
      const d=DELTA[m];
      if(d){
        const nx=x+d[0], ny=y+d[1];
        if(ehp>0 && nx===ex && ny===ey){ ehp=Math.max(0, ehp-patk); }
        else if(!isBlocked(g,nx,ny)){
          x=nx; y=ny; steps+=1;
          const c=g[y][x];
          if(c==='$'){ gold+=GOLD; g[y][x]='.'; }
          else if(c==='!'){ potions+=1; g[y][x]='.'; }
          else if(c==='^'){ php=Math.max(0, php-TRAP); g[y][x]='.'; }
          else if(c==='W'){ patk+=WEAPON; g[y][x]='.'; }
          else if(c==='A'){ defense+=ARMOR; g[y][x]='.'; }
          else if(c==='+'){ php=maxhp; g[y][x]='.'; }
          else if(c==='>'){ descended=true; }
        }
      }
    }
    if(descended) break;
    if(ehp>0){
      const man=Math.abs(x-ex)+Math.abs(y-ey);
      if(man===1){ php=Math.max(0, php-Math.max(1, eatk-defense)); }
      else { const e=chaseStep(g,ex,ey,x,y); ex=e.x; ey=e.y; }
    }
  }
  return { x, y, steps, ex, ey, php, ehp, gold, potions, descended, patk, defense };
}
module.exports = { run, chaseStep };
""",
"main.js": """\
// 부품4 진입점 — 시나리오 실행 후 위치·HP·골드·포션·하강·공격·방어 출력
const { run } = require('./engine');

const SCENARIOS = {
  "1": { grid:["#######","#.WA..#","#.....#","#.....#","#######"], start:[1,1], enemy:[5,3],
         moves:"RRRD", player_hp:10, enemy_hp:10, player_atk:2, enemy_atk:3 },
  "2": { grid:["######","#.^+.#","#....#","######"], start:[1,1], enemy:[4,2],
         moves:"RR", player_hp:10, enemy_hp:10, player_atk:2, enemy_atk:3 },
  "3": { grid:["#####","#.W.#","#...#","#####"], start:[1,1], enemy:[3,1],
         moves:"RRR", player_hp:10, enemy_hp:4, player_atk:2, enemy_atk:2 },
  "4": { grid:["######","#.A..#","#...^#","######"], start:[1,1], enemy:[4,1],
         moves:"RRDD", player_hp:8, enemy_hp:10, player_atk:3, enemy_atk:4 }
};

function main(){
  const args = process.argv.slice(2);
  let idx = null;
  const eq = args.find(a => a.startsWith('--scenario='));
  if (eq) idx = eq.split('=')[1];
  else { const k = args.indexOf('--scenario'); if (k>=0) idx = args[k+1]; }
  const s = SCENARIOS[idx];
  if (!s) return;
  const r = run(s.grid, s.start, s.enemy, s.moves, s);
  process.stdout.write(
    `x: ${r.x}\\ny: ${r.y}\\nsteps: ${r.steps}\\nenemy_x: ${r.ex}\\nenemy_y: ${r.ey}\\n` +
    `player_hp: ${r.php}\\nenemy_hp: ${r.ehp}\\ngold: ${r.gold}\\npotions: ${r.potions}\\n` +
    `descended: ${r.descended}\\nplayer_atk: ${r.patk}\\ndefense: ${r.defense}\\n`);
}
main();
""",
}

SCENARIO_INPUTS = {
    "1": {"grid":["#######","#.WA..#","#.....#","#.....#","#######"], "start":[1,1], "enemy":[5,3],
          "moves":"RRRD", "player_hp":10, "enemy_hp":10, "player_atk":2, "enemy_atk":3},
    "2": {"grid":["######","#.^+.#","#....#","######"], "start":[1,1], "enemy":[4,2],
          "moves":"RR", "player_hp":10, "enemy_hp":10, "player_atk":2, "enemy_atk":3},
    "3": {"grid":["#####","#.W.#","#...#","#####"], "start":[1,1], "enemy":[3,1],
          "moves":"RRR", "player_hp":10, "enemy_hp":4, "player_atk":2, "enemy_atk":2},
    "4": {"grid":["######","#.A..#","#...^#","######"], "start":[1,1], "enemy":[4,1],
          "moves":"RRDD", "player_hp":8, "enemy_hp":10, "player_atk":3, "enemy_atk":4},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "로그라이크 부품4 — 장비(무기·방어구·회복제단)",
        "genre": "roguelike",
        "mechanics": "grid,combat,items,equipment,weapon,armor,defense,heal,turn-order",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},
        "reference": REF,
        "notes": "부품3(rogue-p3) 확장 = 장비. 모듈 베이스+파일별 생성 검증용. 확장 런: --base rogue-p3.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): "
              f"pos=({g.get('x')},{g.get('y')}) steps={g.get('steps')} "
              f"enemy=({g.get('enemy_x')},{g.get('enemy_y')}) php={g.get('player_hp')} "
              f"ehp={g.get('enemy_hp')} atk={g.get('player_atk')} def={g.get('defense')} "
              f"gold={g.get('gold')} desc={g.get('descended')}")

    with tempfile.TemporaryDirectory(prefix="golem_rogue4_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
