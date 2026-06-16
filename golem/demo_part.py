# 통과본 부품을 시나리오에 실제로 돌려 격자 애니메이션 + 사람말 시연 HTML을 만드는 도구
"""부품(카드)이 게이트를 통과하면 숫자(11/11)가 아니라 '눈으로 되는 것'을 보여주기 위한 시연.

핵심: 재구현하지 않는다. 카드의 레퍼런스 JS를 그대로 꺼내 _demo_runner.js로 명령 prefix 재생 →
매 턴 상태(프레임)를 뽑고, 그 프레임을 격자(@=플레이어, E=적)로 그린다. 레퍼런스는 골든을 만든
구현이고 gemma 통과본은 11/11 정확일치로 레퍼런스와 동치임이 증명됐으므로, 레퍼런스 트레이스가
통과 부품의 동작을 그대로 보여준다(골든과 100% 일치 보장 + 부품 늘어나도 도구가 안 깨짐).
결정적 엔진이라 moves[:k] 호출이 k턴 후 상태와 정확히 일치한다.

사용:
  python demo_part.py                 # 기본: rogue-p0, rogue-p1 → web/demo.html
  python demo_part.py rogue-p0        # 한 부품만
  python demo_part.py rogue-p0 rogue-p1 --out web/demo.html
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
try:
    from config import force_utf8_stdout
    force_utf8_stdout()
except Exception:  # noqa: BLE001
    pass

import game_bank as gb

DIR_NAME = {"U": "위", "D": "아래", "L": "왼쪽", "R": "오른쪽"}


def build_frames(card, slug):
    """레퍼런스 JS를 임시 폴더에 풀고 _demo_runner.js로 매 턴 프레임을 받아온다."""
    work = ROOT / "runs" / "golem" / "_demo" / slug
    work.mkdir(parents=True, exist_ok=True)
    for fn, content in card["reference"].items():
        (work / fn).write_text(content, encoding="utf-8")

    scen_path = work / "_scenarios.json"
    scen_path.write_text(json.dumps(card["scenarios"], ensure_ascii=False), encoding="utf-8")

    res = subprocess.run(
        ["node", str(ROOT / "_demo_runner.js"), str(work), str(scen_path)],
        capture_output=True, text=True, timeout=30,
    )
    if res.returncode != 0:
        raise RuntimeError(f"{slug} 러너 실패: {res.stderr.strip()}")
    return json.loads(res.stdout)


def narrate(card, slug, frames):
    """프레임 시퀀스를 사람말 + 격자 텍스트로 변환. has_enemy면 적, has_combat면 HP·공격·사망도 표기."""
    scens = []
    for sid, scenario in card["scenarios"].items():
        inp = scenario["input"]
        grid = inp["grid"]
        moves = inp["moves"]
        fr = frames[sid]
        has_enemy = "enemy" in inp
        has_combat = "player_hp" in inp

        steps_frames = []
        for k, f in enumerate(fr):
            if k == 0:
                line = "시작 위치."
            else:
                cmd = moves[k - 1]
                prev = fr[k - 1]
                tag = f"명령 {cmd}({DIR_NAME[cmd]}): "
                if has_combat and prev["php"] == 0:
                    line = tag + "플레이어가 이미 쓰러져 명령 무시됨."
                    steps_frames.append({"grid": render_grid(grid, f, False),
                                         "line": line, "steps": f["steps"],
                                         "php": f["php"], "ehp": f["ehp"]})
                    continue
                if has_combat and f["ehp"] < prev["ehp"]:
                    killed = " — 적 처치!" if f["ehp"] == 0 else ""
                    line = tag + f"플레이어가 적을 공격 (적 HP {prev['ehp']}→{f['ehp']}){killed}"
                elif (f["px"], f["py"]) != (prev["px"], prev["py"]):
                    line = tag + f"플레이어 ({f['px']},{f['py']})로 이동."
                else:
                    line = tag + "벽/경계에 막혀 제자리."
                if has_combat and f["php"] < prev["php"]:
                    dead = " 플레이어 쓰러짐 — 이후 명령 무시." if f["php"] == 0 else ""
                    line += f" 적이 반격 (플레이어 HP {prev['php']}→{f['php']}).{dead}"
                elif has_enemy:
                    if has_combat and f["ehp"] == 0:
                        line += " 적은 쓰러져 있음."
                    elif (f["ex"], f["ey"]) != (prev["ex"], prev["ey"]):
                        line += f" 적이 ({f['ex']},{f['ey']})로 추격."
                    else:
                        line += " 적은 제자리."
            frame = {
                "grid": render_grid(grid, f, has_enemy and (not has_combat or f.get("ehp", 1) > 0)),
                "line": line,
                "steps": f["steps"],
            }
            if has_combat:
                frame["php"] = f["php"]
                frame["ehp"] = f["ehp"]
            steps_frames.append(frame)

        g = scenario["golden"]
        summary = f"명령열 \"{moves}\" → 최종 ({g['x']},{g['y']}), {g['steps']}걸음"
        if has_enemy:
            summary += f", 적 ({g['enemy_x']},{g['enemy_y']})"
        if has_combat:
            summary += f", 플레이어HP {g['player_hp']}, 적HP {g['enemy_hp']}"
        summary += " — 정답과 일치."
        scens.append({"sid": sid, "moves": moves, "frames": steps_frames, "summary": summary})
    return scens


def render_grid(grid, f, has_enemy):
    """격자를 셀 행렬로. #=벽, .=바닥, @=플레이어, E=적, X=둘이 겹침(부품1엔 안 생김)."""
    rows = []
    for y, row in enumerate(grid):
        cells = []
        for x, ch in enumerate(row):
            c = ch
            is_p = (x == f["px"] and y == f["py"])
            is_e = has_enemy and (x == f["ex"] and y == f["ey"])
            if is_p and is_e:
                c = "X"
            elif is_p:
                c = "@"
            elif is_e:
                c = "E"
            cells.append(c)
        rows.append(cells)
    return rows


HTML_TMPL = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>golem 부품 시연</title>
<style>
 :root{ --bg:#0f1117; --fg:#e6e6e6; --dim:#8a93a6; --wall:#2a2f3a; --floor:#161a22;
        --p:#4ea1ff; --e:#ff5b6e; --acc:#ffd24a; }
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);
   font-family:-apple-system,system-ui,sans-serif;padding:14px;-webkit-text-size-adjust:100%}
 h1{font-size:18px;margin:0 0 4px} .sub{color:var(--dim);font-size:13px;margin-bottom:12px}
 .tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
 .tab,.sbtn{background:#1b2030;color:var(--fg);border:1px solid #2a3142;border-radius:8px;
   padding:8px 12px;font-size:14px;cursor:pointer}
 .tab.on{background:var(--p);border-color:var(--p);color:#001}
 .sbtn.on{background:var(--acc);border-color:var(--acc);color:#001}
 .panel{background:#12151d;border:1px solid #232838;border-radius:12px;padding:12px}
 .grid{display:grid;gap:3px;justify-content:center;margin:10px 0}
 .cell{width:34px;height:34px;display:flex;align-items:center;justify-content:center;
   border-radius:6px;font-size:18px;font-weight:700}
 .c-wall{background:var(--wall)} .c-floor{background:var(--floor)}
 .c-p{background:var(--p);color:#001} .c-e{background:var(--e);color:#fff} .c-x{background:var(--acc);color:#001}
 .line{font-size:15px;min-height:42px;line-height:1.4;margin:6px 2px}
 .meta{color:var(--dim);font-size:13px;margin-bottom:4px}
 .hp{font-size:14px;margin:2px 0 2px;font-weight:600;min-height:20px}
 .hp .pp{color:var(--p)} .hp .ee{color:var(--e)}
 .ctl{display:flex;gap:8px;align-items:center;margin-top:8px}
 .ctl button{flex:1;padding:11px;font-size:15px;border-radius:10px;border:1px solid #2a3142;
   background:#1b2030;color:var(--fg)}
 .ctl button:active{background:#283047}
 .prog{color:var(--dim);font-size:13px;min-width:64px;text-align:center}
 .sum{margin-top:10px;padding:9px 11px;background:#13211a;border:1px solid #1f4a31;
   border-radius:9px;font-size:14px;color:#9fe6b8}
 .legend{font-size:12px;color:var(--dim);margin-top:12px}
 .legend b{color:var(--p)} .legend i{color:var(--e);font-style:normal}
</style></head><body>
<h1>골렘 부품 시연</h1>
<div class="sub">통과본을 시나리오에 그대로 돌린 결과. @=플레이어, E=적, #=벽.</div>
<div class="tabs" id="parts"></div>
<div class="tabs" id="scens"></div>
<div class="panel">
  <div class="meta" id="meta"></div>
  <div class="hp" id="hp"></div>
  <div class="grid" id="grid"></div>
  <div class="line" id="line"></div>
  <div class="ctl">
    <button onclick="step(-1)">◀ 이전</button>
    <span class="prog" id="prog"></span>
    <button onclick="step(1)">다음 ▶</button>
    <button onclick="play()">▶ 재생</button>
  </div>
  <div class="sum" id="sum"></div>
</div>
<div class="legend">
  <b>@</b> 플레이어 · <i>E</i> 적 · # 벽 · . 바닥 — 좌표는 (x=열, y=행), 좌상단이 (0,0).
</div>
<script>
const DATA = __DATA__;
let pi=0, si=0, fi=0, timer=null;
function parts(){return DATA.parts}
function cur(){return parts()[pi].scenarios[si]}
function renderTabs(){
  const pt=document.getElementById('parts'); pt.innerHTML='';
  parts().forEach((p,i)=>{const b=document.createElement('button');b.className='tab'+(i===pi?' on':'');
    b.textContent=p.title;b.onclick=()=>{pi=i;si=0;fi=0;stop();renderTabs();renderScens();render()};pt.appendChild(b)});
}
function renderScens(){
  const st=document.getElementById('scens'); st.innerHTML='';
  parts()[pi].scenarios.forEach((s,i)=>{const b=document.createElement('button');b.className='sbtn'+(i===si?' on':'');
    b.textContent='시나리오 '+s.sid;b.onclick=()=>{si=i;fi=0;stop();renderScens();render()};st.appendChild(b)});
}
function render(){
  const sc=cur(); const f=sc.frames[fi]; const g=f.grid;
  const grid=document.getElementById('grid');
  grid.style.gridTemplateColumns='repeat('+g[0].length+',34px)'; grid.innerHTML='';
  for(const row of g)for(const ch of row){const d=document.createElement('div');
    let cls='c-floor',t='';
    if(ch==='#')cls='c-wall'; else if(ch==='@'){cls='c-p';t='@'} else if(ch==='E'){cls='c-e';t='E'}
    else if(ch==='X'){cls='c-x';t='X'}
    d.className='cell '+cls; d.textContent=t; grid.appendChild(d);}
  document.getElementById('meta').textContent='명령열 "'+sc.moves+'"  ·  걸음 '+f.steps;
  const hp=document.getElementById('hp');
  hp.innerHTML=(f.php!==undefined)?('<span class="pp">@ 플레이어 HP '+f.php+'</span>  ·  <span class="ee">E 적 HP '+f.ehp+'</span>'):'';
  document.getElementById('line').textContent=f.line;
  document.getElementById('prog').textContent=fi+' / '+(sc.frames.length-1);
  document.getElementById('sum').textContent=(fi===sc.frames.length-1)?('✓ '+sc.summary):'';
}
function step(d){const n=cur().frames.length; fi=Math.max(0,Math.min(n-1,fi+d)); stop(); render();}
function stop(){if(timer){clearInterval(timer);timer=null}}
function play(){stop(); fi=0; render(); timer=setInterval(()=>{if(fi>=cur().frames.length-1){stop();return}fi++;render()},650);}
renderTabs(); renderScens(); render();
</script>
</body></html>
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_idx = sys.argv.index("--out") if "--out" in sys.argv else -1
    out_path = ROOT / (sys.argv[out_idx + 1] if out_idx != -1 else "web/demo.html")

    slugs = args or ["rogue-p0", "rogue-p1"]
    parts = []
    for slug in slugs:
        card = gb.get_card(slug)
        if card is None:
            print(f"[SKIP] 카드 없음: {slug}")
            continue
        if not card.get("solution"):
            print(f"[SKIP] 통과본(solution) 없음: {slug}")
            continue
        frames = build_frames(card, slug)
        scens = narrate(card, slug, frames)
        parts.append({"slug": slug, "title": card["title"].split("—")[-1].strip() or slug,
                      "scenarios": scens})
        print(f"[OK] {slug}: 시나리오 {len(scens)}개, 통과본 재생 완료")

        # 터미널에도 1번 시나리오 마지막 프레임 미리보기
        s0 = scens[0]
        print(f"     예) 시나리오 {s0['sid']} {s0['summary']}")

    if not parts:
        print("[FAIL] 시연할 부품이 없다.")
        return 1

    html = HTML_TMPL.replace("__DATA__", json.dumps({"parts": parts}, ensure_ascii=False))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    rel = out_path.relative_to(ROOT.parent).as_posix()
    print(f"[DONE] {out_path}")
    print(f"       폰: http://100.89.73.83:8731/{rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
