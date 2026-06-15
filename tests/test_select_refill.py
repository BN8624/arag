# 병렬 인프라 2: select_run 연속리필 + early-stop 취소 테스트 (결정22, 콜 0)
"""checklist 2 검증: CAP개 시도를 한 번에 제출하고, 첫 통과가 나오면 아직 시작 안 한
시도를 취소해 8개를 다 돌지 않는다(콜 절약). _run_attempt는 가짜로 대체(API 콜 0).
"""

import threading
import time

import bank_db
import select_run


class _FakeDB:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_task(self, tid):
        return {"goal": "idea"}


def test_select_early_stop_cancels_pending(monkeypatch):
    monkeypatch.setattr(select_run, "get_api_keys", lambda: ["k1", "k2"])
    monkeypatch.setattr(select_run, "CARDS", ["T-x"])
    monkeypatch.setattr(select_run, "CAP", 8)
    monkeypatch.setattr(bank_db, "BankDB", _FakeDB)

    logs = []
    monkeypatch.setattr(select_run, "_log", lambda e: logs.append(e))

    ran = []
    lock = threading.Lock()

    def fake_attempt(tid, idea, attempt, frozen, key):
        with lock:
            ran.append(attempt)
        time.sleep(0.05)        # 다른 시도가 큐에 남아있도록 잠깐 점유
        return attempt == 2     # 2번째 시도가 통과

    monkeypatch.setattr(select_run, "_run_attempt", fake_attempt)

    rc = select_run.main(["T-000012", "31solo", "2"])   # width=2
    assert rc == 0
    assert logs[0]["cracked_at"] == 2
    assert logs[0]["attempts"] == len(ran)   # 누적 시도수 = 실제로 돈 수
    assert len(ran) < 8                       # early-stop: 8개를 다 안 돌았다
