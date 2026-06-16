# golem 카드 #3 적재 — 2048 + 벽(장애물) 확장. 베이스(merge-2048) 위에 메카닉 하나 더 얹기
"""3단계 확장 루프: 통과한 merge-2048을 베이스로, 벽(-1=고정 장애물) 규칙만 추가한 확장.
레퍼런스는 베이스에서 moves.js의 슬라이드만 '벽으로 분할된 세그먼트별 슬라이드'로 바꾼 것.
생성 런은 driver --card merge-2048-walls --base merge-2048 로 베이스 solution을 워커에 줘서
'맨바닥 대비 확장이 싸게 되나'를 측정한다."""

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

SLUG = "merge-2048-walls"

RULES = """\
You are implementing a DETERMINISTIC 2048-style merge puzzle WITH WALLS in JavaScript (Node.js).
There is NO randomness anywhere: the same scenario always produces the same result.

== OUTPUT CONTRACT (must match EXACTLY) ==
- The program must be runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- It must print EXACTLY these lines and NOTHING else, in this order:
      score: <integer>
      cell_<r>_<c>: <integer>   for every r in 0..3 and every c in 0..3,
                                in row-major order (r outer 0..3, c inner 0..3) = 16 lines
  So 17 lines total: the score line first, then cell_0_0, cell_0_1, ... cell_3_3.
- Empty cells print as 0. WALL cells print as -1 (see below).

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm packages, no network, no filesystem, no stdin/prompts. No Math.random.
- Multi-file using CommonJS (require / module.exports). At minimum: board.js, moves.js, main.js.
  The files MUST actually require each other (no dead files). Entry point is main.js.

== INPUT (per scenario; hardcode the scenarios given below) ==
Each scenario input = { "board": <4x4 array of integers>, "moves": "<string of U/D/L/R>" }.
Cell values: 0 = empty, a positive number = a tile, -1 = a WALL (fixed obstacle).
The board is row-major: board[r][c], r = row top->bottom (0..3), c = column left->right (0..3).

== A MOVE (with walls) ==
A move shifts ALL tiles as far as possible toward one edge, merging equal tiles, BUT walls block them:
- L = toward left edge, R = right, U = top, D = bottom.
- A WALL (-1) never moves, never merges, and tiles can NEVER pass through or onto it.
- Therefore each affected line (each row for L/R, each column for U/D) is split by its walls into
  independent SEGMENTS (the runs of cells between walls / line ends). Each segment is processed on its
  own, exactly like ordinary 2048, toward the moving edge:
  1. SLIDE: drop the zeros within the segment so tiles move toward the edge, keeping their order.
  2. MERGE: scanning from the EDGE side inward, equal ADJACENT tiles combine into ONE tile of DOUBLE
     value. Each tile merges AT MOST ONCE per move; after a merge continue after the merged pair.
     Examples toward the edge: [2,2,2]->[4,2]; [2,2,2,2]->[4,4]; [4,2,2]->[4,4].
  3. PAD the segment with zeros on its far side; the wall cells keep their -1 positions unchanged.
  Example for a left move on row [2,-1,2,2]: segment [2] stays [2]; segment [2,2] -> [4,0];
  result row = [2,-1,4,0].
- SCORE: each merge adds the value of the NEW combined tile to the running score (2+2 adds 4).

== AFTER EACH MOVE: SPAWN ==
- If the move CHANGED the board (any cell differs from before this move, comparing the post-slide/merge
  board, before spawning): place a new tile of value 2 in the FIRST EMPTY (value 0) cell in row-major
  order (scan r = 0..3, within each row c = 0..3). NEVER spawn on a wall (-1) or an occupied tile.
- If the move did NOT change the board: do nothing (no spawn, no score), then continue to the next move.

== RUN ==
Start from the scenario's board with score = 0. Apply each character of "moves" left to right.
After all moves, print the final score and board per the OUTPUT CONTRACT (walls printed as -1).

== FILES (multi-file required) ==
At minimum: board.js (4x4 grid helpers), moves.js (segment-aware slide+merge and apply a move per
direction), main.js (the hardcoded scenarios + run loop + printing). main.js must require the others.
"""

# --- 확장 레퍼런스: 베이스에서 moves.js 슬라이드만 '벽 분할 세그먼트'로 변경 ---
REF = {
"board.js": """\
// 2048(벽) 보드 유틸 — 4x4 정수 그리드 복제·비교·전치 (-1=벽도 값 그대로 따라감)
function clone(b) { return b.map(r => r.slice()); }
function equal(a, b) {
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) if (a[i][j] !== b[i][j]) return false;
  return true;
}
function transpose(b) {
  const t = [[0,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]];
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) t[j][i] = b[i][j];
  return t;
}
module.exports = { clone, equal, transpose };
""",
"moves.js": """\
// 2048(벽) 이동·병합 — 벽(-1)으로 나뉜 세그먼트별 슬라이드+병합, 점수 가산. 결정적.
const { transpose } = require('./board');

// 벽 없는 세그먼트(숫자 배열)를 왼쪽으로 압축+병합. {seg, gained} 반환(길이 보존).
function slideSeg(arr) {
  const nz = arr.filter(v => v !== 0);
  const out = []; let gained = 0; let i = 0;
  while (i < nz.length) {
    if (i + 1 < nz.length && nz[i] === nz[i + 1]) { const m = nz[i] * 2; out.push(m); gained += m; i += 2; }
    else { out.push(nz[i]); i += 1; }
  }
  while (out.length < arr.length) out.push(0);
  return { seg: out, gained };
}
// 한 줄(벽 포함)을 왼쪽으로. 벽으로 분할해 세그먼트별 처리. {line, gained} 반환.
function slideLineLeft(line) {
  const out = new Array(line.length).fill(0);
  let gained = 0; let buf = []; let start = 0;
  const flush = () => { const { seg, gained: g } = slideSeg(buf); for (let k = 0; k < buf.length; k++) out[start + k] = seg[k]; gained += g; };
  for (let i = 0; i < line.length; i++) {
    if (line[i] === -1) { flush(); out[i] = -1; buf = []; start = i + 1; }
    else buf.push(line[i]);
  }
  flush();
  return { line: out, gained };
}
function moveLeft(b) {
  let g = 0;
  const nb = b.map(r => { const { line, gained } = slideLineLeft(r); g += gained; return line; });
  return { board: nb, gained: g };
}
function rev(b) { return b.map(r => r.slice().reverse()); }

function applyMove(b, dir) {
  if (dir === 'L') return moveLeft(b);
  if (dir === 'R') { const res = moveLeft(rev(b)); return { board: rev(res.board), gained: res.gained }; }
  if (dir === 'U') { const res = moveLeft(transpose(b)); return { board: transpose(res.board), gained: res.gained }; }
  if (dir === 'D') { const res = moveLeft(rev(transpose(b))); return { board: transpose(rev(res.board)), gained: res.gained }; }
  return { board: b.map(r => r.slice()), gained: 0 };
}
module.exports = { slideSeg, slideLineLeft, applyMove };
""",
"main.js": """\
// 2048(벽) 진입점 — 시나리오 보드(벽 포함)+이동시퀀스를 결정적으로 실행해 점수·보드 출력
const { clone, equal } = require('./board');
const { applyMove } = require('./moves');

const SCENARIOS = {
  "1": { board: [[2,-1,2,2],[0,0,0,0],[0,0,0,0],[0,0,0,0]], moves: "L" },
  "2": { board: [[2,2,-1,2],[0,0,0,0],[0,0,0,0],[0,0,0,0]], moves: "L" },
  "3": { board: [[2,0,0,0],[-1,0,0,0],[2,0,0,0],[2,0,0,0]], moves: "U" },
  "4": { board: [[2,2,0,-1],[0,-1,0,0],[2,0,0,2],[0,0,0,0]], moves: "LDR" }
};

function spawn(b) {
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) if (b[i][j] === 0) { b[i][j] = 2; return; }
}
function run(s) {
  let board = clone(s.board); let score = 0;
  for (const dir of s.moves) {
    const { board: nb, gained } = applyMove(board, dir);
    if (!equal(board, nb)) { score += gained; spawn(nb); board = nb; }
  }
  return { score, board };
}
function main() {
  const args = process.argv.slice(2);
  let idx = null;
  const eq = args.find(a => a.startsWith('--scenario='));
  if (eq) idx = eq.split('=')[1];
  else { const k = args.indexOf('--scenario'); if (k >= 0) idx = args[k + 1]; }
  const s = SCENARIOS[idx];
  if (!s) return;
  const { score, board } = run(s);
  let out = `score: ${score}`;
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) out += `\\ncell_${i}_${j}: ${board[i][j]}`;
  process.stdout.write(out + '\\n');
}
main();
""",
}

SCENARIO_INPUTS = {
    "1": {"board": [[2,-1,2,2],[0,0,0,0],[0,0,0,0],[0,0,0,0]], "moves": "L"},
    "2": {"board": [[2,2,-1,2],[0,0,0,0],[0,0,0,0],[0,0,0,0]], "moves": "L"},
    "3": {"board": [[2,0,0,0],[-1,0,0,0],[2,0,0,0],[2,0,0,0]], "moves": "U"},
    "4": {"board": [[2,2,0,-1],[0,-1,0,0],[2,0,0,2],[0,0,0,0]], "moves": "LDR"},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "2048 + 벽(장애물) 확장",
        "genre": "puzzle",
        "mechanics": "grid-merge,walls,segments,deterministic-spawn,score",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},
        "reference": REF,
        "notes": "merge-2048 확장(벽=-1 고정 장애물, 줄을 세그먼트로 분할). 확장 런: --base merge-2048.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        grid = " ".join(g.get(f"cell_{i}_{j}", "?") for i in range(4) for j in range(4))
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): score={g.get('score')}  board=[{grid}]")

    with tempfile.TemporaryDirectory(prefix="golem_walls_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
