import time
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.market.cache import PriceCache
from app.market.massive import MassiveSource, _extract_price, _extract_ts


# ---- _extract_price tests ------------------------------------------------

def test_extract_price_prefers_last_trade():
    row = {"lastTrade": {"p": 191.23}, "day": {"c": 190.0}}
    assert _extract_price(row) == pytest.approx(191.23)


def test_extract_price_falls_back_to_day_close():
    row = {"day": {"c": 190.0}}
    assert _extract_price(row) == pytest.approx(190.0)


def test_extract_price_returns_none_when_both_absent():
    assert _extract_price({}) is None


def test_extract_price_returns_none_for_zero_day_close():
    # A zero close would be falsy; treat as absent.
    row = {"day": {"c": 0}}
    assert _extract_price(row) is None


def test_extract_price_handles_null_last_trade_key():
    row = {"lastTrade": None, "day": {"c": 190.0}}
    assert _extract_price(row) == pytest.approx(190.0)


# ---- _extract_ts tests ---------------------------------------------------

def test_extract_ts_converts_nanoseconds():
    ns = 1_700_000_000_000_000_000
    ts = _extract_ts({"lastTrade": {"t": ns}})
    assert ts == pytest.approx(1_700_000_000.0)


def test_extract_ts_falls_back_to_now_when_missing():
    before = time.time()
    ts = _extract_ts({})
    after = time.time()
    assert before <= ts <= after


def test_extract_ts_handles_null_last_trade():
    before = time.time()
    ts = _extract_ts({"lastTrade": None})
    after = time.time()
    assert before <= ts <= after


# ---- _poll_once tests ----------------------------------------------------

@pytest.mark.asyncio
async def test_poll_once_writes_cache():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: {"AAPL"})
    body = {
        "tickers": [
            {"ticker": "AAPL", "lastTrade": {"p": 191.23, "t": 1_700_000_000_000_000_000}}
        ]
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        await src._poll_once(client)
    assert cache.get_price("AAPL") == pytest.approx(191.23)
    assert "AAPL" in src.universe


@pytest.mark.asyncio
async def test_poll_once_silently_handles_http_error():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: {"AAPL"})
    transport = httpx.MockTransport(lambda req: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as client:
        await src._poll_once(client)  # must not raise
    assert cache.get("AAPL") is None  # nothing written on error


@pytest.mark.asyncio
async def test_poll_once_skips_tickers_with_missing_price():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: {"AAPL"})
    body = {"tickers": [{"ticker": "AAPL"}]}  # no lastTrade or day
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        await src._poll_once(client)
    assert cache.get("AAPL") is None


@pytest.mark.asyncio
async def test_poll_once_empty_watchlist_makes_no_request():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: set())
    request_count = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"tickers": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await src._poll_once(client)
    assert request_count == 0


@pytest.mark.asyncio
async def test_poll_once_adds_tickers_to_universe():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: {"AAPL", "MSFT"})
    body = {
        "tickers": [
            {"ticker": "AAPL", "lastTrade": {"p": 191.0, "t": 1_700_000_000_000_000_000}},
            {"ticker": "MSFT", "lastTrade": {"p": 420.0, "t": 1_700_000_000_000_000_000}},
        ]
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        await src._poll_once(client)
    assert "AAPL" in src.universe
    assert "MSFT" in src.universe


# ---- validate_symbol tests -----------------------------------------------

@pytest.mark.asyncio
async def test_validate_symbol_known_short_circuits():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: set())
    src._universe.add("AAPL")
    # Should return True without making any network call.
    assert await src.validate_symbol("AAPL")


@pytest.mark.asyncio
async def test_validate_symbol_known_is_case_insensitive():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: set())
    src._universe.add("AAPL")
    assert await src.validate_symbol("aapl")


@pytest.mark.asyncio
async def test_validate_symbol_live_lookup_success():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: set())
    body = {"ticker": {"lastTrade": {"p": 191.23}}}

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=body)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.market.massive.httpx.AsyncClient", return_value=mock_client):
        result = await src.validate_symbol("NVDA")

    assert result is True
    assert "NVDA" in src.universe


@pytest.mark.asyncio
async def test_validate_symbol_live_lookup_http_error():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: set())

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("error"))

    with patch("app.market.massive.httpx.AsyncClient", return_value=mock_client):
        result = await src.validate_symbol("NOTASTOCK")

    assert result is False
    assert "NOTASTOCK" not in src.universe


@pytest.mark.asyncio
async def test_validate_symbol_live_lookup_no_price_in_response():
    cache = PriceCache()
    src = MassiveSource(cache, api_key="test_key", watched=lambda: set())
    body = {"ticker": {}}  # ticker found but no price data

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=body)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.market.massive.httpx.AsyncClient", return_value=mock_client):
        result = await src.validate_symbol("NOPRICE")

    assert result is False
