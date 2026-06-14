# L4 분산/노트효과 측정: role-26all로 cold N회 + warm N회 단발(--no-retry) 반복
"""L4(T-000007)에서 cold vs warm 통과율을 N회씩 재서 (1)분산 (2)노트 효과(D)를 본다.

--no-retry로 각 런 = 독립 1점(자동재시도가 fail+pass를 섞지 않게). fresh(설계도 매번 새로).
역할은 26all(머리·손 둘 다 26B). 끝나면 `python variance.py T-000007`로 통과율·델타 확인.
장부: runs/auto_ledger.jsonl (phase=L4-26all-cold / L4-26all-warm).
"""

from config import force_utf8_stdout
from auto_campaign import run_phase, _default_runner, R26

CARD = "T-000007"
N = 3


def main() -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    with BankDB() as db:
        cards = {CARD: db.get_task(CARD)}
    env = {"GENERATOR_MODEL": R26, "CRITIC_MODEL": R26}
    plan = [("L4-26all-cold", ["--mode", "cold", "--no-retry"]),
            ("L4-26all-warm", ["--mode", "warm", "--no-retry"])]
    for name, extra in plan:
        for rep in range(1, N + 1):
            print(f"[L45] {name} rep {rep}/{N}")
            st = run_phase(f"{name}", env, extra, False, {}, cards,
                           _default_runner)
            print(f"[L45] {name} rep {rep} -> {st}")
    print("[L45] 완료. 확인: python variance.py T-000007")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
