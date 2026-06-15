# 병렬 인프라 1: 키풀 + 키별 페이서 테스트 (결정22, 콜 0)
"""checklist 1 검증: .env 키 리스트 로더 / 키별 페이서(같은 키만 직렬, 다른 키 독립) /
KeyPool 체크아웃·반납·고갈 블록 / 단일키 하위호환.
"""

import os
from queue import Empty

import pytest

import config
import llm
from llm import AllKeysExhausted, KeyPool, LLMClient


# --- config.get_api_keys: .env 키 리스트 로더 ---

def _clear_keys(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda *a, **k: True)  # 실제 .env 차단
    for name in list(os.environ):
        if name.startswith("GOOGLE_API_KEY"):
            monkeypatch.delenv(name, raising=False)


def test_get_api_keys_numbered_numeric_sort(monkeypatch):
    """GOOGLE_API_KEY_N 을 *숫자* 순으로 모은다(10이 2 뒤)."""
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY_2", "kk2")
    monkeypatch.setenv("GOOGLE_API_KEY_10", "kk10")
    monkeypatch.setenv("GOOGLE_API_KEY_1", "kk1")
    assert config.get_api_keys() == ["kk1", "kk2", "kk10"]


def test_get_api_keys_fallback_single(monkeypatch):
    """번호 키가 없으면 단일 GOOGLE_API_KEY로 폴백(하위호환)."""
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "solo")
    assert config.get_api_keys() == ["solo"]
    assert config.get_api_key() == "solo"


def test_get_api_keys_excludes_placeholder_and_empty(monkeypatch):
    """빈 값·플레이스홀더 키는 풀에서 제외."""
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY_1", "real")
    monkeypatch.setenv("GOOGLE_API_KEY_2", config.PLACEHOLDER)
    monkeypatch.setenv("GOOGLE_API_KEY_3", "")
    assert config.get_api_keys() == ["real"]


def test_get_api_keys_raises_when_none(monkeypatch):
    _clear_keys(monkeypatch)
    with pytest.raises(RuntimeError):
        config.get_api_keys()


# --- 키별 페이서: 같은 키만 직렬, 다른 키는 독립 ---

def test_pacer_same_key_serialized_diff_key_independent(monkeypatch):
    llm._pacers.clear()
    state = {"t": 1000.0, "slept": []}
    monkeypatch.setattr(llm.time, "monotonic", lambda: state["t"])

    def fake_sleep(s):
        state["slept"].append(s)
        state["t"] += s
    monkeypatch.setattr(llm.time, "sleep", fake_sleep)

    a = object.__new__(LLMClient); a._api_key = "A"
    b = object.__new__(LLMClient); b._api_key = "B"

    a._wait_interval()              # 키A 첫 콜: 대기 없음
    assert state["slept"] == []
    a._wait_interval()              # 키A 두 번째: 4초 직렬화
    assert state["slept"] == [4.0]
    b._wait_interval()              # 키B 첫 콜: A와 독립 → 대기 없음
    assert state["slept"] == [4.0]


# --- 동적 페이서(AIMD): 429면 곱연산↑, 성공이면 가산↓, 키마다 독립 ---

def test_dynamic_pacer_aimd_clamps_and_recovers():
    llm._pacers.clear()
    k = "K"
    assert llm._get_pacer(k)["interval"] == llm.MIN_INTERVAL_SEC  # 하한서 시작
    for _ in range(10):                       # 429 누적 → 상한 클램프
        llm._nudge_interval(k, hit_limit=True)
    assert llm._get_pacer(k)["interval"] == llm.MAX_INTERVAL_SEC
    for _ in range(100):                      # 성공 누적 → 하한 회복
        llm._nudge_interval(k, hit_limit=False)
    assert llm._get_pacer(k)["interval"] == llm.MIN_INTERVAL_SEC


def test_dynamic_pacer_per_key_isolation():
    """한 키가 429로 감속해도 다른 키는 하한(풀속도) 유지."""
    llm._pacers.clear()
    llm._nudge_interval("slow", hit_limit=True)
    assert llm._get_pacer("slow")["interval"] > llm.MIN_INTERVAL_SEC
    assert llm._get_pacer("fast")["interval"] == llm.MIN_INTERVAL_SEC


# --- KeyPool: 체크아웃·반납·고갈 블록 ---

def test_keypool_distinct_keys_and_return():
    pool = KeyPool(["k1", "k2"])
    assert pool.size == 2
    with pool.checkout() as a, pool.checkout() as b:
        assert {a, b} == {"k1", "k2"}   # 동시 워커는 서로 다른 키
    # 반납됐으므로 다시 둘 다 빌릴 수 있다
    with pool.checkout() as a, pool.checkout() as b:
        assert {a, b} == {"k1", "k2"}


def test_keypool_blocks_when_exhausted():
    pool = KeyPool(["only"])
    with pool.checkout():
        with pytest.raises(Empty):
            with pool.checkout(timeout=0.05):
                pass


def test_keypool_default_uses_config(monkeypatch):
    monkeypatch.setattr(llm, "get_api_keys", lambda: ["x", "y", "z"])
    pool = KeyPool()
    assert pool.size == 3


# --- RPD 소진 인지 체크아웃 (결정23) ---

def test_keypool_skips_exhausted_key(monkeypatch):
    """소진된 키는 건너뛰고 여유 있는 키를 빌려준다."""
    import key_usage
    # k1만 모델 m에 대해 소진
    monkeypatch.setattr(key_usage, "is_exhausted",
                        lambda key, model: key == "k1")
    pool = KeyPool(["k1", "k2"], models=["m"])
    seen = set()
    for _ in range(4):
        with pool.checkout() as k:
            seen.add(k)
    assert seen == {"k2"}          # 소진된 k1은 절대 안 빌려줌


def test_keypool_all_exhausted_raises(monkeypatch):
    import key_usage
    monkeypatch.setattr(key_usage, "is_exhausted", lambda key, model: True)
    pool = KeyPool(["k1", "k2"], models=["m"])
    with pytest.raises(AllKeysExhausted):
        with pool.checkout():
            pass


def test_keypool_no_models_skips_rpd_check():
    """models 미지정이면 RPD 검사 안 함(하위호환)."""
    pool = KeyPool(["k1", "k2"])    # models=None
    with pool.checkout() as a, pool.checkout() as b:
        assert {a, b} == {"k1", "k2"}
