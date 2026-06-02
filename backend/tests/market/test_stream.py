import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock

from app.market.cache import PriceCache
from app.market.stream import (
    price_event_stream,
    create_stream_router,
    PUSH_SECONDS,
    KEEPALIVE_SECONDS,
    SSE_HEADERS,
)


def make_fake_request(disconnect_after: int = 1) -> MagicMock:
    """Request that reports is_disconnected() True after `disconnect_after` calls."""
    call_count = 0

    async def is_disconnected() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > disconnect_after

    req = MagicMock()
    req.is_disconnected = is_disconnected
    return req


async def collect_chunks(
    cache: PriceCache,
    disconnect_after: int = 2,
    keepalive_seconds: float = 999.0,   # suppress keepalive in tests
    push_seconds: float = 0.001,        # minimal sleep so tests stay fast
) -> list[str]:
    """Collect all SSE chunks from price_event_stream until disconnect."""
    request = make_fake_request(disconnect_after)
    chunks: list[str] = []
    async for chunk in price_event_stream(
        cache, request, push_seconds=push_seconds, keepalive_seconds=keepalive_seconds
    ):
        chunks.append(chunk)
    return chunks


# ---- SSE wire format (unit tests on the generator) ----------------------

@pytest.mark.asyncio
async def test_first_chunk_is_retry():
    cache = PriceCache()
    chunks = await collect_chunks(cache, disconnect_after=1)
    assert chunks[0] == "retry: 3000\n\n"


@pytest.mark.asyncio
async def test_initial_snapshot_includes_all_cached_tickers():
    cache = PriceCache()
    cache.set_price("AAPL", 190.0)
    cache.set_price("MSFT", 420.0)
    chunks = await collect_chunks(cache, disconnect_after=1)
    event_data = []
    for c in chunks:
        if c.startswith("event: price\ndata: "):
            data_line = c.split("\n")[1]
            event_data.append(json.loads(data_line[len("data: "):]))
    tickers = {e["ticker"] for e in event_data}
    assert tickers == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_event_frames_have_correct_prefix():
    cache = PriceCache()
    cache.set_price("AAPL", 190.0)
    chunks = await collect_chunks(cache, disconnect_after=1)
    price_events = [c for c in chunks if c.startswith("event: price")]
    assert len(price_events) >= 1
    for chunk in price_events:
        assert chunk.startswith("event: price\ndata: ")
        assert chunk.endswith("\n\n")


@pytest.mark.asyncio
async def test_data_payload_is_valid_json():
    cache = PriceCache()
    cache.set_price("AAPL", 191.5)
    chunks = await collect_chunks(cache, disconnect_after=1)
    data_chunks = [c for c in chunks if c.startswith("event: price")]
    assert data_chunks
    for chunk in data_chunks:
        # chunk = "event: price\ndata: {...}\n\n"
        data_line = chunk.split("\n")[1]  # "data: {...}"
        payload = json.loads(data_line[len("data: "):])
        assert payload["ticker"] == "AAPL"
        assert payload["price"] == pytest.approx(191.5, abs=0.01)
        assert payload["direction"] in ("up", "down", "flat")


@pytest.mark.asyncio
async def test_empty_cache_yields_only_retry_and_no_events():
    cache = PriceCache()
    chunks = await collect_chunks(cache, disconnect_after=1)
    assert chunks[0] == "retry: 3000\n\n"
    price_events = [c for c in chunks if c.startswith("event: price")]
    assert price_events == []


@pytest.mark.asyncio
async def test_second_iteration_emits_only_changed_tickers():
    cache = PriceCache()
    cache.set_price("AAPL", 190.0)
    cache.set_price("MSFT", 420.0)

    # disconnect_after=2 → two is_disconnected checks → one retry + one snapshot + one empty loop
    chunks = await collect_chunks(cache, disconnect_after=2, push_seconds=0.001)

    # Move AAPL price after cache is primed so the second iteration sees a change.
    # Actually in this test the prices don't change, so the second iteration should emit nothing.
    price_event_chunks = [c for c in chunks if c.startswith("event: price")]
    tickers = [
        json.loads(c.split("\n")[1][len("data: "):])["ticker"]
        for c in price_event_chunks
    ]
    # Both tickers in first snapshot, nothing new in second (prices unchanged).
    assert set(tickers) == {"AAPL", "MSFT"}
    assert tickers.count("AAPL") == 1
    assert tickers.count("MSFT") == 1


@pytest.mark.asyncio
async def test_keepalive_comment_is_emitted():
    cache = PriceCache()
    request = make_fake_request(disconnect_after=2)
    chunks: list[str] = []
    async for chunk in price_event_stream(
        cache, request, push_seconds=0.001, keepalive_seconds=0.0
    ):
        chunks.append(chunk)

    keepalive_chunks = [c for c in chunks if c.startswith(": keepalive")]
    assert len(keepalive_chunks) >= 1


@pytest.mark.asyncio
async def test_disconnect_stops_generator():
    """Generator stops as soon as is_disconnected() returns True."""
    cache = PriceCache()
    request = make_fake_request(disconnect_after=0)  # disconnect immediately
    chunks: list[str] = []
    async for chunk in price_event_stream(cache, request, push_seconds=0.001):
        chunks.append(chunk)
    # Should get at most the retry line.
    assert len(chunks) <= 1


# ---- Router wiring (integration) ----------------------------------------

def test_stream_router_registers_prices_endpoint():
    cache = PriceCache()
    router = create_stream_router(cache)
    paths = [route.path for route in router.routes]
    assert "/api/stream/prices" in paths


# ---- Constants ----------------------------------------------------------

def test_push_seconds():
    assert PUSH_SECONDS == pytest.approx(0.5)


def test_keepalive_seconds():
    assert KEEPALIVE_SECONDS == pytest.approx(15.0)


def test_sse_header_no_cache():
    assert SSE_HEADERS["Cache-Control"] == "no-cache"


def test_sse_header_no_buffering():
    assert SSE_HEADERS["X-Accel-Buffering"] == "no"
