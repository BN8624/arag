# 결정17 관찰표: 31단독 cold로 8장 라운드로빈 ~50런 + 통짜/분할 교대, 통과율·분산·아키텍처 수집
"""난이도를 통과율로 사후 확정 + 아키텍처(통짜 vs 분할) 비교(결정17 운영 ③).

구성: 31단독(GENERATOR=CRITIC=31B — 26B 야간 사망 회피, L4-5 31단독 데이터 확보).
cold(노트 OFF) + --no-retry(각 런=독립 1점) + fresh.
8장 라운드로빈, 라운드마다 아키텍처를 뒤집어(짝수=분할 / 홀수=통짜) 카드×아키텍처 엮임 방지.
→ 각 카드가 통짜·분할을 고르게 받음. 끝나면 `python variance.py`로 카드별·whole별 통과율.

사용: python obs_run.py [TOTAL]   (기본 50)
"""

import sys

from config import force_utf8_stdout
from auto_campaign import run_phase, _default_runner, R31

TOTAL_DEFAULT = 50


def main(argv=None) -> int:
    force_utf8_stdout()
    args = list(argv if argv is not None else sys.argv[1:])
    total = int(args[0]) if args and args[0].isdigit() else TOTAL_DEFAULT
    from bank_db import BankDB
    with BankDB() as db:
        all_cards = {t["task_id"]: t for t in db.list_tasks()}
    ids = sorted(all_cards)
    env = {"GENERATOR_MODEL": R31, "CRITIC_MODEL": R31}  # 31단독
    print(f"[OBS] 31단독 cold ~{total}런 (통짜/분할 라운드 교대) — 카드 {ids}")
    ok = fail = 0
    done = 0
    rnd = 0
    while done < total:
        whole = (rnd % 2 == 1)  # 라운드마다 아키텍처 뒤집기
        arch = ["--whole"] if whole else []
        tag = "whole" if whole else "perfile"
        for tid in ids:
            if done >= total:
                break
            cards = {tid: all_cards[tid]}
            st = run_phase(f"obs-31solo-cold-{tag}", env,
                           ["--mode", "cold", "--no-retry", *arch],
                           False, {}, cards, _default_runner)
            ok += st["ok"]
            fail += st["fail"]
            done += 1
            print(f"[OBS] {done}/{total} {tid} [{tag}] -> "
                  f"ok={st['ok']} fail={st['fail']} (누적 ok={ok} fail={fail})")
        rnd += 1
    print(f"[OBS] 완료 ok={ok} fail={fail}. 확인: python variance.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
