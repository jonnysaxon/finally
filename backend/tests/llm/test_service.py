"""Full handle_chat orchestration in mock mode (PLAN §9, offline)."""

import pytest

from app.db import repository
from app.llm import service
from app.llm.schema import ChatResponse, TradeAction


@pytest.mark.asyncio
async def test_buy_executes_and_decrements_cash(db, cache, source):
    before = repository.get_profile(db)["cash_balance"]
    result = await service.handle_chat(db, cache, source, "buy 5 AAPL")

    assert result["actions"]["trades"][0]["status"] == "executed"
    assert result["actions"]["trades"][0]["ticker"] == "AAPL"

    pos = repository.get_position(db, "AAPL")
    assert pos["quantity"] == 5
    after = repository.get_profile(db)["cash_balance"]
    assert after == pytest.approx(before - 5 * 190.0)


@pytest.mark.asyncio
async def test_messages_persisted(db, cache, source):
    await service.handle_chat(db, cache, source, "buy 1 AAPL")
    msgs = repository.list_chat_messages(db)
    assert msgs[-2]["role"] == "user"
    assert msgs[-2]["content"] == "buy 1 AAPL"
    assert msgs[-1]["role"] == "assistant"
    # assistant message carries the actions JSON
    assert msgs[-1]["actions"]["trades"][0]["status"] == "executed"


@pytest.mark.asyncio
async def test_watchlist_add_applied(db, cache, source):
    result = await service.handle_chat(db, cache, source, "add PYPL")
    assert result["actions"]["watchlist_changes"][0]["status"] == "applied"
    assert "PYPL" in repository.list_watchlist(db)


@pytest.mark.asyncio
async def test_watchlist_remove_applied(db, cache, source):
    result = await service.handle_chat(db, cache, source, "remove JPM")
    assert result["actions"]["watchlist_changes"][0]["status"] == "applied"
    assert "JPM" not in repository.list_watchlist(db)


@pytest.mark.asyncio
async def test_unknown_ticker_add_errors_but_does_not_crash(db, cache, source):
    result = await service.handle_chat(db, cache, source, "add ZZZZ")
    change = result["actions"]["watchlist_changes"][0]
    assert change["status"] == "error"
    assert "Unknown ticker" in change["error"]
    assert "ZZZZ" not in repository.list_watchlist(db)


@pytest.mark.asyncio
async def test_insufficient_cash_trade_errors(db, cache, source):
    # 10000 cash; 1000 shares of AAPL @190 is far too expensive.
    result = await service.handle_chat(db, cache, source, "buy 1000 AAPL")
    trade = result["actions"]["trades"][0]
    assert trade["status"] == "error"
    assert "Insufficient cash" in trade["error"]
    # no position created
    assert repository.get_position(db, "AAPL") is None


@pytest.mark.asyncio
async def test_oversell_errors(db, cache, source):
    result = await service.handle_chat(db, cache, source, "sell 5 AAPL")
    trade = result["actions"]["trades"][0]
    assert trade["status"] == "error"
    assert "only" in trade["error"].lower() or "shorting" in trade["error"].lower()


@pytest.mark.asyncio
async def test_no_action_message_only(db, cache, source):
    result = await service.handle_chat(db, cache, source, "how am I doing?")
    assert result["actions"]["trades"] == []
    assert result["actions"]["watchlist_changes"] == []
    assert result["message"]


@pytest.mark.asyncio
async def test_unparseable_returns_raw_executes_nothing(db, cache, source, monkeypatch):
    """PLAN §13.10: on unparseable LLM JSON, return raw text and execute nothing."""
    monkeypatch.setenv("LLM_MOCK", "false")  # take the real path...
    # ...but stub the LLM call to return garbage so nothing hits the network.
    monkeypatch.setattr(service, "_mock_enabled", lambda: False)

    def fake_complete(messages):
        return "I am not JSON at all { oops"

    import app.llm.client as client

    monkeypatch.setattr(client, "complete_chat", fake_complete)

    before_cash = repository.get_profile(db)["cash_balance"]
    result = await service.handle_chat(db, cache, source, "buy 5 AAPL")

    assert result["message"] == "I am not JSON at all { oops"
    assert result["raw"] == "I am not JSON at all { oops"
    assert result["actions"] == {"trades": [], "watchlist_changes": []}
    # nothing executed
    assert repository.get_position(db, "AAPL") is None
    assert repository.get_profile(db)["cash_balance"] == before_cash


@pytest.mark.asyncio
async def test_parsed_real_path_executes(db, cache, source, monkeypatch):
    """Real (non-mock) path with a valid JSON response auto-executes."""
    monkeypatch.setattr(service, "_mock_enabled", lambda: False)
    valid = ChatResponse(
        message="Buying 2 GOOGL",
        trades=[TradeAction(ticker="GOOGL", side="buy", quantity=2)],
    ).model_dump_json()

    import app.llm.client as client

    monkeypatch.setattr(client, "complete_chat", lambda messages: valid)

    result = await service.handle_chat(db, cache, source, "buy 2 GOOGL please")
    assert result["actions"]["trades"][0]["status"] == "executed"
    assert repository.get_position(db, "GOOGL")["quantity"] == 2
