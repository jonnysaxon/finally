"""Tests for portfolio business rules (PLAN §7, §13.5-13.7)."""

import pytest

from app.db import repository
from app.services import portfolio as svc
from app.services.portfolio import TradeError

# ---- buys -------------------------------------------------------------------


def test_buy_decrements_cash_and_creates_position(db, cache):
    result = svc.execute_trade(db, cache, "AAPL", "buy", 10)
    assert result["cash_balance"] == pytest.approx(10000.0 - 190.0 * 10)
    pos = result["position"]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == pytest.approx(10)
    assert pos["avg_cost"] == pytest.approx(190.0)
    # Returned position is fully valued (matches PositionOut / build_portfolio shape).
    assert pos["current_price"] == pytest.approx(190.0)
    assert pos["market_value"] == pytest.approx(1900.0)
    assert pos["unrealized_pnl"] == pytest.approx(0.0)  # bought at current price
    assert pos["pnl_pct"] == pytest.approx(0.0)
    # Persisted.
    stored = repository.get_position(db, "AAPL")
    assert stored["quantity"] == pytest.approx(10)


def test_buy_records_trade_row(db, cache):
    result = svc.execute_trade(db, cache, "AAPL", "buy", 2)
    trade = result["trade"]
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == pytest.approx(2)
    assert trade["price"] == pytest.approx(190.0)
    assert trade["id"]
    assert repository.list_trades(db)[0]["id"] == trade["id"]


def test_buy_writes_snapshot(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 5)
    snaps = repository.list_snapshots(db)
    assert len(snaps) == 1
    # cash + 5*190 = 10000 always (bought at current price, no fees).
    assert snaps[0]["total_value"] == pytest.approx(10000.0)


def test_second_buy_uses_weighted_average_cost(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)  # avg 190
    cache.set_price("AAPL", 200.0)
    result = svc.execute_trade(db, cache, "AAPL", "buy", 10)  # avg of 190 and 200
    assert result["position"]["quantity"] == pytest.approx(20)
    assert result["position"]["avg_cost"] == pytest.approx((10 * 190 + 10 * 200) / 20)


def test_buy_insufficient_cash_raises(db, cache):
    with pytest.raises(TradeError, match="Insufficient cash"):
        svc.execute_trade(db, cache, "AAPL", "buy", 1000)  # 1000*190 >> 10000
    # No partial state.
    assert repository.get_position(db, "AAPL") is None
    assert repository.get_profile(db)["cash_balance"] == pytest.approx(10000.0)


# ---- sells ------------------------------------------------------------------


def test_sell_increments_cash_and_reduces_quantity(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)
    result = svc.execute_trade(db, cache, "AAPL", "sell", 4)
    assert result["position"]["quantity"] == pytest.approx(6)
    expected_cash = 10000.0 - 190.0 * 10 + 190.0 * 4
    assert result["cash_balance"] == pytest.approx(expected_cash)


def test_sell_keeps_avg_cost_unchanged(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)  # avg 190
    cache.set_price("AAPL", 250.0)
    result = svc.execute_trade(db, cache, "AAPL", "sell", 3)  # price moved, avg must not
    pos = result["position"]
    assert pos["avg_cost"] == pytest.approx(190.0)
    # Remaining 7 shares valued at the moved price, P&L against unchanged avg cost.
    assert pos["quantity"] == pytest.approx(7)
    assert pos["current_price"] == pytest.approx(250.0)
    assert pos["market_value"] == pytest.approx(7 * 250.0)
    assert pos["unrealized_pnl"] == pytest.approx(7 * (250.0 - 190.0))


def test_full_sell_deletes_position(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)
    result = svc.execute_trade(db, cache, "AAPL", "sell", 10)
    assert result["position"] is None
    assert repository.get_position(db, "AAPL") is None


def test_sell_more_than_held_raises_no_shorting(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 5)
    with pytest.raises(TradeError, match="no shorting"):
        svc.execute_trade(db, cache, "AAPL", "sell", 6)
    # Quantity never clamped, never negative.
    assert repository.get_position(db, "AAPL")["quantity"] == pytest.approx(5)


def test_sell_with_no_position_raises(db, cache):
    with pytest.raises(TradeError):
        svc.execute_trade(db, cache, "AAPL", "sell", 1)


# ---- validation -------------------------------------------------------------


def test_trade_unknown_price_raises(db, cache):
    with pytest.raises(TradeError, match="No price"):
        svc.execute_trade(db, cache, "TSLA", "buy", 1)  # not in cache


def test_trade_zero_quantity_raises(db, cache):
    with pytest.raises(TradeError, match="greater than zero"):
        svc.execute_trade(db, cache, "AAPL", "buy", 0)


def test_trade_invalid_side_raises(db, cache):
    with pytest.raises(TradeError, match="Invalid side"):
        svc.execute_trade(db, cache, "AAPL", "hold", 1)


def test_ticker_is_case_insensitive(db, cache):
    result = svc.execute_trade(db, cache, "aapl", "buy", 1)
    assert result["position"]["ticker"] == "AAPL"


# ---- valuation --------------------------------------------------------------


def test_build_portfolio_empty(db, cache):
    p = svc.build_portfolio(db, cache)
    assert p["cash_balance"] == pytest.approx(10000.0)
    assert p["total_value"] == pytest.approx(10000.0)
    assert p["positions_value"] == pytest.approx(0.0)
    assert p["positions"] == []


def test_build_portfolio_computes_pnl(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)  # cost 1900 @ 190
    cache.set_price("AAPL", 200.0)  # +10/share
    p = svc.build_portfolio(db, cache)
    pos = p["positions"][0]
    assert pos["current_price"] == pytest.approx(200.0)
    assert pos["market_value"] == pytest.approx(2000.0)
    assert pos["unrealized_pnl"] == pytest.approx(100.0)
    assert pos["pnl_pct"] == pytest.approx(100.0 / 1900.0)
    assert p["positions_value"] == pytest.approx(2000.0)
    assert p["total_value"] == pytest.approx(10000.0 - 1900.0 + 2000.0)


def test_build_portfolio_handles_priceless_position(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)
    # Drop AAPL from the cache by using a fresh cache with no AAPL price.
    from app.market.cache import PriceCache

    empty = PriceCache()
    p = svc.build_portfolio(db, empty)
    pos = p["positions"][0]
    assert pos["current_price"] is None
    assert pos["market_value"] == pytest.approx(0.0)
    assert pos["unrealized_pnl"] == pytest.approx(0.0)


def test_compute_total_value(db, cache):
    svc.execute_trade(db, cache, "AAPL", "buy", 10)
    cache.set_price("AAPL", 210.0)
    total = svc.compute_total_value(db, cache)
    assert total == pytest.approx(10000.0 - 1900.0 + 2100.0)
