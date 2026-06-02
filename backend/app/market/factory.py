import os
from .cache import PriceCache
from .base import MarketSource
from .simulator import SimulatorSource
from .massive import MassiveSource


def create_source(cache: PriceCache, watched: "callable") -> MarketSource:
    """Massive if MASSIVE_API_KEY is set and non-empty, else the simulator.

    `watched` is a callback returning the current watchlist tickers as a set[str].
    The simulator ignores it (its universe is fixed); the Massive poller uses it
    to size each snapshot request.

    `MASSIVE_POLL_SECONDS` overrides the poll interval (default 15s), allowing
    paid tiers to poll faster without a code change.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        interval = float(os.environ.get("MASSIVE_POLL_SECONDS", "15"))
        return MassiveSource(cache, api_key, watched, interval=interval)
    return SimulatorSource(cache)
