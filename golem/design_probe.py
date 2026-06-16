# gemma 31B에게 "다음 큰 층을 야심차게 설계하라"(코드 말고 설계만) 1콜 — 설계 야심 calibration
"""작게 나오는 게 모델 탓인지 주문 탓인지 본다. 현재 로그라이크(부품0~4) 요약을 주고 다음 큰 층을
설계만 시킨다. 큰 그릇(여러 맞물리는 시스템)을 명시 요청. 결과 전문 + 토큰을 찍는다. 키 1콜."""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from config import force_utf8_stdout, get_api_keys, get_model  # noqa: E402
force_utf8_stdout()
os.environ["GENERATOR_MODEL"] = "gemma-4-31b-it"   # golem = 31solo
os.environ["CRITIC_MODEL"] = "gemma-4-31b-it"

PROMPT = """You have built a DETERMINISTIC, turn-based roguelike engine in Node.js
(CommonJS multi-file, Node built-ins only, NO Math.random, runnable as `node main.js --scenario N`,
graded by EXACT output lines). It is modular: dungeon / chase / combat / items / engine / main.

Systems that ALREADY exist:
- Grid dungeon ('#' wall, '.' floor). Player moves U/D/L/R; `steps` counts real moves.
- One enemy with deterministic chase (primary axis HORIZONTAL if |dx|>=|dy| else VERTICAL, etc.).
- Combat: player & enemy have hp/attack. Moving into the enemy = attack; an adjacent enemy attacks
  back; hp floors at 0; death at 0.
- Items: '$' gold(+10), '!' potion (command 'Q' quaffs to heal +5 capped), '^' trap(-3, one-shot),
  '>' stairs (descending ends the run).
- Equipment: 'W' weapon (+2 attack), 'A' armor (+1 defense; enemy damage = max(1, atk - defense)),
  '+' altar (full heal). Output already prints x,y,steps,enemy_x,enemy_y,player_hp,enemy_hp,gold,
  potions,descended,player_atk,defense.

YOUR TASK: design the NEXT MAJOR LAYER of this roguelike. Be AMBITIOUS — do not propose a single
mechanic. Propose SEVERAL interacting systems that together turn this into a deep, real roguelike,
and explain how they mesh turn-by-turn (emergent interaction is the point).

Hard constraints the design must respect:
- Fully DETERMINISTIC (no Math.random). If you need 'randomness' (e.g. procedural maps, loot, enemy
  variety), derive it from a fixed seed + a simple deterministic PRNG you define, so the same seed
  always gives the same run.
- Node built-ins only, multi-file CommonJS, CLI `node main.js --scenario N`, exact-line output.
- It must remain deterministically TESTABLE (exact output for a given scenario).

Output a DESIGN DOCUMENT ONLY — NO CODE. Cover:
1. The systems you add and WHY each makes the game deeper.
2. How they interact each turn (the turn order with all new systems woven in).
3. The new game state and the new output fields (so it stays exactly gradeable).
4. How you keep it deterministic + how you'd write scenarios that test the emergent interactions.
Be thorough and concrete. Use as much space as you need."""


def main():
    from llm import LLMClient
    key = get_api_keys()[0]
    client = LLMClient(api_key=key)
    print(f"[설계 프로브] model={get_model('generator')}, 1콜, 설계-only\n")
    resp = client.generate("generator", PROMPT)
    toks = client.tokens
    out = HERE / "_design_probe_out.md"
    out.write_text(resp, encoding="utf-8")
    print(resp)
    print("\n" + "=" * 60)
    print(f"[토큰] input={toks['input']} output={toks['output']} thinking={toks['thinking']} "
          f"out+think={toks['output']+toks['thinking']}/32k")
    print(f"[저장] {out}")


if __name__ == "__main__":
    main()
