"""Shared fixtures for the LLM tests.

Everything here runs fully offline: a real seeded SQLite DB on a tmp file and the
real PriceCache (no network, no LiteLLM). LLM_MOCK is forced on so handle_chat
never reaches the network.
"""

import pytest

from app.db import database, repository
from app.market.cache import PriceCache


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """Force deterministic mock LLM for every test in this package.

    (The project-wide guard in tests/conftest.py separately blocks any real
    network LLM call, so a missing env var can never cause a hang.)
    """
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A freshly seeded SQLite connection on a tmp file."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "test.db"))
    database.init_db()
    conn = database.get_connection()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cache():
    """A PriceCache seeded with prices for the default watchlist tickers."""
    c = PriceCache()
    seed = {
        "AAPL": 190.0,
        "GOOGL": 175.0,
        "MSFT": 420.0,
        "AMZN": 185.0,
        "TSLA": 250.0,
        "NVDA": 120.0,
        "META": 500.0,
        "JPM": 200.0,
        "V": 280.0,
        "NFLX": 650.0,
    }
    for ticker, price in seed.items():
        c.set_price(ticker, price)
    return c


class FakeSource:
    """Minimal MarketSource stand-in for watchlist validation in tests."""

    def __init__(self, universe):
        self._universe = {t.upper() for t in universe}

    @property
    def universe(self):
        return self._universe

    def knows(self, ticker):
        return ticker.upper() in self._universe


@pytest.fixture
def source():
    return FakeSource(
        ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX", "PYPL"]
    )


@pytest.fixture
def seed_position(db, cache):
    """Helper to put an opening position in the DB via a real buy."""
    from app.services import portfolio

    def _seed(ticker, quantity):
        portfolio.execute_trade(db, cache, ticker, "buy", quantity)

    return _seed


# Re-export repository for convenience in tests.
repo = repository
