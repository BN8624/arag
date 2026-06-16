// 공유 엔진(engine.browser.js)이 골든(attempt10 검증본)과 정확일치하는지 무회귀 가드
const fs = require('fs');
const path = require('path');
const { buildEngine } = require('./engine.browser.js');

const GOLDEN = JSON.parse(fs.readFileSync(
  path.join(__dirname, '..', 'golden', 'scenarios.json'), 'utf8'));

function got(n) {
  const eng = buildEngine(n); // 내부에서 run()까지 완료
  const lines = eng.getResult().split('\n');
  const winner = lines[0].split(': ')[1];
  const turns = parseInt(lines[1].split(': ')[1], 10);
  const hp = {};
  lines.slice(2).forEach(l => { const [k, v] = l.split(': '); hp[k] = parseInt(v, 10); });
  return { winner, turns, hp };
}

let allPass = true;
for (const n of ['1', '2', '3', '4']) {
  const g = GOLDEN[String(n)].golden;
  const exp = { winner: g.winner, turns: g.turns, hp: g.final_hp };
  const gotv = got(n);
  const ok = JSON.stringify(gotv) === JSON.stringify(exp);
  console.log(`scenario ${n}: ${ok ? 'PASS' : 'FAIL'}  got=${JSON.stringify(gotv)}`);
  if (!ok) { allPass = false; console.log(`           exp=${JSON.stringify(exp)}`); }
}
console.log(allPass ? '\n[OK] 공유 엔진 == 골든 (무회귀 통과)' : '\n[FAIL] 불일치');
process.exit(allPass ? 0 : 1);
