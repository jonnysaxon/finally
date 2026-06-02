# Market Data Backend — Detailed Design

**Status:** Design / implementation guide.
**Scope:** Everything under `backend/app/market/` — the unified data-source
interface, the in-memory price cache, the GBM simulator, the Massive (Polygon.io)
live client, the source factory, and the SSE streaming endpoint. Also covers the
FastAPI wiring, watchlist-add validation, configuration, and the test plan.

This document is the single, authoritative implementation reference for the market
data subsystem. It synthesizes and supersedes the partial snippets in
`MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, and `MASSIVE_API.md`, filling in the
pieces those docs only sketch (the SSE change-detection endpoint, the cache version
counter, app wiring, and symbol validation). Where this document and the earlier
ones differ on a name, **this document wins**.

---

## 1. Goals & Constraints

From PLAN §3 and §6:

- **One interface, two implementations.** A simulator (default, zero deps) and a
  Massive REST poller (when `MASSIVE_API_KEY` is set). Downstream code never knows
  which is running.
- **The cache is the single source of truth.** Exactly one background producer
  writes the latest price per ticker into an in-memory cache; SSE readers only ever
  read the cache (PLAN §13.1).
- **Push only on actual change** (PLAN §13.3) plus a periodic keepalive comment, so
  the flash animation stays meaningful and traffic stays low. Same code path for
  both sources — the simulator changes every tick, Massive changes ~every 15s.
- **Session-scoped state.** `open_price` (the change-% anchor, PLAN §13.2), prev
  price, and any session buffers reset on container restart (PLAN §13.4). The cache
  is in-memory by design.
- **No shorting, market orders only** — out of scope here; this subsystem only
  produces prices. Trade math lives in the portfolio module and reads
  `cache.get_price()`.
- **Async, single event loop, no blocking.** The simulator is an asyncio task; the
  Massive poller uses `httpx.AsyncClient`, never the synchronous official client on
  the hot path.

---

## 2. Architecture

```
┌────────────────┐    writes (set_price)    ┌──────────────┐    reads (snapshot)   ┌─────────────┐
│  MarketSource  │ ───────────────────────▶ │  PriceCache  │ ◀──────────────────── │ SSE endpoint │
│ (sim │ massive)│   ~500 ms  │  ~15 s       │ (in-memory + │   on push tick        │ /api/stream/ │
│   .run()       │            │              │  version ctr)│   (diff by version)   │   prices     │
└────────────────┘            │              └──────────────┘                       └─────────────┘
        ▲                     │                     │  ▲                                    │
        │ universe()          │                     │  │ get_price()                        ▼
        │ validates           │                     │  └────────────── portfolio / chat   EventSource
        │ watchlist adds      │                     └──────────────────── valuation        (browser)
        └─────────────────────┘
```

Key properties:

- **Single writer, many readers.** Because the writer (the source `run()` loop) and
  the readers (SSE generators, REST handlers) all live on the same asyncio event
  loop, no preemption can interleave a half-written quote. **No lock is needed**
  while the producer is an asyncio task. If a future version moves polling onto a
  thread, add a `threading.Lock` around cache mutations (noted in §4).
- **Change detection by version counter.** The cache bumps a monotonic integer every
  time a quote actually changes. SSE readers remember the last version they sent and
  emit only quotes newer than that — this is how "push only on change" (PLAN §13.3)
  is implemented without the source knowing anything about SSE.

### Module layout

```
backend/
  pyproject.toml                 # uv project; deps: fastapi, uvicorn, httpx, (massive)
  app/
    __init__.py
    main.py                      # FastAPI app, lifespan wiring (§9)
    market/
      __init__.py                # public exports: PriceCache, create_source, Quote, ...
      types.py                   # Quote (frozen dataclass)
      cache.py                   # PriceCache + version counter
      base.py                    # MarketSource ABC
      sim_config.py              # TickerSpec + SEED universe
      simulator.py               # SimulatorSource (GBM)
      massive.py                 # MassiveSource (httpx poller) + symbol validation
      factory.py                 # create_source() — env-driven selection
      stream.py                  # create_stream_router() — SSE endpoint
  tests/
    market/
      test_types.py
      test_cache.py
      test_simulator.py
      test_simulator_source.py
      test_massive.py
      test_factory.py
      test_stream.py
```

> Naming note: this layout uses `backend/app/market/` (a proper FastAPI `app`
> package) with `types.py`/`base.py`/`Quote`. Earlier drafts referenced
> `backend/market/` and `PriceUpdate`; the names below are canonical.

---

## 3. Data Model — `types.py`

A single immutable value type flows through the whole system. Computed fields are
properties so they can never drift out of sync with the raw prices.

```python
# backend/app/market/types.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Quote:
    """The latest known state of one ticker. The unit pushed over SSE.

    Immutable: the cache replaces the whole Quote on every update rather than
    mutating fields, so a reader always sees a consistent snapshot.
    """

    ticker: str
    price: float          # latest trade price
    prev_price: float     # price at the previous tick (drives flash direction)
    open_price: float     # session-open baseline, set once on first tick (PLAN §13.2)
    timestamp: float      # epoch seconds

    @property
    def change(self) -> float:
        return self.price - self.open_price

    @property
    def change_pct(self) -> float:
        # Guard against a zero open_price (never expected, but cheap insurance).
        return (self.price - self.open_price) / self.open_price if self.open_price else 0.0

    @property
    def direction(self) -> str:
        """'up' | 'down' | 'flat' — drives the green/red flash animation."""
        if self.price > self.prev_price:
            return "up"
        if self.price < self.prev_price:
            return "down"
        return "flat"

    def to_event(self) -> dict:
        """JSON-serializable payload for an SSE `price` event."""
        return {
            "ticker": self.ticker,
            "price": round(self.price, 4),
            "prev_price": round(self.prev_price, 4),
            "open_price": round(self.open_price, 4),
            "change": round(self.change, 4),
            "change_pct": round(self.change_pct, 6),
            "direction": self.direction,
            "timestamp": self.timestamp,
        }
```

Why `open_price` lives on the Quote: PLAN §13.2 anchors "Change %" to a per-ticker
**session-open captured at process start**, not a calendar day. The cache sets it
once on the first sighting of a ticker and never mutates it until restart. The
frontend relabels this "Change" (not "Daily change"), per PLAN §13.2.

---

## 4. The Price Cache — `cache.py`

The single source of truth. One producer writes; SSE and REST read. Adds a
**monotonic version counter** so SSE can emit only changed quotes (PLAN §13.3)
without coupling the source to the stream.

```python
# backend/app/market/cache.py
import time
from .types import Quote


class PriceCache:
    """In-memory latest-price store. Written by exactly one source, read by SSE
    and REST handlers.

    Resets on process restart by design (PLAN §13.4): sparklines, the change-%
    anchor, and session buffers are all session-scoped.

    Concurrency: safe for a single asyncio writer + async readers on one event
    loop (no preemption between awaits). If polling ever moves to a thread, wrap
    the mutating section of set_price() in a threading.Lock — readers would then
    take it too.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._version: int = 0          # bumps on every real change
        self._ticker_version: dict[str, int] = {}  # per-ticker last-change version

    # ---- writes (producer only) -------------------------------------------------

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
            # No price movement: refresh timestamp in place, do NOT bump version.
            # (A new Quote with the same price would otherwise re-trigger SSE.)
            refreshed = Quote(ticker, price, prior.prev_price, prior.open_price, ts)
            self._quotes[ticker] = refreshed
            return refreshed

        quote = Quote(ticker, price, prior.price, prior.open_price, ts)
        self._quotes[ticker] = quote
        self._version += 1
        self._ticker_version[ticker] = self._version
        return quote

    # ---- reads (any consumer) ---------------------------------------------------

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
```

Design notes:

- **Why a per-ticker version, not just a global one:** with a global-only counter,
  a reader behind by N versions would have to re-scan every ticker. The per-ticker
  map lets `changed_since` return exactly the moved tickers in O(universe).
- **Same-price refresh:** the Massive poller may return an identical price between
  trades; we refresh the timestamp but do **not** bump the version, so SSE stays
  quiet and the flash animation only fires on genuine moves.
- **First sighting sets `prev_price == price == open_price`** → `direction == "flat"`,
  `change == 0`. The very first event for a ticker doesn't flash, which is correct.

---

## 5. The Abstract Source — `base.py`

```python
# backend/app/market/base.py
from abc import ABC, abstractmethod
from .cache import PriceCache


class MarketSource(ABC):
    """A background producer that writes latest prices into the cache.

    Implementations: SimulatorSource (default) and MassiveSource (live).
    Nothing else in the app imports a concrete source — consumers depend on
    MarketSource and PriceCache only.
    """

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache

    @abstractmethod
    async def run(self) -> None:
        """Long-running loop: compute/fetch prices, call cache.set_price().
        Runs as an asyncio background task for the app's lifetime. Must return
        promptly (or be cancellable) when the task is cancelled at shutdown."""

    @property
    @abstractmethod
    def universe(self) -> set[str]:
        """Symbols this source can price. Used to validate watchlist adds
        (PLAN §13.11 — reject unknown tickers with a 400)."""

    def knows(self, ticker: str) -> bool:
        return ticker.upper() in self.universe

    async def validate_symbol(self, ticker: str) -> bool:
        """Confirm a symbol can be priced before adding it to the watchlist.

        Default: check the static universe. The Massive source overrides this to
        do a live single-ticker snapshot lookup for symbols it hasn't seen yet
        (PLAN §13.11)."""
        return self.knows(ticker)
```

`validate_symbol` is `async` so the Massive override can make a network call; the
simulator's synchronous check is trivially wrapped.

---

## 6. The Simulator — `sim_config.py` + `simulator.py`

The default source. Generates realistic, continuously moving prices for the seeded
universe with no external dependencies (pure stdlib `random`/`math`, no numpy), so
FinAlly runs out of the box.

### 6.1 Per-ticker config

```python
# backend/app/market/sim_config.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSpec:
    ticker: str
    seed_price: float
    sigma: float          # annualized volatility
    sector: str           # for correlation grouping


# The ten defaults match the watchlist seed in PLAN §7.
SEED: list[TickerSpec] = [
    TickerSpec("AAPL", 190.0, 0.28, "tech"),
    TickerSpec("GOOGL", 175.0, 0.30, "tech"),
    TickerSpec("MSFT", 420.0, 0.26, "tech"),
    TickerSpec("AMZN", 185.0, 0.34, "tech"),
    TickerSpec("TSLA", 250.0, 0.55, "tech"),
    TickerSpec("NVDA", 120.0, 0.50, "tech"),
    TickerSpec("META", 500.0, 0.36, "tech"),
    TickerSpec("JPM", 200.0, 0.24, "finance"),
    TickerSpec("V", 280.0, 0.22, "finance"),
    TickerSpec("NFLX", 650.0, 0.40, "tech"),
]
```

To support more symbols, extend this list — the simulator's `universe` is exactly
the set of seeded tickers.

### 6.2 The model: Geometric Brownian Motion with correlated shocks

Each tick advances every ticker by one GBM step (keeps prices positive, log-normal
walk like real equities):

```
S(t+dt) = S(t) * exp( (mu - 0.5*sigma^2) * dt + sigma * sqrt(dt) * Z )
```

Correlation is built from a **shared market factor + a sector factor + idiosyncratic
noise**, with weights whose squares sum to 1 (preserving unit variance):

```
Z_i = w_m * Z_market + w_s * Z_sector[sector_i] + w_i * Z_idio_i
w_m = 0.5, w_s = 0.4, w_i = sqrt(1 - 0.25 - 0.16) ≈ 0.768
```

`Z_market` is drawn once per tick, `Z_sector` once per sector per tick, `Z_idio`
per ticker. Result: the whole market drifts together, tech names cluster, each stock
still wiggles on its own. This factor model is equivalent to a Cholesky-correlated
draw but far cheaper and dependency-free.

### 6.3 Implementation

```python
# backend/app/market/simulator.py
import asyncio
import math
import random
import time

from .base import MarketSource
from .cache import PriceCache
from .sim_config import SEED, TickerSpec

TICK_SECONDS = 0.5
TRADING_YEAR_SECONDS = 6.5 * 60 * 60 * 252   # ~6.5h/day * 252 trading days
DT = TICK_SECONDS / TRADING_YEAR_SECONDS
MU = 0.05                     # gentle annualized upward drift
EVENT_PROB = 0.005            # per-ticker chance of a dramatic move per tick

# Correlation weights (squares sum to 1 → preserves unit variance).
W_MARKET, W_SECTOR = 0.5, 0.4
W_IDIO = math.sqrt(1 - W_MARKET**2 - W_SECTOR**2)


class SimulatorSource(MarketSource):
    """In-process GBM price generator. No external dependencies."""

    def __init__(
        self,
        cache: PriceCache,
        specs: list[TickerSpec] = SEED,
        seed: int | None = None,
        event_prob: float = EVENT_PROB,
    ) -> None:
        super().__init__(cache)
        self._specs = {s.ticker: s for s in specs}
        self._price = {s.ticker: s.seed_price for s in specs}
        self._rng = random.Random(seed)
        self._event_prob = event_prob

    @property
    def universe(self) -> set[str]:
        return set(self._specs)

    async def run(self) -> None:
        # Prime the cache so the first SSE push has data immediately.
        now = time.time()
        for ticker, price in self._price.items():
            self.cache.set_price(ticker, round(price, 2), now)
        try:
            while True:
                self._step()
                await asyncio.sleep(TICK_SECONDS)
        except asyncio.CancelledError:
            raise  # cooperative shutdown

    def _step(self) -> None:
        z_market = self._rng.gauss(0, 1)
        z_sector: dict[str, float] = {}
        now = time.time()
        for ticker, spec in self._specs.items():
            zs = z_sector.setdefault(spec.sector, self._rng.gauss(0, 1))
            z = W_MARKET * z_market + W_SECTOR * zs + W_IDIO * self._rng.gauss(0, 1)
            price = self._gbm_step(self._price[ticker], spec.sigma, z)
            price = self._maybe_event(price)
            self._price[ticker] = price
            self.cache.set_price(ticker, round(price, 2), now)

    def _gbm_step(self, price: float, sigma: float, z: float) -> float:
        drift = (MU - 0.5 * sigma**2) * DT
        diffusion = sigma * math.sqrt(DT) * z
        return price * math.exp(drift + diffusion)

    def _maybe_event(self, price: float) -> float:
        """Occasional ±2–5% shock on top of the GBM step (PLAN/SIM §5)."""
        if self._rng.random() < self._event_prob:
            shock = self._rng.uniform(0.02, 0.05) * self._rng.choice((-1, 1))
            return price * (1 + shock)
        return price
```

Notes:

- The simulator keeps its **own** running price (`self._price`) and feeds the cache
  the rounded value; it never reads back from the cache. The cache derives
  `prev_price`/`open_price`/`change`/`direction` purely from the stream of
  `set_price` calls — exactly like the Massive source.
- `event_prob` is injectable so unit tests can set it to `0` to isolate the GBM path.
- With a 500ms tick and tiny `DT`, ordinary per-tick moves are fractions of a percent
  — the gentle flicker a terminal shows, punctuated by the occasional event.

---

## 7. The Massive Live Source — `massive.py`

Used when `MASSIVE_API_KEY` is set. Polls the **Full Market Snapshot** endpoint for
the union of watched tickers on an interval (free tier: one request every ~15s,
which returns every requested ticker in a single call). Uses `httpx.AsyncClient`
directly so it never blocks the event loop.

```python
# backend/app/market/massive.py
import asyncio
import time
import httpx

from .base import MarketSource
from .cache import PriceCache

BASE_URL = "https://api.polygon.io"   # Massive == rebranded Polygon; host unchanged
SNAPSHOT_URL = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
TICKER_SNAPSHOT_URL = SNAPSHOT_URL + "/{ticker}"


class MassiveSource(MarketSource):
    """Polls the Massive Full Market Snapshot for watched tickers and writes the
    cache. One request per interval covers the entire watchlist."""

    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        watched: "callable",        # () -> set[str], current watchlist union
        interval: float = 15.0,     # free tier: 5 req/min → one every ~15s
    ) -> None:
        super().__init__(cache)
        self._api_key = api_key
        self._watched = watched
        self._interval = interval
        self._universe: set[str] = set()   # learned from responses + validations

    @property
    def universe(self) -> set[str]:
        return set(self._universe)

    # ---- polling loop -----------------------------------------------------------

    async def run(self) -> None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=10.0) as client:
            try:
                while True:
                    await self._poll_once(client)
                    await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise

    async def _poll_once(self, client: httpx.AsyncClient) -> None:
        tickers = sorted(self._watched())
        if not tickers:
            return
        try:
            resp = await client.get(SNAPSHOT_URL, params={"tickers": ",".join(tickers)})
            resp.raise_for_status()
        except httpx.HTTPError:
            # Rate-limited (429) or transient error: keep last good cache value,
            # retry next interval. (PLAN MASSIVE §5.5)
            return
        for row in resp.json().get("tickers", []):
            price = _extract_price(row)
            if price is not None:
                self.cache.set_price(row["ticker"], price, _extract_ts(row))
                self._universe.add(row["ticker"].upper())

    # ---- watchlist-add validation (PLAN §13.11) --------------------------------

    async def validate_symbol(self, ticker: str) -> bool:
        """Accept a symbol if Massive returns a snapshot for it. Caches the result
        in the universe so subsequent checks are free and the next poll includes it."""
        ticker = ticker.upper()
        if ticker in self._universe:
            return True
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = TICKER_SNAPSHOT_URL.format(ticker=ticker)
        try:
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError:
            return False
        row = resp.json().get("ticker") or {}
        if _extract_price(row) is not None:
            self._universe.add(ticker)
            return True
        return False


def _extract_price(row: dict) -> float | None:
    """Prefer the last trade; fall back to today's close (pre-market)."""
    last = (row.get("lastTrade") or {}).get("p")
    if last:
        return float(last)
    close = (row.get("day") or {}).get("c")
    return float(close) if close else None


def _extract_ts(row: dict) -> float:
    """Last-trade timestamp is in nanoseconds; convert to epoch seconds."""
    ns = (row.get("lastTrade") or {}).get("t")
    return ns / 1e9 if ns else time.time()
```

Notes:

- **Why `httpx` and not the official `massive` client on the hot path:** the official
  client is synchronous (`urllib3`) and would block the event loop. We hit the REST
  endpoint directly. The official client is fine for one-off, offline tasks via
  `asyncio.to_thread` (e.g. an optional EOD baseline backfill — §7.1).
- **`universe` is learned, not seeded.** The live source discovers valid symbols as
  the snapshot returns them; `validate_symbol` does a single-ticker lookup for a
  symbol not yet seen and adds it to the universe on success.
- **"Emit only on change" is the cache/SSE layer's job**, not the poller's: the
  poller always writes the latest; the cache's version counter suppresses no-op
  re-emits (§4). A static price between trades therefore produces no SSE event.
- **Missing keys are always guarded** — a ticker can be absent or fieldless before
  market open (PLAN MASSIVE §3.1).

### 7.1 Optional: real session-open baseline (stretch)

By default `open_price` is "price at process start" (PLAN §13.2). If a real
prior-close baseline is ever wanted, fetch it once at startup via the Previous Close
endpoint and seed the cache before the poller's first write:

```python
# one-off at startup, off the hot path
async def seed_prev_close(cache: PriceCache, api_key: str, tickers: list[str]) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=10.0) as client:
        for t in tickers:
            try:
                r = await client.get(f"/v2/aggs/ticker/{t}/prev", params={"adjusted": "true"})
                r.raise_for_status()
                close = r.json()["results"][0]["c"]
            except (httpx.HTTPError, KeyError, IndexError):
                continue
            cache.set_price(t, float(close))   # first write → sets open_price
```

This is explicitly **not** part of v1 (PLAN §13.2 keeps the session-open anchor);
documented here as the upgrade path.

---

## 8. The Factory — `factory.py`

The one place the implementation is chosen, driven entirely by the environment.

```python
# backend/app/market/factory.py
import os
from .cache import PriceCache
from .base import MarketSource
from .simulator import SimulatorSource
from .massive import MassiveSource

# A callable returning the current watchlist union, e.g. from SQLite.
WatchedFn = "callable"   # () -> set[str]


def create_source(cache: PriceCache, watched: WatchedFn) -> MarketSource:
    """Massive if MASSIVE_API_KEY is set and non-empty, else the simulator.

    `watched` is a callback returning the current watchlist tickers. The simulator
    ignores it (its universe is fixed); the Massive poller uses it to size each
    snapshot request.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        interval = float(os.environ.get("MASSIVE_POLL_SECONDS", "15"))
        return MassiveSource(cache, api_key, watched, interval=interval)
    return SimulatorSource(cache)
```

`MASSIVE_POLL_SECONDS` is an optional override (default 15) so paid tiers can poll
faster by changing one env var, no code change (PLAN MASSIVE §2).

---

## 9. SSE Streaming Endpoint — `stream.py`

The browser consumer. Long-lived `text/event-stream` connection; the native
`EventSource` API handles reconnection. The endpoint reads the cache each push tick
and emits **only changed quotes** (via the version counter), with a periodic
keepalive comment to hold the connection open through idle periods.

```python
# backend/app/market/stream.py
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

PUSH_SECONDS = 0.5        # how often we check the cache for changes
KEEPALIVE_SECONDS = 15.0  # comment ping to keep proxies/browser from timing out

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",   # disable proxy buffering so events flush immediately
}


def create_stream_router(cache: PriceCache) -> APIRouter:
    """Factory so the cache is injected (no module-level globals)."""
    router = APIRouter()

    async def _events(request: Request) -> AsyncGenerator[str, None]:
        # Start from 0 so a freshly connected client immediately receives the full
        # current snapshot (every ticker counts as "changed since 0").
        last_version = 0
        last_keepalive = asyncio.get_event_loop().time()

        # Tell EventSource to retry after 3s if the connection drops.
        yield "retry: 3000\n\n"

        while True:
            if await request.is_disconnected():
                break

            changed, last_version = cache.changed_since(last_version)
            for quote in changed:
                payload = json.dumps(quote.to_event())
                yield f"event: price\ndata: {payload}\n\n"

            now = asyncio.get_event_loop().time()
            if now - last_keepalive >= KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"   # SSE comment — ignored by the client
                last_keepalive = now

            await asyncio.sleep(PUSH_SECONDS)

    @router.get("/api/stream/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _events(request),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return router
```

SSE wire format and behavior:

- **Event shape:** each price update is `event: price` with a JSON `data:` line
  (`Quote.to_event()`), terminated by a blank line. The client listens with
  `es.addEventListener("price", ...)`.
- **Initial snapshot:** a new client starts at `last_version = 0`, so its first tick
  delivers every known ticker — the watchlist renders immediately, then updates
  incrementally.
- **Change-only emission (PLAN §13.3):** `changed_since` returns only tickers whose
  price actually moved, so the simulator streams continuously while Massive emits
  roughly every 15s — same code path.
- **Keepalive:** a `:` comment every 15s keeps intermediaries from closing an idle
  connection without triggering any client-side event.
- **No buffering:** headers set `Cache-Control: no-cache` and `X-Accel-Buffering: no`;
  run a single Uvicorn process with no buffering proxy so events flush immediately
  (PLAN §13 CORS/origin clarification).
- **Disconnect:** `request.is_disconnected()` ends the generator promptly when the
  browser navigates away, so we don't leak tasks.

Example client (frontend reference):

```js
const es = new EventSource("/api/stream/prices");
es.addEventListener("price", (e) => {
  const q = JSON.parse(e.data);
  // q.ticker, q.price, q.change_pct, q.direction ("up"|"down"|"flat"), q.timestamp
  applyPriceUpdate(q);   // flash green/red, push into sparkline buffer
});
// EventSource auto-reconnects using the `retry:` hint on drop.
```

---

## 10. FastAPI Wiring — `main.py`

The source runs as a single background task for the app's lifetime, started in the
lifespan handler. The cache and source live on `app.state` so REST handlers (e.g.
watchlist add) can reach them.

```python
# backend/app/main.py
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .market.cache import PriceCache
from .market.factory import create_source
from .market.stream import create_stream_router
# from .db import current_watchlist_tickers   # () -> set[str], reads SQLite


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    # `watched` is the watchlist union; simulator ignores it, Massive uses it.
    source = create_source(cache, watched=current_watchlist_tickers)
    app.state.cache = cache
    app.state.source = source

    task = asyncio.create_task(source.run(), name="market-source")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    # The SSE router needs the cache; it's created per-app after lifespan sets it.
    # Because the cache is created inside lifespan, mount the router lazily or
    # create the cache here and pass it into lifespan. Simplest: create the cache
    # at module construction time (below).
    return app
```

> Wiring caveat: the SSE router needs the `PriceCache` instance, but lifespan runs
> after routers are registered. Two clean options:
>
> 1. **Construct the cache in `create_app()`** and pass it to both `lifespan`
>    (closure) and `create_stream_router(cache)`. Preferred — one cache, explicit.
> 2. Have the SSE handler read `request.app.state.cache` at request time instead of
>    capturing it in the factory.

The preferred form:

```python
def create_app() -> FastAPI:
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        source = create_source(cache, watched=current_watchlist_tickers)
        app.state.cache = cache
        app.state.source = source
        task = asyncio.create_task(source.run(), name="market-source")
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_stream_router(cache))
    return app


app = create_app()
```

---

## 11. Watchlist-Add Validation (PLAN §13.11)

The watchlist `POST` handler (owned by the portfolio/watchlist module, shown here
for the integration contract) rejects symbols the active source can't price:

```python
# in the watchlist router
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

@router.post("/api/watchlist")
async def add_to_watchlist(body: dict, request: Request):
    ticker = body["ticker"].strip().upper()
    source = request.app.state.source
    if not await source.validate_symbol(ticker):
        raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")
    # ... insert into SQLite watchlist (UNIQUE on user_id, ticker) ...
    return {"ticker": ticker}
```

- **Simulator:** `validate_symbol` checks the seeded universe → only the 10 seeded
  symbols (or any added to `SEED`) are accepted.
- **Massive:** `validate_symbol` accepts any symbol Massive returns a snapshot for,
  caching it into the universe so the next poll includes it.
- In the chat flow, the same 400 is surfaced to the LLM so it can tell the user
  (PLAN §13.11).

---

## 12. Configuration / Environment Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `MASSIVE_API_KEY` | *(empty)* | Non-empty → use `MassiveSource`; empty → `SimulatorSource`. |
| `MASSIVE_POLL_SECONDS` | `15` | Poll interval for the live source (paid tiers can lower it). |

Constants that are code-level (not env) but documented for tuning:

| Constant | Module | Default | Meaning |
|----------|--------|---------|---------|
| `TICK_SECONDS` | simulator | `0.5` | Simulator step cadence. |
| `MU` | simulator | `0.05` | Annualized drift. |
| `EVENT_PROB` | simulator | `0.005` | Per-tick per-ticker dramatic-move chance. |
| `PUSH_SECONDS` | stream | `0.5` | SSE change-check cadence. |
| `KEEPALIVE_SECONDS` | stream | `15` | SSE keepalive comment interval. |

`.env.example` already documents `MASSIVE_API_KEY` (PLAN §5); add
`MASSIVE_POLL_SECONDS=` as an optional commented line.

---

## 13. Testing Strategy (PLAN §12)

All tests are pure-Python and fast; no network, no real Massive calls.

### 13.1 `types.py`
- `change`, `change_pct`, `direction` for up/down/flat and zero-open guard.
- `to_event()` keys and rounding.

### 13.2 `cache.py`
- First `set_price` sets `open_price == prev_price == price`, `direction == "flat"`,
  version bumps to 1.
- Second `set_price` with a different price → `prev_price` is the prior price,
  `open_price` unchanged, version bumps.
- Same-price write refreshes timestamp but does **not** bump version.
- `changed_since(v)` returns exactly the moved tickers and the new version; with
  `v == current` returns `([], current)`.

```python
def test_changed_since_returns_only_moved():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    c.set_price("MSFT", 420.0)
    base = c.version
    c.set_price("AAPL", 191.0)            # only AAPL moves
    changed, ver = c.changed_since(base)
    assert {q.ticker for q in changed} == {"AAPL"}
    assert ver == c.version
```

### 13.3 `simulator.py` / `simulator_source.py`
- **Determinism:** same `seed` → identical price sequence.
- **Positivity:** GBM never yields `price <= 0` over many steps.
- **Drift-only:** with every `sigma == 0` and `event_prob == 0`, prices follow pure
  drift `S * exp(MU * DT)` per step (assert close).
- **Universe:** equals the seeded symbols; `knows()`/`validate_symbol()` true for
  seeded, false otherwise.
- **`run()` primes the cache:** after starting the task and one `await asyncio.sleep`,
  every seeded ticker has a quote. Cancel the task cleanly.

```python
import asyncio, pytest
from app.market.cache import PriceCache
from app.market.simulator import SimulatorSource

@pytest.mark.asyncio
async def test_run_primes_and_ticks():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42, event_prob=0)
    task = asyncio.create_task(src.run())
    await asyncio.sleep(0.0)               # let it prime
    assert cache.get("AAPL") is not None
    v0 = cache.version
    await asyncio.sleep(0.6)               # at least one tick
    assert cache.version > v0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
```

### 13.4 `massive.py`
- `_extract_price` prefers `lastTrade.p`, falls back to `day.c`, returns `None` when
  both absent.
- `_extract_ts` converts nanoseconds → seconds; falls back to `time.time()`.
- `_poll_once` writes the cache and grows the universe (mock `httpx` via
  `respx` or a `MockTransport`); returns silently on `HTTPError` (no raise, last
  value kept).
- `validate_symbol` returns True on a mocked snapshot with a price, False on
  `HTTPError` or empty body; cached symbols short-circuit without a request.

```python
import httpx, pytest
from app.market.cache import PriceCache
from app.market.massive import MassiveSource

@pytest.mark.asyncio
async def test_poll_once_writes_cache():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="k", watched=lambda: {"AAPL"})
    body = {"tickers": [{"ticker": "AAPL",
                         "lastTrade": {"p": 191.23, "t": 1_700_000_000_000_000_000}}]}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        await src._poll_once(client)
    assert cache.get_price("AAPL") == pytest.approx(191.23)
    assert "AAPL" in src.universe
```

### 13.5 `factory.py`
- `MASSIVE_API_KEY` empty/whitespace → `SimulatorSource`.
- `MASSIVE_API_KEY` set → `MassiveSource`, honoring `MASSIVE_POLL_SECONDS`.

### 13.6 `stream.py`
- The `_events` generator yields a `retry:` line, then `event: price` frames for the
  initial snapshot, and a `: keepalive` comment after the interval. Drive it with a
  fake `Request` whose `is_disconnected()` flips to True after N iterations, or test
  via FastAPI `TestClient` streaming and assert the first frames.
- Conformance: the same abstract-source test battery runs against both
  `SimulatorSource` and a mocked `MassiveSource` (both satisfy `MarketSource`).

### 13.7 E2E (in `test/`, PLAN §12)
- Fresh start: default watchlist streams prices within a second or two.
- SSE resilience: kill and restore the connection, assert `EventSource` reconnects
  and resumes (the change-only stream re-sends the full snapshot on reconnect because
  the new generator starts at `last_version = 0`).

---

## 14. Public API Surface — `__init__.py`

```python
# backend/app/market/__init__.py
from .types import Quote
from .cache import PriceCache
from .base import MarketSource
from .factory import create_source
from .stream import create_stream_router

__all__ = [
    "Quote",
    "PriceCache",
    "MarketSource",
    "create_source",
    "create_stream_router",
]
```

Downstream usage (portfolio valuation, chat context):

```python
from app.market import PriceCache, create_source

cache = PriceCache()
source = create_source(cache, watched=current_watchlist_tickers)
# started as a background task in the FastAPI lifespan (§10)

price = cache.get_price("AAPL")     # float | None — latest, for P&L
quote = cache.get("AAPL")           # Quote | None — full state incl. change_pct
snapshot = cache.all()              # dict[str, Quote] — chat/portfolio context
```

---

## 15. Summary of Decisions (traceability to PLAN)

| Decision | Source | Where implemented |
|----------|--------|-------------------|
| Cache is single source of truth | PLAN §6, §13.1 | `cache.py`; SSE reads cache only |
| Session-open change% anchor | PLAN §13.2 | `Quote.open_price`, set once in `set_price` |
| Push only on change + keepalive | PLAN §13.3 | version counter + `changed_since` + `_events` |
| Cache resets on restart | PLAN §13.4 | in-memory `PriceCache`, no persistence |
| Reject unknown tickers (400) | PLAN §13.11 | `MarketSource.validate_symbol` + watchlist route |
| Env-driven source selection | PLAN §5, §6 | `factory.create_source` |
| Simulator: GBM + correlation + events | PLAN §6, SIM | `simulator.py`, `sim_config.py` |
| Massive: snapshot poll, free-tier 15s | PLAN §6, MASSIVE | `massive.py`, `MASSIVE_POLL_SECONDS` |
| No CORS, no SSE buffering | PLAN §13 clarifications | `SSE_HEADERS`, single Uvicorn process |
```
