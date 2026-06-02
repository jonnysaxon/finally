"""Fixtures for API tests.

A real FastAPI app (full lifespan: init_db + background tasks) against a fresh
seeded tmp database, but with the live market source swapped for a deterministic
seeded cache and a fake source so prices and the known-symbol universe are stable.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market.cache import PriceCache


class FakeSource:
    """Deterministic source: a no-op run loop and a fixed universe."""

    def __init__(self, universe):
        self._universe = {t.upper() for t in universe}

    @property
    def universe(self):
        return self._universe

    def knows(self, ticker: str) -> bool:
        return ticker.upper() in self._universe

    async def run(self):  # pragma: no cover - never awaited in tests
        return


SEED_PRICES = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
    "TSLA": 250.0,
    "NVDA": 120.0,
    "META": 500.0,
    "JPM": 200.0,
    "V": 280.0,
    "NFLX": 600.0,
    "PYPL": 70.0,  # known but not watched by default
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient over a freshly seeded tmp DB with a deterministic cache/source.

    LLM_MOCK is on so any chat path that reaches the LLM is deterministic; the
    chat tests additionally stub handle_chat directly.
    """
    db_file = tmp_path / "api.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    monkeypatch.setenv("LLM_MOCK", "true")

    # `database._db_path()` reads FINALLY_DB_PATH at call time, so a fresh app is
    # all we need — no module reload.
    app = create_app()

    cache = PriceCache()
    for ticker, price in SEED_PRICES.items():
        cache.set_price(ticker, price)
    source = FakeSource(SEED_PRICES.keys())

    with TestClient(app) as c:
        # Override the live source/cache the lifespan installed with our stubs.
        app.state.cache = cache
        app.state.source = source
        yield c
