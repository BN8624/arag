# auto-towerdef 카드를 골든 그대로 두고 규칙에 '종료 타이밍 정밀화 + 워크드 트레이스'만 덧붙인 -tight 카드로 적재(단일변수 실험)
"""사용: python golem/bank_add_towerdef_tight.py  (키 안 씀)
원본 auto-towerdef의 scenarios/golden/solution/reference를 그대로 복사하고, rules에만
실행 의미(틱/종료 off-by-one 제거 + 시나리오1 트레이스)를 덧붙인다. = Claude 정밀화가
0/11을 뚫는지 보는 대조 카드. 워커는 rules를 그대로 받으므로 규칙이 유일 변수다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import force_utf8_stdout
force_utf8_stdout()
import game_bank

SRC_SLUG = "auto-towerdef"
DST_SLUG = "auto-towerdef-tight"

# 원본 규칙이 안 못박은 부분(종료를 +1 전에 판정하나 후에 판정하나)을 명시한다.
# 손 트레이스로 시나리오 1·2·3 골든을 모두 만족하는 일관 해석을 확인하고 박았다.
CLARIFICATION = """

== EXACT EXECUTION SEMANTICS (read carefully — these pin down tick/termination timing) ==

The main loop is EXACTLY this:

  currentTick = 0
  loop forever:
    run the 5 phases above, in order, for this tick
        (the SPAWN phase uses `currentTick` to decide which waves spawn now)
    if TERMINATION holds now (see below):
        STOP immediately. Do NOT increment currentTick.
    else:
        currentTick += 1
        continue

TERMINATION holds only when BOTH are true, checked at the END of a tick (after the SPAWN phase):
  (a) every scheduled wave has already spawned, i.e. currentTick >= (the largest `tick` value in waves), AND
  (b) there are zero active enemies remaining on the field.
BOTH are required. If any enemy is still alive on the path, the game does NOT end even if all waves
have already spawned.

The `ticks` output is the value of `currentTick` at the moment termination holds — i.e. the index of
the tick that was just processed. Because you STOP before incrementing, the terminating tick is counted
once, never twice.

Worked trace of Scenario 1 (path length 2, one tower at [0,0] dmg 10 range 1, one wave hp 5 at tick 0):
  tick 0: phases 1-4 do nothing (no enemy on the field yet); SPAWN phase: enemy E appears at pathIndex 0.
          termination? an enemy remains -> NO. So currentTick becomes 1.
  tick 1: ATTACK: tower at [0,0] vs E at pathIndex 0 = [0,0], Manhattan distance 0 <= range 1 -> hit,
          E.hp = 5 - 10 = -5. DEATH: E.hp <= 0 -> E removed, kills = 1. MOVEMENT/LEAK/SPAWN: nothing.
          termination? all waves spawned (currentTick 1 >= 0) AND no enemies left -> YES. STOP.
  Result: kills=1, leaks=0, ticks=1.  (NOT ticks=2 — you stop BEFORE incrementing currentTick.)
"""


def main():
    src = game_bank.get_card(SRC_SLUG)
    if src is None:
        print(f"[ERR] 원본 카드 '{SRC_SLUG}' 없음 — 캠페인 적재본이 필요")
        return 2
    card = {
        "slug": DST_SLUG,
        "title": src["title"] + " (tight rules)",
        "genre": src.get("genre", ""),
        "mechanics": src.get("mechanics", ""),
        "rules": src["rules"].rstrip() + CLARIFICATION,
        "scenarios": src["scenarios"],          # 골든 그대로 (단일변수 보장)
        "solution": src.get("solution", {}),
        "reference": src.get("reference", {}),
        "notes": (src.get("notes", "") + " | +tight: 종료타이밍 정밀화 + 시나리오1 트레이스(Claude)").strip(" |"),
    }
    game_bank.save_card(card)
    # 검증: 골든이 원본과 동일한가 + 규칙이 길어졌는가
    chk = game_bank.get_card(DST_SLUG)
    same_golden = chk["scenarios"] == src["scenarios"]
    print(f"[OK] 적재 '{DST_SLUG}' — 골든동일={same_golden}, "
          f"rules {len(src['rules'])}->{len(chk['rules'])}자, 시나리오 {len(chk['scenarios'])}개")
    return 0 if same_golden else 1


if __name__ == "__main__":
    raise SystemExit(main())
