import pytest
from app.market.cache import PriceCache
from app.market.factory import create_source
from app.market.simulator import SimulatorSource
from app.market.massive import MassiveSource


def test_no_api_key_returns_simulator(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert isinstance(src, SimulatorSource)


def test_empty_api_key_returns_simulator(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "")
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert isinstance(src, SimulatorSource)


def test_whitespace_api_key_returns_simulator(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "   ")
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert isinstance(src, SimulatorSource)


def test_api_key_returns_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test_api_key_123")
    monkeypatch.delenv("MASSIVE_POLL_SECONDS", raising=False)
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert isinstance(src, MassiveSource)


def test_api_key_with_custom_interval(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test_api_key_123")
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", "5")
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert isinstance(src, MassiveSource)
    assert src._interval == 5.0


def test_default_interval_is_15(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test_api_key_123")
    monkeypatch.delenv("MASSIVE_POLL_SECONDS", raising=False)
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert src._interval == 15.0


def test_cache_is_passed_through_to_simulator(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert src.cache is cache


def test_cache_is_passed_through_to_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test_api_key_123")
    cache = PriceCache()
    src = create_source(cache, watched=lambda: set())
    assert src.cache is cache
