import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .market.cache import PriceCache
from .market.factory import create_source
from .market.stream import create_stream_router


def _placeholder_watchlist() -> set[str]:
    """Placeholder until the database/watchlist module is wired in."""
    return {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"}


def create_app() -> FastAPI:
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # `watched` is the watchlist union callback; simulator ignores it,
        # Massive uses it to size each snapshot request.
        source = create_source(cache, watched=_placeholder_watchlist)
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

    app = FastAPI(title="FinAlly Backend", lifespan=lifespan)
    app.include_router(create_stream_router(cache))

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
