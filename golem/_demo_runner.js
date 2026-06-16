// 카드 레퍼런스 engine.js를 명령 prefix로 재생해 매 턴 상태(프레임)를 JSON으로 뽑는 시연 러너
// 레퍼런스는 안정적 API(run)고, gemma 통과본은 11/11 정확일치로 레퍼런스와 동치임이 증명됨 →
// 레퍼런스 트레이스가 통과 부품의 동작을 그대로 보여준다(골든과 100% 일치 보장).
// run을 moves.slice(0,k)로 호출 → k턴 후 결정적 상태. 시나리오 필드로 부품(p0/p1/p2) 자동 판별.
// 사용: node _demo_runner.js <engineDir> <scenariosJsonPath>
// 출력(stdout): { "<sid>": [ {k, px, py, steps, ex?, ey?, php?, ehp?}, ... ], ... }

const path = require('path');
const fs = require('fs');

const engineDir = process.argv[2];
const scenPath = process.argv[3];

const { run } = require(path.resolve(engineDir, 'engine.js'));
const scenarios = JSON.parse(fs.readFileSync(scenPath, 'utf8'));

const out = {};
for (const sid of Object.keys(scenarios)) {
  const sc = scenarios[sid].input;
  const hasEnemy = Array.isArray(sc.enemy);
  const hasCombat = typeof sc.player_hp === 'number';
  const frames = [];
  for (let k = 0; k <= sc.moves.length; k++) {
    const prefix = sc.moves.slice(0, k);
    let r;
    if (hasCombat) {
      const stats = { player_hp: sc.player_hp, enemy_hp: sc.enemy_hp,
                      player_atk: sc.player_atk, enemy_atk: sc.enemy_atk };
      r = run(sc.grid, sc.start, sc.enemy, prefix, stats);
      frames.push({ k, px: r.x, py: r.y, steps: r.steps, ex: r.ex, ey: r.ey, php: r.php, ehp: r.ehp });
    } else if (hasEnemy) {
      r = run(sc.grid, sc.start, sc.enemy, prefix);
      frames.push({ k, px: r.x, py: r.y, steps: r.steps, ex: r.ex, ey: r.ey });
    } else {
      r = run(sc.grid, sc.start, prefix);
      frames.push({ k, px: r.x, py: r.y, steps: r.steps });
    }
  }
  out[sid] = frames;
}

process.stdout.write(JSON.stringify(out));
