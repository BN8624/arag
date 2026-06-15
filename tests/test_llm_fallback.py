# 가용성 폴백 테스트: generator(손) 429/5xx 소진 시 critic(31B)로 1회 강등 (콜 0, 가짜 client)
"""결정16 폴백 동작 검증. 실제 API 대신 가짜 client를 주입한다.
- #4(26손/31머리): 26B가 5xx 소진 → 31B 강등 성공.
- #1 31단독 / #2 26단독: generator==critic → 강등 대상 같음 → no-op(그대로 실패).
- critic(머리) 콜은 폴백 안 함.
"""

import types

import llm
from llm import LLMClient


class _FakeModels:
    def __init__(self, fail_models, calls):
        self.fail_models = fail_models   # 이 모델명이면 500을 던진다
        self.calls = calls               # 호출된 모델명 기록

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.fail_models:
            raise RuntimeError("500 INTERNAL. server is sad")
        return types.SimpleNamespace(text="OK")


def _client(fail_models):
    c = object.__new__(LLMClient)
    c.call_count = 0
    c.max_calls = None
    c.record_path = None
    c.tokens = {"input": 0, "output": 0, "thinking": 0}
    c.tokens_by_role = {"generator": {"input": 0, "output": 0, "thinking": 0},
                        "critic": {"input": 0, "output": 0, "thinking": 0}}
    calls = []
    c._client = types.SimpleNamespace(models=_FakeModels(fail_models, calls))
    return c, calls


def _set_models(monkeypatch, generator, critic):
    monkeypatch.setattr(llm, "get_model",
                        lambda role: generator if role == "generator" else critic)


def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *a, **k: None)


def test_generator_5xx_demotes_to_critic(monkeypatch):
    """26손이 5xx 소진하면 31머리로 강등해 성공한다(#4)."""
    _no_sleep(monkeypatch)
    _set_models(monkeypatch, generator="M26", critic="M31")
    c, calls = _client(fail_models={"M26"})
    out = c.generate("generator", "prompt")
    assert out == "OK"
    assert "M31" in calls          # 강등이 일어났다
    assert calls.count("M26") >= 1  # 26으로 먼저 시도했다


def test_no_fallback_when_generator_equals_critic(monkeypatch):
    """31단독·26단독은 강등 대상이 같아 no-op — 그대로 실패한다."""
    _no_sleep(monkeypatch)
    _set_models(monkeypatch, generator="M31", critic="M31")
    c, calls = _client(fail_models={"M31"})
    try:
        c.generate("generator", "prompt")
        assert False, "no-op이어야 하므로 RuntimeError가 나야 한다"
    except RuntimeError:
        pass
    assert set(calls) == {"M31"}   # 다른 모델로 강등 시도 없음


def test_critic_role_does_not_fall_back(monkeypatch):
    """머리(critic) 콜은 폴백 대상이 아니다 — 소진 시 그대로 실패."""
    _no_sleep(monkeypatch)
    _set_models(monkeypatch, generator="M26", critic="M31")
    c, calls = _client(fail_models={"M31"})
    try:
        c.generate("critic", "prompt")
        assert False, "critic은 폴백 안 하므로 실패해야 한다"
    except RuntimeError:
        pass
    assert set(calls) == {"M31"}
