# 부품3 베이스를 모듈 구조(6파일)로 재작성 — 파일별 생성 대비. 골든 그대로 채점 후 solution 승격. 키 안 씀.
"""스케일 한계(통째 재생성) 해소의 1단계. 무거운 재사용 로직(추격·전투·아이템)을 모듈로 분리하고
engine은 얇은 오케스트레이터로 둔다. 다음 부품은 '바뀐 engine + 새 작은 모듈'만 생성하면 되므로
부품당 출력이 전체 크기와 무관해진다. 이 모듈 구현을 rogue-p3 골든으로 채점해 통과하면 베이스로 승격."""

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
from grade import grade

SLUG = "rogue-p3"

MODULAR = {
"dungeon.js": """\
// 던전 격자 유틸 — 경계 판정 + 벽('#')만 차단(나머지 칸은 통행 가능)
function inBounds(grid, x, y) {
  return y >= 0 && y < grid.length && x >= 0 && x < grid[y].length;
}
function isBlocked(grid, x, y) {
  if (!inBounds(grid, x, y)) return true;
  return grid[y][x] === '#';
}
module.exports = { inBounds, isBlocked };
""",
"chase.js": """\
// 적 결정적 추격 한 칸 — 1차축(|dx|>=|dy|=수평) 막히면 2차축. 플레이어칸/벽/경계 불가. (재사용·안정)
const { isBlocked } = require('./dungeon');
const sign = n => (n > 0 ? 1 : (n < 0 ? -1 : 0));

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
module.exports = { chaseStep };
""",
"combat.js": """\
// 전투 — 플레이어가 적 칸으로 가면 공격(이동X), 적은 인접 시 공격 아니면 추격. HP 0=사망. (재사용·안정)
const { chaseStep } = require('./chase');

function playerAttacks(s, tx, ty) {     // 목표칸이 적이면 공격하고 true
  if (s.ehp > 0 && tx === s.ex && ty === s.ey) {
    s.ehp = Math.max(0, s.ehp - s.patk);
    return true;
  }
  return false;
}
function enemyAct(s) {                   // 적 페이즈: 인접이면 반격, 아니면 추격
  if (s.ehp <= 0) return;
  const man = Math.abs(s.px - s.ex) + Math.abs(s.py - s.ey);
  if (man === 1) { s.php = Math.max(0, s.php - s.eatk); }
  else { const e = chaseStep(s.grid, s.ex, s.ey, s.px, s.py); s.ex = e.x; s.ey = e.y; }
}
module.exports = { playerAttacks, enemyAct };
""",
"items.js": """\
// 아이템·함정·계단·포션 — 밟은 칸 효과($골드/!포션/^함정/>계단)와 포션 사용(Q). (재사용·안정)
const GOLD = 10, TRAP = 3, HEAL = 5;

function resolveCell(s) {                // 플레이어가 막 들어선 칸의 효과(1회성: 칸을 비움)
  const c = s.grid[s.py][s.px];
  if (c === '$') { s.gold += GOLD; s.grid[s.py][s.px] = '.'; }
  else if (c === '!') { s.potions += 1; s.grid[s.py][s.px] = '.'; }
  else if (c === '^') { s.php = Math.max(0, s.php - TRAP); s.grid[s.py][s.px] = '.'; }
  else if (c === '>') { s.descended = true; }
}
function quaff(s) {                      // 포션 마시기: 보유분 있으면 HP 회복(최대치 캡)
  if (s.potions > 0) { s.potions -= 1; s.php = Math.min(s.maxhp, s.php + HEAL); }
}
module.exports = { resolveCell, quaff };
""",
"engine.js": """\
// 오케스트레이터 — 게임 상태 생성 + 결정적 턴 루프 + 출력 포맷. 무거운 로직은 모듈에 위임.
// 기능 추가 = 새 모듈 + 여기 세 곳(makeState 필드 / playerCommand·run 연결 / format 줄)만 손댄다.
const { isBlocked } = require('./dungeon');
const { playerAttacks, enemyAct } = require('./combat');
const { resolveCell, quaff } = require('./items');
const DELTA = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] };

function makeState(sc) {
  return {
    grid: sc.grid.map(r => r.split('')), px: sc.start[0], py: sc.start[1], steps: 0,
    ex: sc.enemy[0], ey: sc.enemy[1], php: sc.player_hp, ehp: sc.enemy_hp, maxhp: sc.player_hp,
    patk: sc.player_atk, eatk: sc.enemy_atk, gold: 0, potions: 0, descended: false, moves: sc.moves,
  };
}
function playerCommand(s, cmd) {          // 한 명령의 플레이어 페이즈
  if (cmd === 'Q') { quaff(s); return; }
  const d = DELTA[cmd];
  if (!d) return;
  const nx = s.px + d[0], ny = s.py + d[1];
  if (playerAttacks(s, nx, ny)) return;   // 적 칸 = 공격(이동X)
  if (isBlocked(s.grid, nx, ny)) return;  // 벽/경계 = 막힘
  s.px = nx; s.py = ny; s.steps += 1;      // 이동
  resolveCell(s);                          // 선 칸 효과
}
function run(sc) {
  const s = makeState(sc);
  for (const cmd of s.moves) {
    if (s.php <= 0 || s.descended) break;  // 사망/하강 → 남은 명령 무시
    playerCommand(s, cmd);
    if (s.descended) break;                // 계단 → 적 페이즈 없이 종료
    enemyAct(s);
  }
  return s;
}
function format(s) {
  return `x: ${s.px}\\ny: ${s.py}\\nsteps: ${s.steps}\\nenemy_x: ${s.ex}\\nenemy_y: ${s.ey}\\n` +
         `player_hp: ${s.php}\\nenemy_hp: ${s.ehp}\\ngold: ${s.gold}\\npotions: ${s.potions}\\n` +
         `descended: ${s.descended}\\n`;
}
module.exports = { run, format, makeState, playerCommand };
""",
"main.js": """\
// 던전 진입점 — 시나리오 선택(--scenario N) 후 결정적 실행 결과를 출력
const { run, format } = require('./engine');

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
  process.stdout.write(format(run(s)));
}
main();
""",
}


def main():
    card = game_bank.get_card(SLUG)
    if card is None:
        print(f"[ERR] 카드 '{SLUG}' 없음 — bank_add_roguelike_p3.py 먼저")
        return 2

    with tempfile.TemporaryDirectory(prefix="golem_p3mod_") as d:
        for name, body in MODULAR.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, card["scenarios"])
    if not res["pass"]:
        print(f"[FAIL] 모듈 구현 채점 실패: {res['first_divergence']}")
        return 1

    card["solution"] = MODULAR
    game_bank.save_card(card)
    print(f"[OK] '{SLUG}'.solution <- 모듈 구조 {len(MODULAR)}파일 "
          f"({', '.join(MODULAR)})  — 골든 채점 PASS, 베이스 승격 완료")
    total = sum(len(v) for v in MODULAR.values())
    print(f"     총 {total}자. 안정모듈(dungeon/chase/combat/items)은 다음 부품에서 재출력 불필요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
