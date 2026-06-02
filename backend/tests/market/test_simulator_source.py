import asyncio

import pytest

from app.market.cache import PriceCache
from app.market.sim_config import SEED
from app.market.simulator import SimulatorSource


@pytest.mark.asyncio
async def test_run_primes_cache_immediately():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42)
    task = asyncio.create_task(src.run())
    await asyncio.sleep(0.0)  # yield to let the task prime the cache
    for spec in SEED:
        assert cache.get(spec.ticker) is not None, f"{spec.ticker} not primed"
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_run_advances_version_after_one_tick():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42, event_prob=0)
    task = asyncio.create_task(src.run())
    await asyncio.sleep(0.0)  # prime
    v0 = cache.version
    await asyncio.sleep(0.6)  # wait for at least one 500ms tick
    assert cache.version > v0
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_run_cancels_cleanly():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42)
    task = asyncio.create_task(src.run())
    await asyncio.sleep(0.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_validate_symbol_returns_true_for_seeded():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42)
    assert await src.validate_symbol("AAPL")


@pytest.mark.asyncio
async def test_validate_symbol_returns_false_for_unknown():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42)
    assert not await src.validate_symbol("UNKNOWN_TICKER_XYZ")


@pytest.mark.asyncio
async def test_validate_symbol_case_insensitive():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42)
    assert await src.validate_symbol("aapl")
    assert await src.validate_symbol("Aapl")


@pytest.mark.asyncio
async def test_run_multiple_ticks():
    cache = PriceCache()
    src = SimulatorSource(cache, seed=42, event_prob=0)
    task = asyncio.create_task(src.run())
    await asyncio.sleep(0.0)  # prime
    v0 = cache.version
    await asyncio.sleep(1.2)  # ~2 ticks at 500ms
    assert cache.version >= v0 + len(SEED)  # each ticker moved at least once
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
