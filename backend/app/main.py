import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.chat import create_chat_router
from .api.portfolio import create_portfolio_router
from .api.watchlist import create_watchlist_router
from .db import repository
from .db.database import get_connection, init_db
from .market.cache import PriceCache
from .market.factory import create_source
from .market.stream import create_stream_router
from .services import portfolio as portfolio_service
from .static_files import mount_static

SNAPSHOT_INTERVAL_SECONDS = 30.0


def _current_watchlist_tickers() -> set[str]:
    """Watchlist union callback for the market source (PLAN §6 / MARKET_INTERFACE §5).

    Reads the live watchlist from SQLite on its own short-lived connection — the
    simulator ignores this, the Massive poller uses it to size each request.
    """
    conn = get_connection()
    try:
        return set(repository.list_watchlist(conn))
    finally:
        conn.close()


async def _snapshot_loop(cache: PriceCache) -> None:
    """Record a portfolio value snapshot every 30s, always-on (PLAN §7, §13.8).

    Uses its own connection so it never shares a sqlite3.Connection across the
    async/thread boundary with request handlers. insert_snapshot also prunes
    rows older than 7 days (PLAN §13.8), so the table stays bounded.
    """
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        try:
            conn = get_connection()
            try:
                total_value = portfolio_service.compute_total_value(conn, cache)
                repository.insert_snapshot(conn, total_value)
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # A transient DB/price hiccup must not kill the long-lived task.
            continue


def create_app() -> FastAPI:
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Lazily create + seed the database before anything reads the watchlist.
        init_db()

        source = create_source(cache, watched=_current_watchlist_tickers)
        app.state.cache = cache
        app.state.source = source

        source_task = asyncio.create_task(source.run(), name="market-source")
        snapshot_task = asyncio.create_task(_snapshot_loop(cache), name="portfolio-snapshot")
        try:
            yield
        finally:
            for task in (source_task, snapshot_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="FinAlly Backend", lifespan=lifespan)

    # API routes first so the SPA static mount at "/" never shadows them.
    app.include_router(create_stream_router(cache))
    app.include_router(create_portfolio_router())
    app.include_router(create_watchlist_router())
    app.include_router(create_chat_router())

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # Static export mounted last, with SPA fallback. Tolerates a missing dir (dev).
    mount_static(app)

    return app


app = create_app()
