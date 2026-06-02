from app.market.cache import PriceCache


def test_initial_version_is_zero():
    c = PriceCache()
    assert c.version == 0


def test_first_set_price_sets_open_prev_equal_to_price():
    c = PriceCache()
    q = c.set_price("AAPL", 190.0)
    assert q.price == 190.0
    assert q.prev_price == 190.0
    assert q.open_price == 190.0


def test_first_set_price_direction_flat():
    c = PriceCache()
    q = c.set_price("AAPL", 190.0)
    assert q.direction == "flat"


def test_first_set_price_bumps_version():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    assert c.version == 1


def test_second_different_price_updates_prev_price():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    q = c.set_price("AAPL", 191.0)
    assert q.prev_price == 190.0
    assert q.price == 191.0


def test_second_different_price_preserves_open_price():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    q = c.set_price("AAPL", 191.0)
    assert q.open_price == 190.0


def test_second_different_price_bumps_version():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    v1 = c.version
    c.set_price("AAPL", 191.0)
    assert c.version == v1 + 1


def test_same_price_does_not_bump_version():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    v1 = c.version
    c.set_price("AAPL", 190.0)
    assert c.version == v1


def test_same_price_refreshes_timestamp():
    c = PriceCache()
    c.set_price("AAPL", 190.0, timestamp=1000.0)
    q = c.set_price("AAPL", 190.0, timestamp=2000.0)
    assert q.timestamp == 2000.0


def test_ticker_is_uppercased():
    c = PriceCache()
    c.set_price("aapl", 190.0)
    assert c.get("AAPL") is not None
    assert c.get("aapl") is not None


def test_get_returns_quote():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    q = c.get("AAPL")
    assert q is not None
    assert q.price == 190.0


def test_get_returns_none_for_unknown():
    c = PriceCache()
    assert c.get("UNKNOWN") is None


def test_get_price_returns_float():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    assert c.get_price("AAPL") == 190.0


def test_get_price_returns_none_for_unknown():
    c = PriceCache()
    assert c.get_price("UNKNOWN") is None


def test_all_returns_all_tickers():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    c.set_price("MSFT", 420.0)
    all_quotes = c.all()
    assert "AAPL" in all_quotes
    assert "MSFT" in all_quotes
    assert len(all_quotes) == 2


def test_all_returns_copy():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    snapshot = c.all()
    c.set_price("MSFT", 420.0)
    assert "MSFT" not in snapshot  # original snapshot is unaffected


def test_changed_since_returns_only_moved_tickers():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    c.set_price("MSFT", 420.0)
    base = c.version
    c.set_price("AAPL", 191.0)  # only AAPL moves
    changed, ver = c.changed_since(base)
    assert {q.ticker for q in changed} == {"AAPL"}
    assert ver == c.version


def test_changed_since_current_version_returns_empty():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    changed, ver = c.changed_since(c.version)
    assert changed == []
    assert ver == c.version


def test_changed_since_version_zero_returns_all():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    c.set_price("MSFT", 420.0)
    changed, ver = c.changed_since(0)
    assert {q.ticker for q in changed} == {"AAPL", "MSFT"}


def test_multiple_tickers_independent_versions():
    c = PriceCache()
    c.set_price("AAPL", 190.0)
    c.set_price("MSFT", 420.0)
    v_after_two = c.version
    c.set_price("AAPL", 191.0)
    c.set_price("MSFT", 421.0)
    changed, _ = c.changed_since(v_after_two)
    assert {q.ticker for q in changed} == {"AAPL", "MSFT"}
