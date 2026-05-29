# Market Data Interface

The unified Python API FinAlly uses to retrieve stock prices. One interface, two
implementations: the **Massive API client** (when `MASSIVE_API_KEY` is set) and
the built-in **simulator** (otherwise). All downstream code — the SSE stream, the
price cache, the frontend — is agnostic to which source is running.

This is the contract from PLAN §6: a single background task writes the latest
price into a shared in-memory cache, and the **cache is the single source of
truth**. SSE readers only ever read the cache; they never touch a data source.

```
┌──────────────┐     writes      ┌──────────────┐     reads      ┌─────────────┐
│ MarketSource │ ───────────────▶│  PriceCache  │◀────────────── │ SSE readers │
│ (sim | live) │   ~500ms / 15s  │ (in-memory)  │  on push tick  │             │
└──────────────┘                 └──────────────┘                └─────────────┘
        ▲                                                                 │
        │ universe() validates watchlist adds                            ▼
        └───────────────────────────────────────────────  EventSource clients
```

---

## 1. Data Types

A single immutable value type flows through the whole system. Keep it tiny.

```python
# backend/market/types.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Quote:
    """The latest known state of one ticker. The unit pushed over SSE."""

    ticker: str
    price: float          # latest trade price
    prev_price: float     # price at the previous tick (for flash direction)
    open_price: float     # session-open baseline, set on first tick (PLAN §13.2)
    timestamp: float      # epoch seconds

    @property
    def change(self) -> float:
        return self.price - self.open_price

    @property
    def change_pct(self) -> float:
        return (self.price - self.open_price) / self.open_price if self.open_price else 0.0

    @property
    def direction(self) -> str:
        """'up' | 'down' | 'flat' — drives the green/red flash animation."""
        if self.price > self.prev_price:
            return "up"
        if self.price < self.prev_price:
            return "down"
        return "flat"
```

Why `open_price` lives here: PLAN §13.2 anchors "Change %" to a per-ticker
session-open captured at process start, not a calendar day. The cache sets it
once on the first tick and never mutates it (until restart).

---

## 2. The Price Cache (single source of truth)

```python
# backend/market/cache.py
import time
from .types import Quote


class PriceCache:
    """In-memory latest-price store. Written by one source, read by SSE.

    Resets on process restart by design (PLAN §13.4) — sparklines, the change%
    anchor, and session buffers are all session-scoped.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}

    def set_price(self, ticker: str, price: float, timestamp: float | None = None) -> Quote:
        """Record a new price. Captures open_price on first sighting, computes
        prev_price from the prior quote. Returns the new Quote."""
        ticker = ticker.upper()
        ts = timestamp if timestamp is not None else time.time()
        prior = self._quotes.get(ticker)
        prev_price = prior.price if prior else price
        open_price = prior.open_price if prior else price
        quote = Quote(ticker, price, prev_price, open_price, ts)
        self._quotes[ticker] = quote
        return quote

    def get(self, ticker: str) -> Quote | None:
        return self._quotes.get(ticker.upper())

    def all(self) -> dict[str, Quote]:
        return dict(self._quotes)
```

No locking is needed: a single asyncio task writes, and async readers run on the
same event loop (no preemption between awaits). If a future version moves polling
to a thread, wrap writes in a lock then.

---

## 3. The Abstract Source

```python
# backend/market/base.py
from abc import ABC, abstractmethod
from .cache import PriceCache


class MarketSource(ABC):
    """A background producer that writes latest prices into the cache."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache

    @abstractmethod
    async def run(self) -> None:
        """Long-running loop: compute/fetch prices, call cache.set_price().
        Runs as an asyncio background task for the app's lifetime."""

    @property
    @abstractmethod
    def universe(self) -> set[str]:
        """Symbols this source can price. Used to validate watchlist adds
        (PLAN §13.11 — reject unknown tickers with a 400)."""

    def knows(self, ticker: str) -> bool:
        return ticker.upper() in self.universe
```

Both implementations satisfy exactly this. Nothing else in the app imports a
concrete source — they depend on `MarketSource` and `PriceCache` only.

---

## 4. The Two Implementations

### 4.1 Simulator (default)

Full design in **MARKET_SIMULATOR.md**. Interface-relevant points:

- `run()` ticks every ~500ms, advances GBM prices, calls `cache.set_price()` for
  every ticker in its universe.
- `universe` is the seeded symbol set (the 10 defaults plus any others it knows).
- Streams continuously — every tick changes prices.

### 4.2 Massive live source

```python
# backend/market/massive.py
import asyncio
import time
import httpx
from .base import MarketSource
from .cache import PriceCache

SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"


class MassiveSource(MarketSource):
    """Polls the Massive Full Market Snapshot for watched tickers and writes
    the cache. One request per interval covers the entire watchlist."""

    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        watched: callable,          # () -> set[str], current watchlist union
        interval: float = 15.0,     # free tier: 5 req/min
    ) -> None:
        super().__init__(cache)
        self._api_key = api_key
        self._watched = watched
        self._interval = interval
        self._universe: set[str] = set()

    @property
    def universe(self) -> set[str]:
        return self._universe

    async def run(self) -> None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            while True:
                await self._poll_once(client)
                await asyncio.sleep(self._interval)

    async def _poll_once(self, client: httpx.AsyncClient) -> None:
        tickers = sorted(self._watched())
        if not tickers:
            return
        try:
            resp = await client.get(SNAPSHOT_URL, params={"tickers": ",".join(tickers)})
            resp.raise_for_status()
        except httpx.HTTPError:
            return  # keep last good cache value; retry next interval
        for row in resp.json().get("tickers", []):
            price = _extract_price(row)
            if price is not None:
                self.cache.set_price(row["ticker"], price, _extract_ts(row))
                self._universe.add(row["ticker"])


def _extract_price(row: dict) -> float | None:
    """Prefer last trade; fall back to today's close (pre-market)."""
    last = row.get("lastTrade", {}).get("p")
    if last:
        return last
    return row.get("day", {}).get("c") or None


def _extract_ts(row: dict) -> float:
    ns = row.get("lastTrade", {}).get("t")
    return ns / 1e9 if ns else time.time()
```

Notes:
- We use `httpx.AsyncClient` directly rather than the synchronous `massive`
  client so we never block the event loop. (The official client is fine for
  one-off validation calls via `asyncio.to_thread`.)
- `universe` for the live source is **populated from responses** — we learn which
  symbols are valid as the snapshot returns them. For watchlist-add validation of
  a symbol not yet seen, do a single `get_snapshot_ticker` lookup and accept it if
  Massive returns data (PLAN §13.11).
- Emitting "only on change" (PLAN §13.3) is handled at the SSE layer by diffing
  the cache, not here — the cache always holds the latest.

---

## 5. Selection / Factory

One function chooses the implementation from the environment. This is the only
place the choice is made.

```python
# backend/market/factory.py
import os
from .cache import PriceCache
from .base import MarketSource
from .simulator import SimulatorSource
from .massive import MassiveSource


def create_source(cache: PriceCache, watched: callable) -> MarketSource:
    """Massive if MASSIVE_API_KEY is set and non-empty, else the simulator."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveSource(cache, api_key, watched)
    return SimulatorSource(cache)
```

Wiring at app startup (FastAPI lifespan):

```python
# backend/main.py (sketch)
from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app):
    cache = PriceCache()
    source = create_source(cache, watched=current_watchlist_tickers)
    app.state.cache = cache
    app.state.source = source
    task = asyncio.create_task(source.run())
    try:
        yield
    finally:
        task.cancel()
```

`watched` is a callback returning the current watchlist union (queried from
SQLite). The simulator ignores it; the Massive poller uses it to size each
snapshot request.

---

## 6. How Consumers Use It

| Consumer | Touches | How |
|----------|---------|-----|
| SSE `/api/stream/prices` | `PriceCache` only | Read `cache.all()` each push tick; emit changed quotes |
| Watchlist add | `MarketSource.knows()` | Reject unknown symbol with 400 (PLAN §13.11) |
| Portfolio valuation | `PriceCache.get()` | Latest price × quantity for P&L |
| Chat context | `PriceCache` | Inject live prices into the LLM prompt |

The contract is small on purpose: **produce into the cache, read from the cache,
validate against the universe.** Everything else is an implementation detail of a
single source and can change without touching the rest of the app.
