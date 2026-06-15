# 콜 재시도 정책 테스트: 429/5xx는 안 죽고 무한 재시도, RPD만 즉시 차단 (콜 0, 가짜 client)
"""운영=31solo 단독(폴백 없음). 429(RPM)·5xx는 죽이지 않고 재시도 → 서버 복귀 시 성공.
RPD 일일쿼터만 즉시 DailyQuotaExceeded로 전파(2분 대기로 안 풀림 — 풀이 다른 키로 넘긴다).
"""

import types

import pytest

import llm
from llm import DailyQuotaExceeded, LLMClient


class _FlakyModels:
    """fail_times번 err를 던진 뒤 OK를 반환하는 가짜(서버 복귀 모사)."""

    def __init__(self, fail_times, err, calls):
        self.left = fail_times
        self.err = err
        self.calls = calls

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if self.left > 0:
            self.left -= 1
            raise self.err
        return types.SimpleNamespace(text="OK")


def _client(fail_times, err):
    c = object.__new__(LLMClient)
    c.call_count = 0
    c.max_calls = None
    c.record_path = None
    c.tokens = {"input": 0, "output": 0, "thinking": 0}
    c.tokens_by_role = {"generator": {"input": 0, "output": 0, "thinking": 0},
                        "critic": {"input": 0, "output": 0, "thinking": 0}}
    c._api_key = "K"
    calls = []
    c._client = types.SimpleNamespace(models=_FlakyModels(fail_times, err, calls))
    return c, calls


def _solo31(monkeypatch):
    monkeypatch.setattr(llm, "get_model", lambda role: "M31")
    monkeypatch.setattr(llm.time, "sleep", lambda *a, **k: None)


def test_5xx_retries_until_success(monkeypatch):
    """5xx 폭풍은 죽지 않고 재시도 → 서버 복귀 시 성공(백오프 4회 + 그 뒤 무한)."""
    _solo31(monkeypatch)
    c, calls = _client(fail_times=6, err=RuntimeError("500 INTERNAL. server is sad"))
    assert c.generate("generator", "prompt") == "OK"
    assert len(calls) == 7              # 6번 실패 후 7번째 성공


def test_429_rpm_retries_until_success(monkeypatch):
    """RPM 429도 죽지 않고 재시도 → 풀릴 때 성공."""
    _solo31(monkeypatch)
    c, calls = _client(fail_times=3, err=RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert c.generate("critic", "prompt") == "OK"
    assert len(calls) == 4


def test_daily_quota_raises_immediately(monkeypatch):
    """RPD 일일쿼터는 재시도 않고 즉시 DailyQuotaExceeded로 전파(키 차단용)."""
    _solo31(monkeypatch)
    c, calls = _client(
        fail_times=99,
        err=RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded per day"))
    with pytest.raises(DailyQuotaExceeded):
        c.generate("generator", "prompt")
    assert len(calls) == 1              # 재시도 없이 1콜에 즉시 차단


def test_client_4xx_propagates(monkeypatch):
    """일시장애 아닌 4xx(잘못된 요청)는 재시도 않고 그대로 전파."""
    _solo31(monkeypatch)
    c, calls = _client(fail_times=99, err=RuntimeError("400 INVALID_ARGUMENT"))
    with pytest.raises(RuntimeError):
        c.generate("generator", "prompt")
    assert len(calls) == 1
