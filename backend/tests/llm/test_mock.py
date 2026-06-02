"""Deterministic mock LLM triggers (PLAN §9 LLM Mock Mode).

These are the exact triggers the integration-tester relies on, so they are
asserted precisely here.
"""

from app.llm.mock import mock_response


def test_buy_trigger():
    r = mock_response("Please buy 5 AAPL for me")
    assert len(r.trades) == 1
    assert r.trades[0].ticker == "AAPL"
    assert r.trades[0].side == "buy"
    assert r.trades[0].quantity == 5
    assert r.watchlist_changes == []


def test_sell_trigger():
    r = mock_response("sell 3 TSLA now")
    assert r.trades[0].side == "sell"
    assert r.trades[0].ticker == "TSLA"
    assert r.trades[0].quantity == 3


def test_fractional_buy():
    r = mock_response("buy 2.5 NVDA")
    assert r.trades[0].quantity == 2.5


def test_add_watchlist_trigger():
    r = mock_response("add PYPL to my watchlist")
    assert r.trades == []
    assert len(r.watchlist_changes) == 1
    assert r.watchlist_changes[0].ticker == "PYPL"
    assert r.watchlist_changes[0].action == "add"


def test_watch_synonym():
    r = mock_response("watch NFLX")
    assert r.watchlist_changes[0].ticker == "NFLX"
    assert r.watchlist_changes[0].action == "add"


def test_remove_watchlist_trigger():
    r = mock_response("remove JPM")
    assert r.watchlist_changes[0].ticker == "JPM"
    assert r.watchlist_changes[0].action == "remove"


def test_buy_does_not_also_add():
    # "buy 5 AAPL" must not be interpreted as an "add AAPL" too.
    r = mock_response("buy 5 AAPL")
    assert len(r.trades) == 1
    assert r.watchlist_changes == []


def test_multiple_trades():
    r = mock_response("buy 5 AAPL and sell 2 TSLA")
    sides = {(t.side, t.ticker, t.quantity) for t in r.trades}
    assert ("buy", "AAPL", 5.0) in sides
    assert ("sell", "TSLA", 2.0) in sides


def test_no_action_message():
    r = mock_response("how is my portfolio doing?")
    assert r.trades == []
    assert r.watchlist_changes == []
    assert r.message  # non-empty conversational reply


def test_case_insensitive():
    r = mock_response("BUY 1 aapl")
    assert r.trades[0].ticker == "AAPL"
    assert r.trades[0].quantity == 1
