"""Shared fixtures for service-layer tests.

Each test gets a fresh, seeded SQLite database in a tmp file (via the real
`init_db()` path, pointed there with FINALLY_DB_PATH) and a real PriceCache
pre-loaded with a few prices. No mocking of the DB — we exercise the actual
repository + schema so the service tests double as integration coverage.

`FINALLY_DB_PATH` is read at call time by `database._db_path()`, so setting the
env var is enough — no module reload needed.
"""

import pytest

from app.db import database
from app.market.cache import PriceCache


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A connection to a freshly seeded tmp database."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    database.init_db()

    conn = database.get_connection()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cache():
    """A PriceCache pre-seeded with deterministic prices for common tickers."""
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    c.set_price("MSFT", 420.0)
    c.set_price("GOOGL", 175.0)
    return c
