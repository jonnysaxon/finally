"""Tests for watchlist business rules (PLAN §13.11)."""

import pytest

from app.db import repository
from app.services import watchlist as svc
from app.services.watchlist import WatchlistError


class FakeSource:
    """Minimal MarketSource stand-in: knows a fixed universe."""

    def __init__(self, universe):
        self._universe = {t.upper() for t in universe}

    @property
    def universe(self):
        return self._universe

    def knows(self, ticker: str) -> bool:
        return ticker.upper() in self._universe


def test_add_known_ticker(db):
    source = FakeSource(["PYPL"])
    svc.add_ticker(db, source, "PYPL")
    assert "PYPL" in repository.list_watchlist(db)


def test_add_unknown_ticker_raises(db):
    source = FakeSource(["AAPL"])
    with pytest.raises(WatchlistError, match="Unknown ticker"):
        svc.add_ticker(db, source, "ZZZZ")
    assert "ZZZZ" not in repository.list_watchlist(db)


def test_add_is_case_insensitive(db):
    source = FakeSource(["PYPL"])
    svc.add_ticker(db, source, "pypl")
    assert "PYPL" in repository.list_watchlist(db)


def test_add_duplicate_is_noop(db):
    source = FakeSource(["AAPL"])
    before = repository.list_watchlist(db)
    assert "AAPL" in before  # seeded
    svc.add_ticker(db, source, "AAPL")
    after = repository.list_watchlist(db)
    assert after.count("AAPL") == 1
    assert len(after) == len(before)


def test_add_empty_ticker_raises(db):
    source = FakeSource(["AAPL"])
    with pytest.raises(WatchlistError, match="empty"):
        svc.add_ticker(db, source, "   ")


def test_remove_existing_ticker(db):
    assert "AAPL" in repository.list_watchlist(db)
    svc.remove_ticker(db, "AAPL")
    assert "AAPL" not in repository.list_watchlist(db)


def test_remove_missing_ticker_is_noop(db):
    before = repository.list_watchlist(db)
    svc.remove_ticker(db, "NOTINLIST")
    assert repository.list_watchlist(db) == before
