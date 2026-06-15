# 키×모델 RPD 트래커 테스트 (결정23, 콜 0). 임시 파일로 격리.
"""record/count/is_exhausted/태평양날짜 버킷/지문저장(원문 미저장)/리포트 검증."""

import json

import pytest

import key_usage


@pytest.fixture
def store(tmp_path, monkeypatch):
    p = tmp_path / "key_usage.json"
    monkeypatch.setattr(key_usage, "USAGE_PATH", p)
    return p


def test_record_and_count(store):
    assert key_usage.count("KEYAAA", "m31") == 0
    assert key_usage.record("KEYAAA", "m31") == 1
    assert key_usage.record("KEYAAA", "m31") == 2
    assert key_usage.count("KEYAAA", "m31") == 2
    # 다른 모델·다른 키는 독립 버킷
    assert key_usage.count("KEYAAA", "m26") == 0
    assert key_usage.count("KEYBBB", "m31") == 0


def test_does_not_store_raw_key(store):
    key_usage.record("super-secret-raw-key-123", "m31")
    text = store.read_text(encoding="utf-8")
    assert "super-secret-raw-key-123" not in text       # 원문 미저장
    assert key_usage.fingerprint("super-secret-raw-key-123") in text


def test_is_exhausted_threshold(store, monkeypatch):
    monkeypatch.setattr(key_usage, "RPD_LIMIT", 100)
    monkeypatch.setattr(key_usage, "RPD_RESERVE", 10)   # 차단선 = 90
    key_usage.record("K", "m", n=89)
    assert not key_usage.is_exhausted("K", "m")
    key_usage.record("K", "m")                           # 90
    assert key_usage.is_exhausted("K", "m")


def test_pacific_date_bucket_resets(store, monkeypatch):
    """태평양 날짜가 바뀌면 새 버킷 = 0 (자동 복귀)."""
    monkeypatch.setattr(key_usage, "pacific_date", lambda: "2026-06-15")
    key_usage.record("K", "m", n=5)
    assert key_usage.count("K", "m") == 5
    monkeypatch.setattr(key_usage, "pacific_date", lambda: "2026-06-16")
    assert key_usage.count("K", "m") == 0                # 새 날짜 = 리셋
    # 과거 버킷은 파일에 남아있다(이력 보존)
    assert "2026-06-15" in store.read_text(encoding="utf-8")


def test_report_lists_today(store):
    key_usage.record("K1", "m31", n=3)
    out = key_usage.report()
    assert "m31" in out and key_usage.fingerprint("K1") in out
