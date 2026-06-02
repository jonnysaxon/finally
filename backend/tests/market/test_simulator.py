import math

import pytest

from app.market.cache import PriceCache
from app.market.sim_config import SEED, TickerSpec
from app.market.simulator import DT, MU, SimulatorSource


def make_source(seed: int = 42, event_prob: float = 0) -> tuple[PriceCache, SimulatorSource]:
    cache = PriceCache()
    src = SimulatorSource(cache, seed=seed, event_prob=event_prob)
    return cache, src


def test_universe_equals_seeded_symbols():
    _, src = make_source()
    seeded = {s.ticker for s in SEED}
    assert src.universe == seeded


def test_knows_seeded_ticker():
    _, src = make_source()
    assert src.knows("AAPL")
    assert src.knows("aapl")  # case-insensitive


def test_does_not_know_unknown_ticker():
    _, src = make_source()
    assert not src.knows("UNKNOWN_TICKER_XYZ")


def test_deterministic_same_seed():
    cache1 = PriceCache()
    cache2 = PriceCache()
    src1 = SimulatorSource(cache1, seed=42, event_prob=0)
    src2 = SimulatorSource(cache2, seed=42, event_prob=0)
    src1._step()
    src2._step()
    for spec in SEED:
        assert cache1.get_price(spec.ticker) == cache2.get_price(spec.ticker)


def test_different_seeds_produce_different_prices():
    cache1 = PriceCache()
    cache2 = PriceCache()
    src1 = SimulatorSource(cache1, seed=1, event_prob=0)
    src2 = SimulatorSource(cache2, seed=2, event_prob=0)
    src1._step()
    src2._step()
    prices1 = [cache1.get_price(s.ticker) for s in SEED]
    prices2 = [cache2.get_price(s.ticker) for s in SEED]
    assert prices1 != prices2


def test_prices_always_positive_after_many_steps():
    cache, src = make_source(seed=99)
    for _ in range(100):
        src._step()
    for spec in SEED:
        price = cache.get_price(spec.ticker)
        assert price is not None
        assert price > 0


def test_drift_only_follows_gbm():
    """With sigma=0 and event_prob=0, price follows pure drift S * exp(MU * DT)."""
    spec = TickerSpec("TEST", 100.0, 0.0, "tech")
    cache = PriceCache()
    src = SimulatorSource(cache, specs=[spec], seed=0, event_prob=0)
    src._step()
    # The internal price (before rounding) should follow pure drift.
    expected = 100.0 * math.exp(MU * DT)
    assert src._price["TEST"] == pytest.approx(expected, rel=1e-9)


def test_gbm_step_positive_for_extreme_z_positive():
    _, src = make_source()
    price = src._gbm_step(100.0, 0.3, 10.0)
    assert price > 0


def test_gbm_step_positive_for_extreme_z_negative():
    _, src = make_source()
    price = src._gbm_step(100.0, 0.3, -10.0)
    assert price > 0


def test_event_prob_zero_no_large_moves():
    """With event_prob=0, moves within 20 ticks should be modest."""
    cache, src = make_source(seed=42, event_prob=0)
    initial_prices = dict(src._price)
    for _ in range(20):
        src._step()
    for ticker, start in initial_prices.items():
        end = src._price[ticker]
        pct_change = abs(end - start) / start
        # GBM with small DT cannot move more than 20% in 20 ticks without events
        assert pct_change < 0.20


def test_event_prob_one_always_shocks():
    """With event_prob=1, every tick should produce a large move."""
    spec = TickerSpec("TEST", 100.0, 0.0, "tech")
    cache = PriceCache()
    src = SimulatorSource(cache, specs=[spec], seed=1, event_prob=1.0)
    before = src._price["TEST"]
    src._step()
    after = src._price["TEST"]
    pct_change = abs(after - before) / before
    assert pct_change >= 0.02  # always shocks ±2-5%


def test_step_rounds_price_to_two_decimals():
    cache, src = make_source()
    src._step()
    for spec in SEED:
        price = cache.get_price(spec.ticker)
        assert price is not None
        # round() to 2 places should be a no-op
        assert price == round(price, 2)


def test_custom_specs():
    specs = [TickerSpec("CUSTOM", 50.0, 0.1, "tech")]
    cache = PriceCache()
    src = SimulatorSource(cache, specs=specs, seed=0, event_prob=0)
    assert src.universe == {"CUSTOM"}
    src._step()
    assert cache.get_price("CUSTOM") is not None
