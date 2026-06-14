# 결정17 난이도 재정의: 기존 8장 카드에 spec_complete/oracle_verified 필드 추가 (일회성)
"""task_json에 spec_complete·oracle_verified를 채워 넣는다(결정17 최소 스키마).

spec_complete: goal이 오라클이 요구하는 행동을 빠짐없이 적었나.
  - T-000008만 false: 오라클이 "손상된 세이브 복구"를 검사하는데 goal엔 손상 케이스 언급 없음
    (= 출제불량, 난이도로 오인 금지 케이스). 나머지 7장은 goal이 수용기준을 다 담음.
oracle_verified: 사람이 행동-기준 검증을 했나 — 아직 안 했으므로 전부 false(샘플 검증은 후속).

멱등(이미 있으면 덮어씀). 사용: python migrate_card_fields.py
"""

import json

from bank_db import BankDB

SPEC_COMPLETE = {
    "T-000001": True, "T-000002": True, "T-000003": True, "T-000004": True,
    "T-000005": True, "T-000006": True, "T-000007": True,
    "T-000008": False,  # 손상 세이브 복구가 오라클엔 있고 goal엔 없음
}


def main() -> int:
    with BankDB() as db:
        rows = db.conn.execute("SELECT task_id, task_json FROM tasks").fetchall()
        for row in rows:
            tid = row["task_id"]
            card = json.loads(row["task_json"])
            card["spec_complete"] = SPEC_COMPLETE.get(tid, True)
            card["oracle_verified"] = False
            db.conn.execute("UPDATE tasks SET task_json = ? WHERE task_id = ?",
                            (json.dumps(card, ensure_ascii=False), tid))
            print(f"[OK] {tid} spec_complete={card['spec_complete']} "
                  f"oracle_verified=False")
        db.conn.commit()
    print(f"[DONE] {len(rows)} cards updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
