"""Structured-output schema validation (PLAN §9)."""

import pytest
from pydantic import ValidationError

from app.llm.schema import ChatResponse, TradeAction, WatchlistChange


def test_minimal_message_only():
    r = ChatResponse.model_validate_json('{"message": "hi"}')
    assert r.message == "hi"
    assert r.trades == []
    assert r.watchlist_changes == []


def test_full_payload_parses():
    raw = """
    {
      "message": "Bought AAPL and added PYPL",
      "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
      "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
    }
    """
    r = ChatResponse.model_validate_json(raw)
    assert r.trades[0] == TradeAction(ticker="AAPL", side="buy", quantity=10)
    assert r.watchlist_changes[0] == WatchlistChange(ticker="PYPL", action="add")


def test_fractional_quantity():
    t = TradeAction(ticker="NVDA", side="sell", quantity=2.5)
    assert t.quantity == 2.5


def test_invalid_side_rejected():
    with pytest.raises(ValidationError):
        TradeAction(ticker="AAPL", side="hold", quantity=1)


def test_invalid_watchlist_action_rejected():
    with pytest.raises(ValidationError):
        WatchlistChange(ticker="AAPL", action="star")


def test_missing_message_rejected():
    with pytest.raises(ValidationError):
        ChatResponse.model_validate_json('{"trades": []}')
