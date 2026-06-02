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


async def price_event_stream(
    cache: PriceCache,
    request: Request,
    push_seconds: float = PUSH_SECONDS,
    keepalive_seconds: float = KEEPALIVE_SECONDS,
) -> AsyncGenerator[str, None]:
    """Core SSE generator. Exposed at module level so it can be unit-tested directly.

    Starts from version 0 so a freshly connected client immediately receives
    the full current snapshot (every cached ticker counts as "changed since 0").
    Emits only changed quotes (PLAN §13.3); sends a keepalive comment every
    `keepalive_seconds` to keep proxies from closing idle connections.
    """
    last_version = 0
    last_keepalive = asyncio.get_running_loop().time()

    # Tell EventSource to retry after 3s if the connection drops.
    yield "retry: 3000\n\n"

    while True:
        if await request.is_disconnected():
            break

        changed, last_version = cache.changed_since(last_version)
        for quote in changed:
            payload = json.dumps(quote.to_event())
            yield f"event: price\ndata: {payload}\n\n"

        now = asyncio.get_running_loop().time()
        if now - last_keepalive >= keepalive_seconds:
            yield ": keepalive\n\n"
            last_keepalive = now

        await asyncio.sleep(push_seconds)


def create_stream_router(cache: PriceCache) -> APIRouter:
    """Factory so the cache is injected (no module-level globals)."""
    router = APIRouter()

    @router.get("/api/stream/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            price_event_stream(cache, request),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return router
