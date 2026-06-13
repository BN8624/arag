"""야간 무인 캠페인 테스트 (콜0): cold→필터→warm, 예산·장부."""

import json

import night_run


class FakeDB:
    def list_tasks(self):
        return [{"task_id": f"T-00000{i}"} for i in range(1, 4)]  # 3장

    def get_task(self, tid):
        return {"task_id": tid, "goal": f"goal for {tid}"}


def test_campaign_cold_then_warm_with_budget(tmp_path):
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    seen = []

    def runner(args):
        # args = [goal, --task-id, T, --mode, cold|warm]
        mode = args[args.index("--mode") + 1]
        seen.append(mode)
        clock["t"] += 10.0  # 런당 10초
        return 0

    filtered = {"called": False}

    def fake_filter():
        filtered["called"] = True
        # 필터는 cold가 다 끝난 뒤 호출돼야 한다
        assert "warm" not in seen
        return {"lessons.json": {"kept": 1, "dropped": 2}}

    ledger = tmp_path / "ledger.jsonl"
    stats = night_run.campaign(FakeDB(), count=3, budget_sec=120, runner=runner,
                               now=now, ledger_path=ledger, filter_fn=fake_filter,
                               cold_fraction=0.5)

    # 예산 120s, cold 절반(60s)=6런, warm 후반(60s)=6런
    assert filtered["called"]
    assert stats["cold"]["ok"] == 6
    assert stats["warm"]["ok"] == 6
    assert seen[:6] == ["cold"] * 6
    assert seen[6:] == ["warm"] * 6

    # 장부 증분 기록 확인
    lines = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 12
    assert lines[0]["mode"] == "cold" and lines[0]["round"] == 1
    assert lines[-1]["mode"] == "warm"
    assert lines[3]["round"] == 2  # 3장이므로 4번째 런은 round 2


def test_campaign_continues_past_failures(tmp_path):
    clock = {"t": 0.0}

    def runner(args):
        clock["t"] += 10.0
        return 1  # 전부 실패해도 멈추지 않아야 함

    stats = night_run.campaign(FakeDB(), count=3, budget_sec=60,
                               runner=runner, now=lambda: clock["t"],
                               ledger_path=tmp_path / "l.jsonl",
                               filter_fn=lambda: None, cold_fraction=0.5)
    # 실패해도 예산 내내 계속 (cold 30s=3런, warm 30s=3런)
    assert stats["cold"]["fail"] == 3
    assert stats["warm"]["fail"] == 3
