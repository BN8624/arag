# golem 카드 #2 적재 — 결정적 2048 합치기 퍼즐. Claude 레퍼런스(JS)+규칙+시나리오 → oracle 골든
"""A 방식 실연: game/ 같은 기존 레퍼런스가 없는 새 게임을, Claude가 직접 짠 결정적 JS
레퍼런스로 골든을 만들어 카드로 적재한다. 규칙(RULES)은 레퍼런스 동작을 빈틈없이 명세 —
워커가 못 맞추면 계약 버그이지 모델 탓이 아니다(프로젝트 핵심 교훈)."""

import sys
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

SLUG = "merge-2048"

RULES = """\
You are implementing a DETERMINISTIC 2048-style merge puzzle in JavaScript (Node.js).
There is NO randomness anywhere: the same scenario always produces the same result.

== OUTPUT CONTRACT (must match EXACTLY) ==
- The program must be runnable as:  node main.js --scenario N   (N is 1, 2, 3, or 4)
- It must print EXACTLY these lines and NOTHING else, in this order:
      score: <integer>
      cell_<r>_<c>: <integer>   for every r in 0..3 and every c in 0..3,
                                in row-major order (r outer 0..3, c inner 0..3) = 16 lines
  So 17 lines total: the score line first, then cell_0_0, cell_0_1, ... cell_3_3.
- Empty cells print as 0.

== HARD CONSTRAINTS ==
- Node.js built-ins ONLY. No npm packages, no network, no filesystem, no stdin/prompts. No Math.random.
- Multi-file using CommonJS (require / module.exports). At minimum: board.js, moves.js, main.js.
  The files MUST actually require each other (no dead files). Entry point is main.js.

== INPUT (per scenario; hardcode the scenarios given below) ==
Each scenario input = { "board": <4x4 array of integers, 0 = empty>, "moves": "<string of U/D/L/R>" }.
The board is row-major: board[r][c], where r = row top->bottom (0..3), c = column left->right (0..3).

== A MOVE ==
A move shifts ALL tiles as far as possible toward one edge, merging equal tiles:
- L = toward the left edge (column 0). R = right edge. U = top edge (row 0). D = bottom edge.
- For each affected line (each row for L/R, each column for U/D), processed toward the moving edge:
  1. SLIDE: drop the zeros so tiles move over empty space toward the edge, keeping their relative order.
  2. MERGE: scanning from the EDGE side inward, if two ADJACENT tiles are equal, combine them into ONE
     tile of DOUBLE the value. Each tile may take part in AT MOST ONE merge per move; after a merge,
     continue scanning AFTER the merged pair (never chain a third tile into the same merge).
     Examples (toward the edge): [2,2,2] -> [4,2];  [2,2,2,2] -> [4,4];  [4,2,2] -> [4,4].
  3. PAD: fill the rest of the line with zeros on the far side so its length stays 4.
- SCORE: each merge adds the value of the NEW combined tile to the running score (merging 2+2 adds 4).

== AFTER EACH MOVE: SPAWN ==
- If the move CHANGED the board (any cell differs from the board as it was BEFORE this move, comparing
  the post-slide/merge board, before spawning): place a new tile of value 2 in the FIRST empty cell in
  row-major order (scan r = 0..3, and within each row c = 0..3; the first cell whose value is 0).
- If the move did NOT change the board: do nothing for that move (no spawn, no score change), then
  continue to the next move.

== RUN ==
Start from the scenario's board with score = 0. Apply each character of the "moves" string left to right
(each character is one move). After all moves are applied, print the final score and board per the
OUTPUT CONTRACT.

== FILES (multi-file required) ==
At minimum: board.js (4x4 grid helpers: clone / equal / transpose), moves.js (slide+merge a line and
apply a move in a direction, returning the new board and the points gained), main.js (the hardcoded
scenarios + the run loop + printing). main.js must require the others.
"""

# --- Claude 레퍼런스 구현 (결정적, RULES와 정확히 일치) ---
REF = {
"board.js": """\
// 2048 보드 유틸 — 4x4 정수 그리드 복제·비교·전치
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
// 2048 이동·병합 — 한 줄을 가장자리로 밀고 병합(점수 가산), 방향별 적용. 결정적.
const { transpose } = require('./board');

// 한 줄을 왼쪽(가장자리)으로 슬라이드+병합. {row, gained} 반환.
function slideLeft(row) {
  const nz = row.filter(v => v !== 0);
  const out = []; let gained = 0; let i = 0;
  while (i < nz.length) {
    if (i + 1 < nz.length && nz[i] === nz[i + 1]) { const m = nz[i] * 2; out.push(m); gained += m; i += 2; }
    else { out.push(nz[i]); i += 1; }
  }
  while (out.length < 4) out.push(0);
  return { row: out, gained };
}
function moveLeft(b) {
  let g = 0;
  const nb = b.map(r => { const { row, gained } = slideLeft(r); g += gained; return row; });
  return { board: nb, gained: g };
}
function rev(b) { return b.map(r => r.slice().reverse()); }

// dir in {L,R,U,D} → {board, gained}
function applyMove(b, dir) {
  if (dir === 'L') return moveLeft(b);
  if (dir === 'R') { const res = moveLeft(rev(b)); return { board: rev(res.board), gained: res.gained }; }
  if (dir === 'U') { const res = moveLeft(transpose(b)); return { board: transpose(res.board), gained: res.gained }; }
  if (dir === 'D') { const res = moveLeft(rev(transpose(b))); return { board: transpose(rev(res.board)), gained: res.gained }; }
  return { board: b.map(r => r.slice()), gained: 0 };
}
module.exports = { slideLeft, applyMove };
""",
"main.js": """\
// 2048 진입점 — 시나리오 보드+이동시퀀스를 결정적으로 실행해 최종 점수·보드 출력
const { clone, equal } = require('./board');
const { applyMove } = require('./moves');

const SCENARIOS = {
  "1": { board: [[2,2,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]], moves: "L" },
  "2": { board: [[2,2,4,4],[0,0,0,0],[0,0,0,0],[0,0,0,0]], moves: "L" },
  "3": { board: [[2,0,0,0],[2,0,0,0],[2,0,0,0],[2,0,0,0]], moves: "U" },
  "4": { board: [[0,0,0,2],[0,0,0,2],[0,0,2,0],[0,0,0,0]], moves: "RDLU" }
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
    "1": {"board": [[2,2,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]], "moves": "L"},
    "2": {"board": [[2,2,4,4],[0,0,0,0],[0,0,0,0],[0,0,0,0]], "moves": "L"},
    "3": {"board": [[2,0,0,0],[2,0,0,0],[2,0,0,0],[2,0,0,0]], "moves": "U"},
    "4": {"board": [[0,0,0,2],[0,0,0,2],[0,0,2,0],[0,0,0,0]], "moves": "RDLU"},
}


def main():
    ids = list(SCENARIO_INPUTS.keys())
    golden = oracle.golden_from_reference(REF, ids)  # 레퍼런스가 정답
    scenarios = {n: {"input": SCENARIO_INPUTS[n], "golden": golden[n]} for n in ids}

    card = {
        "slug": SLUG,
        "title": "결정적 2048 합치기 퍼즐",
        "genre": "puzzle",
        "mechanics": "grid-merge,deterministic-spawn,score",
        "rules": RULES,
        "scenarios": scenarios,
        "solution": {},          # 아직 없음 — gemma가 생성 런에서 만든다
        "reference": REF,        # Claude 레퍼런스(골든 출처)
        "notes": "A 방식 첫 새 게임. 4x4, 입력=보드+이동시퀀스, 출력=score+cell_r_c. 결정적 스폰.",
    }
    game_bank.save_card(card)
    print(f"[적재] 카드 '{SLUG}' ({len(scenarios)} 시나리오), 레퍼런스 {len(REF)}파일\n")
    for n in ids:
        g = golden[n]
        grid = " ".join(g.get(f"cell_{i}_{j}", "?") for i in range(4) for j in range(4))
        print(f"  scenario {n} ({SCENARIO_INPUTS[n]['moves']}): score={g.get('score')}  board=[{grid}]")

    # 무회귀: 레퍼런스를 grade에 넣어 카드 골든과 PASS (오라클·채점 경로 정합 점검)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="golem_2048_") as d:
        for name, body in REF.items():
            (Path(d) / name).write_text(body, encoding="utf-8")
        res = grade(d, scenarios)
    print(f"\n[{'OK' if res['pass'] else 'FAIL'}] 레퍼런스 self-채점 "
          f"{'PASS' if res['pass'] else res['first_divergence']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
