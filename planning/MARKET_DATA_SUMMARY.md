# Market Data Backend — Summary

**Status:** Complete, tested, reviewed. All review follow-ups resolved (see `MARKET_DATA_REVIEW.md`).

## What Was Built

A complete market data subsystem in `backend/app/market/` providing live price
simulation and real market data behind a single unified interface. The cache is
the single source of truth (PLAN §6); SSE readers only ever read the cache.

### Architecture

```
MarketSource (ABC)
├── SimulatorSource  →  GBM simulator (default, no API key needed)
└── MassiveSource    →  Polygon.io / Massive REST poller (when MASSIVE_API_KEY set)
        │ writes
        ▼
   PriceCache (in-memory, single-writer)
        │ reads
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation (downstream)
        └──→ Chat context (downstream)
```

### Modules (`backend/app/market/`)

| File | Purpose |
|------|---------|
| `types.py` | `Quote` — immutable frozen dataclass (ticker, price, prev_price, open_price, timestamp) with `change`, `change_pct`, `direction` properties and `to_event()` for SSE payloads |
| `cache.py` | `PriceCache` — in-memory latest-price store with a global + per-ticker version counter for "emit only on change" SSE detection; captures `open_price` once per ticker |
| `base.py` | `MarketSource` — abstract base defining `run()`, `universe`, `knows()`, `validate_symbol()` |
| `sim_config.py` | `TickerSpec` and the 10 seeded tickers with per-ticker seed price, annualized volatility, and sector |
| `simulator.py` | `SimulatorSource` — Geometric Brownian Motion generator with a market/sector/idiosyncratic factor model and occasional shock events |
| `massive.py` | `MassiveSource` — async REST polling client (httpx) for the Massive/Polygon full-market snapshot, plus `validate_symbol` via single-ticker lookup |
| `factory.py` | `create_source()` — selects simulator or Massive from `MASSIVE_API_KEY`; honours `MASSIVE_POLL_SECONDS` |
| `stream.py` | `price_event_stream()` + `create_stream_router()` — FastAPI SSE endpoint using version-based change detection, retry hint, and keepalive comments |

`backend/app/main.py` wires a `PriceCache` and `create_source()` into the FastAPI
lifespan as a background task, and exposes `/api/health`. (The watchlist callback
is a placeholder until the DB module lands.)

### Key Design Decisions

- **Strategy pattern** — both sources implement the same ABC; downstream code is source-agnostic.
- **PriceCache as single source of truth** — exactly one writer, many readers; no direct coupling between producer and consumers.
- **Correlated GBM via a factor model** — each tick draws a shared market shock, a per-sector shock, and a per-ticker idiosyncratic shock, combined as `z = 0.5·z_market + 0.4·z_sector + 0.768·z_idio`. This preserves unit variance (0.25 + 0.16 + 0.59 = 1.0) and yields same-sector correlation ≈ 0.41 and cross-sector correlation ≈ 0.25. (No correlation matrix / Cholesky decomposition — the factor model is simpler and sufficient.)
- **Random shock events** — small per-tick chance (`EVENT_PROB = 0.005`) of a ±2–5% move for visual drama.
- **Massive via httpx.AsyncClient** — the official `massive`/Polygon client is synchronous and would block the event loop, so the poller calls the REST snapshot endpoint directly. `massive` is **not** a dependency.
- **SSE over WebSockets** — one-way push, simpler, universal browser support.

## Test Suite

**92 tests, all passing** (`cd backend && uv run pytest`). 7 test modules in `backend/tests/market/`.

| Module | Tests |
|--------|-------|
| test_types.py | 13 |
| test_cache.py | 20 |
| test_simulator.py | 13 |
| test_simulator_source.py | 7 |
| test_massive.py | 18 |
| test_factory.py | 8 |
| test_stream.py | 13 |

### Coverage (`uv run pytest --cov=app`)

| Module | Cover |
|--------|-------|
| `app/market/types.py` | 100% |
| `app/market/cache.py` | 100% |
| `app/market/base.py` | 100% |
| `app/market/sim_config.py` | 100% |
| `app/market/simulator.py` | 100% |
| `app/market/factory.py` | 100% |
| `app/market/stream.py` | 97% |
| `app/market/massive.py` | 88% (the live polling loop and HTTP client setup are not exercised in tests) |
| `app/main.py` | 0% (app wiring / lifespan — not unit-tested) |

The `app/market` package is ~96% covered; overall is ~86% (dragged down by the
untested `main.py` wiring).

## Tooling

- **Package manager:** `uv`. Dev dependencies are declared under `[dependency-groups]`.
- **Lint/format:** `ruff` (config in `pyproject.toml`; `uv run ruff check .` is clean).
- **Coverage:** `pytest-cov`.

## Demo

A Rich terminal demo at `backend/market_data_demo.py` (`rich` is a dev dependency):

```bash
cd backend
uv run market_data_demo.py
```

Displays a live-updating dashboard of all 10 tickers with color-coded direction
arrows and change %. Runs 60 seconds or until Ctrl+C.

## Usage for Downstream Code

```python
from app.market import PriceCache, create_source

# Startup (see backend/app/main.py for the FastAPI lifespan wiring)
cache = PriceCache()
source = create_source(cache, watched=current_watchlist_tickers)  # reads MASSIVE_API_KEY
task = asyncio.create_task(source.run())

# Read prices
quote = cache.get("AAPL")          # Quote or None
price = cache.get_price("AAPL")    # float or None
all_quotes = cache.all()           # dict[str, Quote]

# Validate a symbol before a watchlist add (PLAN §13.11)
ok = await source.validate_symbol("TSLA")

# Shutdown
task.cancel()
```
