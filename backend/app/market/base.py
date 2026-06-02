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
        (PLAN §13.11).
        """
        return self.knows(ticker)
