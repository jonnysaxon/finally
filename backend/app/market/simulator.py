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
    """In-process GBM price generator. No external dependencies.

    Generates realistic, continuously moving prices for the seeded universe
    using Geometric Brownian Motion with correlated sector shocks and
    occasional dramatic event moves.
    """

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
        """Occasional ±2–5% shock on top of the GBM step."""
        if self._rng.random() < self._event_prob:
            shock = self._rng.uniform(0.02, 0.05) * self._rng.choice((-1, 1))
            return price * (1 + shock)
        return price
