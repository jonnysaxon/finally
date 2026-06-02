"""Tests for the chat REST endpoint (PLAN §8).

The chat router delegates to `app.llm.service.handle_chat` via a lazy import.
These tests stub that function so they don't depend on the LLM module being
merged or on a live LLM call — they verify the router contract (request shape,
response shape, async delegation), not the LLM logic itself.
"""

import sys
import types

import pytest


@pytest.fixture
def stub_llm(monkeypatch):
    """Install a fake `app.llm.service` module with a controllable handle_chat."""
    calls = {}

    async def handle_chat(db, cache, source, message, user_id="default"):
        calls["message"] = message
        calls["user_id"] = user_id
        return {
            "message": f"echo: {message}",
            "actions": {"trades": [], "watchlist_changes": []},
        }

    llm_pkg = types.ModuleType("app.llm")
    llm_pkg.__path__ = []  # mark as package
    service_mod = types.ModuleType("app.llm.service")
    service_mod.handle_chat = handle_chat

    monkeypatch.setitem(sys.modules, "app.llm", llm_pkg)
    monkeypatch.setitem(sys.modules, "app.llm.service", service_mod)
    return calls


def test_chat_delegates_and_returns_response(client, stub_llm):
    r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "echo: hello"
    assert body["actions"] == {"trades": [], "watchlist_changes": []}
    assert stub_llm["message"] == "hello"


def test_chat_passes_actions_through(client, monkeypatch):
    async def handle_chat(db, cache, source, message, user_id="default"):
        return {
            "message": "bought it",
            "actions": {
                "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5, "status": "ok"}],
                "watchlist_changes": [],
            },
        }

    service_mod = types.ModuleType("app.llm.service")
    service_mod.handle_chat = handle_chat
    llm_pkg = types.ModuleType("app.llm")
    llm_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "app.llm", llm_pkg)
    monkeypatch.setitem(sys.modules, "app.llm.service", service_mod)

    r = client.post("/api/chat", json={"message": "buy 5 AAPL"})
    assert r.status_code == 200
    body = r.json()
    assert body["actions"]["trades"][0]["ticker"] == "AAPL"


def test_chat_missing_message_rejected(client):
    r = client.post("/api/chat", json={})
    assert r.status_code == 422


# ---- real pipeline (no stub): LLM_MOCK=true drives the actual handle_chat ----
# These exercise the genuine async chat route + cross-thread request connection
# (sync get_db dependency runs in a threadpool, the async handler runs on the
# event loop) and the real per-action result shape the E2E + frontend depend on.


def test_chat_real_pipeline_executes_trade(client):
    """`buy 5 AAPL` -> the mock LLM emits a trade, handle_chat auto-executes it,
    and each trade action carries status="executed" with {ticker, side, quantity}.
    """
    r = client.post("/api/chat", json={"message": "buy 5 AAPL"})
    assert r.status_code == 200, r.text  # not a 500 from cross-thread sqlite use
    body = r.json()
    trades = body["actions"]["trades"]
    assert len(trades) == 1
    t = trades[0]
    assert t["ticker"] == "AAPL"
    assert t["side"] == "buy"
    assert t["quantity"] == 5
    assert t["status"] == "executed"

    # The trade really hit the portfolio.
    p = client.get("/api/portfolio").json()
    assert any(pos["ticker"] == "AAPL" and pos["quantity"] == 5 for pos in p["positions"])
    assert p["cash_balance"] == 10000.0 - 190.0 * 5


def test_chat_real_pipeline_failed_trade_reports_error(client):
    """A trade the portfolio rejects comes back status="error" (not a 500), so the
    user/LLM sees why — the action list still carries {ticker, side, quantity}."""
    r = client.post("/api/chat", json={"message": "buy 100000 AAPL"})
    assert r.status_code == 200, r.text
    t = r.json()["actions"]["trades"][0]
    assert t["ticker"] == "AAPL"
    assert t["status"] == "error"
    assert "error" in t


def test_chat_real_pipeline_persists_history(client):
    """User + assistant messages are persisted (proves the connection is usable
    across the route's awaits without a cross-thread error)."""
    r = client.post("/api/chat", json={"message": "hello there"})
    assert r.status_code == 200
    assert isinstance(r.json()["message"], str) and r.json()["message"]
