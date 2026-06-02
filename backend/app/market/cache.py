import time
from .types import Quote


class PriceCache:
    """In-memory latest-price store. Written by exactly one source, read by SSE
    and REST handlers.

    Resets on process restart by design (PLAN §13.4): sparklines, the change-%
    anchor, and session buffers are all session-scoped.

    Concurrency: safe for a single asyncio writer + async readers on one event
    loop (no preemption between awaits). If polling ever moves to a thread, wrap
    the mutating section of set_price() in a threading.Lock.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._version: int = 0
        self._ticker_version: dict[str, int] = {}

    def set_price(self, ticker: str, price: float, timestamp: float | None = None) -> Quote:
        """Record a new price.

        - Captures open_price on the first sighting of a ticker.
        - Derives prev_price from the prior quote.
        - Bumps the version counter ONLY if the price actually changed, so SSE
          "emit only on change" works for both the always-moving simulator and the
          ~15s Massive poller.
        """
        ticker = ticker.upper()
        ts = timestamp if timestamp is not None else time.time()
        prior = self._quotes.get(ticker)

        if prior is None:
            quote = Quote(ticker, price, price, price, ts)
            self._quotes[ticker] = quote
            self._version += 1
            self._ticker_version[ticker] = self._version
            return quote

        if price == prior.price:
            # No price movement: refresh timestamp but do NOT bump version.
            refreshed = Quote(ticker, price, prior.prev_price, prior.open_price, ts)
            self._quotes[ticker] = refreshed
            return refreshed

        quote = Quote(ticker, price, prior.price, prior.open_price, ts)
        self._quotes[ticker] = quote
        self._version += 1
        self._ticker_version[ticker] = self._version
        return quote

    def get(self, ticker: str) -> Quote | None:
        return self._quotes.get(ticker.upper())

    def get_price(self, ticker: str) -> float | None:
        q = self._quotes.get(ticker.upper())
        return q.price if q else None

    def all(self) -> dict[str, Quote]:
        return dict(self._quotes)

    @property
    def version(self) -> int:
        """Current global version. SSE readers remember the last value they sent."""
        return self._version

    def changed_since(self, version: int) -> tuple[list[Quote], int]:
        """Return (quotes changed since `version`, current version).

        Used by the SSE endpoint each push tick: emit only what moved.
        """
        if version >= self._version:
            return [], self._version
        changed = [
            self._quotes[t]
            for t, v in self._ticker_version.items()
            if v > version
        ]
        return changed, self._version
