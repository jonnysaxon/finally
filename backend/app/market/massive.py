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
    cache. One request per interval covers the entire watchlist.

    Uses httpx.AsyncClient directly so it never blocks the event loop (the
    official synchronous Massive/Polygon client would block).
    """

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
            # retry next interval.
            return
        for row in resp.json().get("tickers", []):
            price = _extract_price(row)
            if price is not None:
                self.cache.set_price(row["ticker"], price, _extract_ts(row))
                self._universe.add(row["ticker"].upper())

    async def validate_symbol(self, ticker: str) -> bool:
        """Accept a symbol if Massive returns a snapshot for it. Caches the result
        in the universe so subsequent checks are free and the next poll includes it.
        """
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
