# L4-5 frontier 캠페인: role-26all-cold(전부 26B, fresh 설계, 노트 OFF)부터 진행
"""PLAN §10 사다리의 L4(T-000007)·L5(T-000008)를 26B 단독 cold로 돌린다.

미측정으로 남아있던 "26B 머리 능력"을 frontier에서 처음 측정한다.
설계·시험출제·구현·비평 전부 26B(CRITIC_MODEL=26B), 노트 OFF(cold), fresh(--resume 아님).
auto_campaign.run_phase(테스트됨)를 그대로 재사용. 한 번에 하나, 인프라 내성.
장부: runs/auto_ledger.jsonl (phase="role-26all-cold").
"""

from config import force_utf8_stdout
from auto_campaign import run_phase, _default_runner, R26, R31

CARDS = ["T-000007"]  # L4 재측정 (화이트리스트 유지, 역할 비교)


def main() -> int:
    force_utf8_stdout()
    from bank_db import BankDB
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in CARDS}
    phases = [
        ("role-26all-cold", {"GENERATOR_MODEL": R26, "CRITIC_MODEL": R26}),
        ("role-26head31hands-cold", {"GENERATOR_MODEL": R31, "CRITIC_MODEL": R26}),
    ]
    for name, env in phases:
        print(f"[L45] {name} 시작 — 카드 {CARDS}")
        st = run_phase(name, env, ["--mode", "cold"], False, {}, cards,
                       _default_runner)
        print(f"[L45] {name} 완료 -> {st}")
    print("[L45] 장부: runs/auto_ledger.jsonl  리포트: python bank_report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
