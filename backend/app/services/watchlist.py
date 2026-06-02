"""Watchlist business rules (PLAN §13.11).

Adds are validated against the active market source's universe so the watchlist
never holds a symbol that can't be priced. Used by both the REST watchlist
endpoints and the LLM auto-executor.

Commit is owned by the caller (BUILD_CONTRACT): the request-scoped get_db commits
on clean exit; the LLM auto-executor commits its own connection.
"""

from ..db import repository
from ..market.base import MarketSource


class WatchlistError(Exception):
    """A watchlist change failed validation. Message is user-safe."""


def add_ticker(db, source: MarketSource, ticker: str, user_id: str = "default") -> None:
    """Add a ticker after validating it against the source universe.

    Rejects unknown symbols with WatchlistError (PLAN §13.11) so we never store a
    watchlist entry the active source can't price. Add is UNIQUE-safe at the
    repository layer (re-adding an existing ticker is a no-op).
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise WatchlistError("Ticker must not be empty")
    if not source.knows(ticker):
        raise WatchlistError(f"Unknown ticker '{ticker}' — not available from the data source")
    repository.add_watchlist(db, ticker, user_id)


def remove_ticker(db, ticker: str, user_id: str = "default") -> None:
    """Remove a ticker from the watchlist. No-op if it isn't present."""
    ticker = ticker.strip().upper()
    repository.remove_watchlist(db, ticker, user_id)
