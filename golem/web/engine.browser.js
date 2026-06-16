// golem 공유 전투엔진 — attempt10 검증 로직 무수정 + 표현용 trace. 브라우저(window)·node(module) 양쪽 호환.

// ===== 시나리오 데이터 (attempt10/main.js 그대로) =====
const SCENARIOS = {
  1: { heroes: [
        { id:"hero1", name:"Tank", team:"hero", max_hp:140, atk:12, defense:9, spd:7, skills:["charge","combo_strike","venom"] },
        { id:"hero2", name:"Volt", team:"hero", max_hp:85, atk:16, defense:3, spd:15, skills:["shock_bolt","venom","combo_strike"] } ],
       enemies: [
        { id:"enemy1", name:"Imp", team:"enemy", max_hp:60, atk:15, defense:2, spd:14, skills:["ignite","frost","detonate"] },
        { id:"enemy2", name:"Golem", team:"enemy", max_hp:160, atk:14, defense:11, spd:5, skills:["combo_strike","charge","frost"] },
        { id:"enemy3", name:"Orc", team:"enemy", max_hp:120, atk:17, defense:6, spd:8, skills:["shock_bolt","detonate","combo_strike"] } ] },
  2: { heroes: [
        { id:"hero1", name:"Volt", team:"hero", max_hp:85, atk:16, defense:3, spd:15, skills:["shock_bolt","venom","combo_strike"] },
        { id:"hero2", name:"Tank", team:"hero", max_hp:140, atk:12, defense:9, spd:7, skills:["charge","combo_strike","venom"] } ],
       enemies: [
        { id:"enemy1", name:"Golem", team:"enemy", max_hp:160, atk:14, defense:11, spd:5, skills:["combo_strike","charge","frost"] },
        { id:"enemy2", name:"Imp", team:"enemy", max_hp:60, atk:15, defense:2, spd:14, skills:["ignite","frost","detonate"] } ] },
  3: { heroes: [
        { id:"hero1", name:"Pyro", team:"hero", max_hp:90, atk:18, defense:4, spd:12, skills:["ignite","detonate","combo_strike"] },
        { id:"hero2", name:"Frost", team:"hero", max_hp:100, atk:14, defense:6, spd:10, skills:["frost","ignite","combo_strike"] },
        { id:"hero3", name:"Volt", team:"hero", max_hp:85, atk:16, defense:3, spd:15, skills:["shock_bolt","venom","combo_strike"] } ],
       enemies: [
        { id:"enemy1", name:"Golem", team:"enemy", max_hp:160, atk:14, defense:11, spd:5, skills:["combo_strike","charge","frost"] },
        { id:"enemy2", name:"Orc", team:"enemy", max_hp:120, atk:17, defense:6, spd:8, skills:["shock_bolt","detonate","combo_strike"] },
        { id:"enemy3", name:"Imp", team:"enemy", max_hp:60, atk:15, defense:2, spd:14, skills:["ignite","frost","detonate"] } ] },
  4: { heroes: [
        { id:"hero1", name:"Tank", team:"hero", max_hp:140, atk:12, defense:9, spd:7, skills:["charge","combo_strike","venom"] },
        { id:"hero2", name:"Frost", team:"hero", max_hp:100, atk:14, defense:6, spd:10, skills:["frost","ignite","combo_strike"] },
        { id:"hero3", name:"Pyro", team:"hero", max_hp:90, atk:18, defense:4, spd:12, skills:["ignite","detonate","combo_strike"] } ],
       enemies: [
        { id:"enemy1", name:"Imp", team:"enemy", max_hp:60, atk:15, defense:2, spd:14, skills:["ignite","frost","detonate"] },
        { id:"enemy2", name:"Orc", team:"enemy", max_hp:120, atk:17, defense:6, spd:8, skills:["shock_bolt","detonate","combo_strike"] },
        { id:"enemy3", name:"Goblin", team:"enemy", max_hp:70, atk:13, defense:3, spd:11, skills:["venom","combo_strike"] } ] }
};

// ===== models.js (그대로) =====
class Entity {
  constructor({ id, name, team, max_hp, atk, defense, spd, skills }) {
    this.id = id; this.name = name; this.team = team;
    this.max_hp = max_hp; this.hp = max_hp; this.atk = atk;
    this.defense = defense; this.spd = spd; this.skills = skills;
    this.gauge = 0; this.statuses = []; this.last_skill = null; this.rotation_index = 0;
  }
  isAlive() { return this.hp > 0; }
  hasStatus(type) { return this.statuses.some(s => s.type === type); }
  getStatus(type) { return this.statuses.find(s => s.type === type); }
  removeStatus(type) { this.statuses = this.statuses.filter(s => s.type !== type); }
}

// ===== skills.js (그대로) =====
const skills = {
  ignite: (a,t,e) => { e.dealDamage(a,t,5); e.applyStatus(t,"burn",3); },
  detonate: (a,t,e) => { let base=20, ab=false; if(a.last_skill==="ignite"){base=50;ab=true;} e.dealDamage(a,t,base); if(ab) e.applyStatus(t,"burn",3); },
  charge: (a,t,e) => { /* no damage */ },
  combo_strike: (a,t,e) => { const b=12; e.dealDamage(a,t,b); if(a.last_skill==="charge") e.dealDamage(a,t,b); },
  frost: (a,t,e) => { e.dealDamage(a,t,4); e.applyStatus(t,"freeze",1); },
  venom: (a,t,e) => { e.dealDamage(a,t,3); e.applyStatus(t,"poison",3,2); },
  shock_bolt: (a,t,e) => { e.dealDamage(a,t,6); e.applyStatus(t,"shock",2); }
};

// ===== engine.js (로직 그대로 + 표현용 trace 수집만 추가) =====
class BattleEngine {
  constructor(heroes, enemies) {
    this.entities = [...heroes, ...enemies];
    this.turns = 0; this.max_turns = 100;
    this.trace = []; // 표현층 전용 — 채점 결과에 영향 없음
  }
  _snap(actor, skillName) {
    this.trace.push({
      turn: this.turns,
      actor: actor ? actor.id : null,
      skill: skillName || null,
      entities: this.entities.map(e => ({
        id: e.id, name: e.name, team: e.team, hp: Math.max(0, e.hp), max_hp: e.max_hp,
        gauge: e.gauge, alive: e.isAlive(),
        statuses: e.statuses.map(s => ({ type: s.type, turns: s.turns, stacks: s.stacks }))
      }))
    });
  }
  dealDamage(attacker, target, skillBase) {
    let dmg = Math.max(1, attacker.atk + skillBase - target.defense);
    if (target.hasStatus("shock")) dmg = Math.floor(dmg * 1.25);
    target.hp -= dmg; if (target.hp < 0) target.hp = 0;
    target.last_skill = null;
  }
  applyStatus(target, type, duration, stacks = 1) {
    if (type === "freeze") { if (target.hasStatus("burn")) return; }
    if (type === "burn") { if (target.hasStatus("freeze")) target.removeStatus("freeze"); }
    if (type === "poison") { if (target.hasStatus("shock")) stacks = Math.min(5, stacks * 2); }
    const existing = target.getStatus(type);
    if (existing) {
      existing.turns = duration;
      if (type === "poison") existing.stacks = Math.min(5, existing.stacks + stacks);
    } else {
      target.statuses.push({ type, turns: duration, stacks });
    }
    if (target.hasStatus("burn") && target.hasStatus("freeze")) {
      target.removeStatus("burn"); target.removeStatus("freeze");
      target.hp -= 30; if (target.hp < 0) target.hp = 0; target.last_skill = null;
    }
  }
  run() {
    while (this.turns < this.max_turns) {
      const ha = this.entities.filter(e => e.team === "hero" && e.isAlive());
      const ea = this.entities.filter(e => e.team === "enemy" && e.isAlive());
      if (ha.length === 0 || ea.length === 0) break;
      this.entities.forEach(e => { if (e.isAlive()) e.gauge += e.spd; });
      while (true) {
        const ready = this.entities.filter(e => e.isAlive() && e.gauge >= 100);
        if (ready.length === 0) break;
        ready.sort((a,b) => {
          if (b.spd !== a.spd) return b.spd - a.spd;
          if (a.hp !== b.hp) return a.hp - b.hp;
          return this.entities.indexOf(a) - this.entities.indexOf(b);
        });
        const actor = ready[0];
        this.processTurn(actor);
        const ha2 = this.entities.filter(e => e.team === "hero" && e.isAlive());
        const ea2 = this.entities.filter(e => e.team === "enemy" && e.isAlive());
        if (ha2.length === 0 || ea2.length === 0) return this.getResult();
      }
    }
    return this.getResult();
  }
  processTurn(actor) {
    this.turns += 1;
    let skillName = null;
    const burn = actor.getStatus("burn");
    if (burn) {
      actor.hp -= Math.floor(actor.hp * 0.05); if (actor.hp < 0) actor.hp = 0;
      burn.turns -= 1; if (burn.turns <= 0) actor.removeStatus("burn");
    }
    if (!actor.isAlive()) { actor.gauge -= 100; this._snap(actor, "(전투불능)"); return; }
    const freeze = actor.getStatus("freeze");
    if (freeze) {
      actor.gauge = 0; freeze.turns -= 1; if (freeze.turns <= 0) actor.removeStatus("freeze");
      actor.last_skill = null; skillName = "(빙결)";
    } else {
      actor.gauge -= 100;
      const enemies = this.entities.filter(e => e.team !== actor.team && e.isAlive());
      enemies.sort((a,b) => a.hp - b.hp || this.entities.indexOf(a) - this.entities.indexOf(b));
      const target = enemies[0];
      skillName = actor.skills[actor.rotation_index % actor.skills.length];
      actor.rotation_index += 1;
      if (target) skills[skillName](actor, target, this);
      actor.last_skill = skillName;
    }
    const poison = actor.getStatus("poison");
    if (poison) {
      actor.hp -= 8 * poison.stacks; if (actor.hp < 0) actor.hp = 0;
      poison.stacks -= 1; if (poison.stacks <= 0) actor.removeStatus("poison");
    }
    const shock = actor.getStatus("shock");
    if (shock) { shock.turns -= 1; if (shock.turns <= 0) actor.removeStatus("shock"); }
    this._snap(actor, skillName);
  }
  getResult() {
    const ha = this.entities.filter(e => e.team === "hero" && e.isAlive());
    const ea = this.entities.filter(e => e.team === "enemy" && e.isAlive());
    let winner = "draw";
    if (this.turns >= this.max_turns && ha.length > 0 && ea.length > 0) winner = "draw";
    else if (ea.length === 0) winner = "hero";
    else if (ha.length === 0) winner = "enemy";
    this.winner = winner;
    let output = `winner: ${winner}\nturns: ${this.turns}`;
    this.entities.forEach(e => { output += `\n${e.id}: ${Math.max(0, e.hp)}`; });
    return output;
  }
}

// 시나리오 번호로 전투를 끝까지 돌린 엔진(trace 포함) 반환
function buildEngine(n) {
  const d = SCENARIOS[n];
  const heroes = d.heroes.map(h => new Entity(h));
  const enemies = d.enemies.map(e => new Entity(e));
  const eng = new BattleEngine(heroes, enemies);
  eng.run();
  return eng;
}

const GolemEngine = { SCENARIOS, Entity, skills, BattleEngine, buildEngine };
if (typeof module !== 'undefined' && module.exports) module.exports = GolemEngine;
if (typeof window !== 'undefined') window.GolemEngine = GolemEngine;
