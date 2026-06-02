import pytest
from app.market.types import Quote


def test_direction_up():
    q = Quote("AAPL", 191.0, 190.0, 190.0, 1.0)
    assert q.direction == "up"


def test_direction_down():
    q = Quote("AAPL", 189.0, 190.0, 190.0, 1.0)
    assert q.direction == "down"


def test_direction_flat():
    q = Quote("AAPL", 190.0, 190.0, 190.0, 1.0)
    assert q.direction == "flat"


def test_change():
    q = Quote("AAPL", 191.0, 190.5, 190.0, 1.0)
    assert q.change == pytest.approx(1.0)


def test_change_negative():
    q = Quote("AAPL", 189.0, 190.0, 190.0, 1.0)
    assert q.change == pytest.approx(-1.0)


def test_change_pct():
    q = Quote("AAPL", 191.0, 190.5, 190.0, 1.0)
    assert q.change_pct == pytest.approx(1.0 / 190.0)


def test_change_pct_zero_open_guard():
    q = Quote("AAPL", 191.0, 190.0, 0.0, 1.0)
    assert q.change_pct == 0.0


def test_to_event_has_required_keys():
    q = Quote("AAPL", 191.0, 190.0, 190.0, 1_000_000.0)
    event = q.to_event()
    assert set(event.keys()) == {"ticker", "price", "prev_price", "open_price", "change", "change_pct", "direction", "timestamp"}


def test_to_event_ticker():
    q = Quote("AAPL", 191.0, 190.0, 190.0, 1.0)
    assert q.to_event()["ticker"] == "AAPL"


def test_to_event_direction():
    q = Quote("AAPL", 191.0, 190.0, 190.0, 1.0)
    assert q.to_event()["direction"] == "up"


def test_to_event_rounding():
    q = Quote("AAPL", 191.123456789, 190.0, 190.0, 1.0)
    event = q.to_event()
    assert event["price"] == round(191.123456789, 4)
    assert event["change_pct"] == round(q.change_pct, 6)


def test_immutable_ticker():
    q = Quote("AAPL", 191.0, 190.0, 190.0, 1.0)
    with pytest.raises((AttributeError, TypeError)):
        q.ticker = "MSFT"  # type: ignore


def test_immutable_price():
    q = Quote("AAPL", 191.0, 190.0, 190.0, 1.0)
    with pytest.raises((AttributeError, TypeError)):
        q.price = 200.0  # type: ignore
