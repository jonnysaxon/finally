# Market Simulator

The default price source when `MASSIVE_API_KEY` is not set. It generates
realistic, continuously moving prices for the seeded ticker universe with no
external dependencies, so FinAlly runs out of the box. It implements the
`MarketSource` interface from MARKET_INTERFACE.md — `run()` writes ticks into the
shared `PriceCache`, and `universe` exposes the seeded symbols.

## 1. Goals

- **Realistic motion** — prices wander like real stocks, not random noise.
- **Drama** — occasional sharp moves so the terminal feels alive.
- **Correlation** — related names (e.g. tech) tend to move together.
- **Deterministic option** — seedable RNG for reproducible tests.
- **Zero dependencies** — pure Python + stdlib `random`/`math`; no numpy needed.

## 2. The Model: Geometric Brownian Motion

Each tick advances every ticker by one GBM step. GBM keeps prices positive and
produces the log-normal walk real equities approximate:

```
S(t+dt) = S(t) * exp( (mu - 0.5*sigma^2) * dt + sigma * sqrt(dt) * Z )
```

- `S` — current price
- `mu` — annualized drift (slight upward bias, e.g. 0.05)
- `sigma` — annualized volatility (per-ticker, e.g. 0.2–0.6)
- `dt` — time step as a fraction of a trading year
- `Z` — standard normal shock (the correlated random draw)

With a 500ms tick and ~6.5h trading day, `dt` is tiny, so per-tick moves are
fractions of a percent — exactly the gentle flicker a terminal shows, punctuated
by the occasional event (§5).

## 3. Per-Ticker Configuration

Seed each ticker with a realistic starting price and its own volatility. Drift is
shared/small; volatility varies so some names are jumpier than others.

```python
# backend/market/sim_config.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSpec:
    ticker: str
    seed_price: float
    sigma: float          # annualized volatility
    sector: str           # for correlation grouping


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

These ten match the default watchlist seed in PLAN §7. The simulator's
`universe` is the set of these symbols (extend the list to support more).

## 4. Correlation

Real sectors move together. Build each ticker's shock `Z` from a shared market
factor plus a sector factor plus idiosyncratic noise:

```
Z_i = w_m * Z_market + w_s * Z_sector[sector_i] + w_i * Z_idiosyncratic_i
```

with weights chosen so `w_m^2 + w_s^2 + w_i^2 = 1` (keeps unit variance), e.g.
`w_m=0.5, w_s=0.4, w_i=0.768...` → in practice pick `0.5 / 0.4 / sqrt(1-0.25-0.16)`.
Draw `Z_market` once per tick, `Z_sector` once per sector per tick, and
`Z_idiosyncratic` per ticker. The result: the whole market drifts together, tech
names cluster, and each stock still has its own wiggle.

## 5. Events (drama)

On each tick, with small probability per ticker (e.g. 0.5%), inject a one-off
shock of ±2–5% on top of the GBM step. This produces the occasional dramatic
candle without breaking the underlying walk.

```python
if random.random() < EVENT_PROB:
    shock = random.uniform(0.02, 0.05) * random.choice((-1, 1))
    price *= (1 + shock)
```

## 6. Implementation

```python
# backend/market/simulator.py
import asyncio
import math
import random
import time

from .base import MarketSource
from .cache import PriceCache
from .sim_config import SEED, TickerSpec

TICK_SECONDS = 0.5
TRADING_YEAR_SECONDS = 6.5 * 60 * 60 * 252
DT = TICK_SECONDS / TRADING_YEAR_SECONDS
MU = 0.05                     # gentle upward drift
EVENT_PROB = 0.005            # per-ticker chance of a dramatic move per tick

# Correlation weights (squares sum to 1 → preserves unit variance)
W_MARKET, W_SECTOR = 0.5, 0.4
W_IDIO = math.sqrt(1 - W_MARKET**2 - W_SECTOR**2)


class SimulatorSource(MarketSource):
    """In-process GBM price generator. No external dependencies."""

    def __init__(self, cache: PriceCache, specs: list[TickerSpec] = SEED, seed: int | None = None) -> None:
        super().__init__(cache)
        self._specs = {s.ticker: s for s in specs}
        self._price = {s.ticker: s.seed_price for s in specs}
        self._rng = random.Random(seed)

    @property
    def universe(self) -> set[str]:
        return set(self._specs)

    async def run(self) -> None:
        # Prime the cache so the first SSE push has data immediately.
        now = time.time()
        for ticker, price in self._price.items():
            self.cache.set_price(ticker, price, now)
        while True:
            self._step()
            await asyncio.sleep(TICK_SECONDS)

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
        if self._rng.random() < EVENT_PROB:
            shock = self._rng.uniform(0.02, 0.05) * self._rng.choice((-1, 1))
            return price * (1 + shock)
        return price
```

## 7. Interface Conformance

| `MarketSource` requirement | Simulator behavior |
|----------------------------|--------------------|
| `run()` writes the cache | Primes cache, then ticks every 500ms calling `set_price` for all tickers |
| `universe` | The seeded symbol set |
| `knows(ticker)` | True for seeded symbols → watchlist-add accepts only known tickers (PLAN §13.11) |

The cache derives `prev_price`, `open_price`, `change`, and `direction` from the
stream of `set_price` calls — the simulator only supplies the latest price and
timestamp, exactly like the Massive source.

## 8. Testing Notes (per PLAN §12)

- **Determinism:** pass `seed=` to `SimulatorSource` for reproducible sequences.
- **GBM correctness:** over many steps with `sigma=0`, prices follow pure drift
  `S * exp(MU * DT)`; assert that. With drift 0 and many steps, the mean log
  return is ~0.
- **Positivity:** GBM never produces a non-positive price — assert `price > 0`.
- **Conformance:** the same test suite that exercises the abstract `MarketSource`
  should run against both `SimulatorSource` and a mocked `MassiveSource`.
- **No event needed for unit tests:** set `EVENT_PROB = 0` (or seed) to isolate the
  GBM path from event jumps.
