"""Chat orchestration (PLAN §9): the full handle_chat flow.

Steps:
  1. persist the user message
  2. build context: portfolio (cash, positions+P&L), watchlist+live prices, last 20 msgs
  3. call the LLM (or the deterministic mock if LLM_MOCK=true) for structured output
  4. auto-execute trades + watchlist_changes, collecting per-action results/errors
  5. persist the assistant message with an actions JSON blob
  6. return {message, actions:{trades, watchlist_changes}}

On unparseable LLM JSON: return the raw text, execute nothing (PLAN §13.10).
"""

from __future__ import annotations

import asyncio
import os

from pydantic import ValidationError

from ..db import repository
from ..market.base import MarketSource
from ..market.cache import PriceCache
from ..services import portfolio as portfolio_service
from ..services import watchlist as watchlist_service
from .prompt import build_messages
from .schema import ChatResponse, TradeAction, WatchlistChange

HISTORY_LIMIT = 20  # PLAN §13.9


def _mock_enabled() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def _build_watchlist_context(db, cache: PriceCache, user_id: str) -> list[dict]:
    """Watchlist tickers annotated with their latest cache quote (price may be None)."""
    rows: list[dict] = []
    for ticker in repository.list_watchlist(db, user_id):
        quote = cache.get(ticker)
        rows.append(
            {
                "ticker": ticker,
                "price": quote.price if quote else None,
                "change_pct": quote.change_pct if quote else None,
            }
        )
    return rows


def _get_response(messages: list[dict], user_message: str) -> tuple[ChatResponse | None, str]:
    """Return (parsed ChatResponse | None, raw_text).

    Mock mode returns a deterministic parsed response. Real mode calls the LLM and
    parses; on a parse/validation failure it returns (None, raw) so the caller can
    surface the raw text and execute nothing (PLAN §13.10).
    """
    if _mock_enabled():
        from .mock import mock_response

        resp = mock_response(user_message)
        return resp, resp.model_dump_json()

    from .client import complete_chat

    raw = complete_chat(messages)
    try:
        return ChatResponse.model_validate_json(raw), raw
    except (ValidationError, ValueError):
        return None, raw


def _execute_actions(
    db,
    cache: PriceCache,
    source: MarketSource,
    response: ChatResponse,
    user_id: str,
) -> dict:
    """Auto-execute trades + watchlist changes, collecting per-action results.

    Each action is independent: a failure on one is recorded as an error and does
    not abort the others (PLAN §9 — failures are surfaced so the model/user sees them).
    """
    trade_results: list[dict] = []
    for trade in response.trades:
        trade_results.append(_execute_trade(db, cache, trade, user_id))

    watchlist_results: list[dict] = []
    for change in response.watchlist_changes:
        watchlist_results.append(_apply_watchlist_change(db, source, change, user_id))

    return {"trades": trade_results, "watchlist_changes": watchlist_results}


def _execute_trade(db, cache: PriceCache, trade: TradeAction, user_id: str) -> dict:
    base = {"ticker": trade.ticker, "side": trade.side, "quantity": trade.quantity}
    try:
        result = portfolio_service.execute_trade(
            db, cache, trade.ticker, trade.side, trade.quantity, user_id
        )
    except portfolio_service.TradeError as exc:
        return {**base, "status": "error", "error": str(exc)}
    return {
        **base,
        "status": "executed",
        "price": result["trade"]["price"],
        "cash_balance": result["cash_balance"],
    }


def _apply_watchlist_change(
    db, source: MarketSource, change: WatchlistChange, user_id: str
) -> dict:
    base = {"ticker": change.ticker, "action": change.action}
    try:
        if change.action == "add":
            watchlist_service.add_ticker(db, source, change.ticker, user_id)
        else:
            watchlist_service.remove_ticker(db, change.ticker, user_id)
    except watchlist_service.WatchlistError as exc:
        return {**base, "status": "error", "error": str(exc)}
    return {**base, "status": "applied"}


async def handle_chat(
    db,
    cache: PriceCache,
    source: MarketSource,
    user_message: str,
    user_id: str = "default",
) -> dict:
    """Full chat flow. See module docstring. Returns the API payload for /api/chat."""
    # 1. persist the user message.
    repository.insert_chat_message(db, "user", user_message, None, user_id)
    db.commit()

    # 2. build context. list_chat_messages already includes the message just
    #    persisted above; drop that trailing entry so build_messages appends the
    #    current user_message exactly once (no duplicate turn).
    portfolio = portfolio_service.build_portfolio(db, cache, user_id)
    watchlist = _build_watchlist_context(db, cache, user_id)
    history = repository.list_chat_messages(db, HISTORY_LIMIT + 1, user_id)
    if history and history[-1]["role"] == "user" and history[-1]["content"] == user_message:
        history = history[-(HISTORY_LIMIT + 1):-1]
    messages = build_messages(portfolio, watchlist, history, user_message)

    # 3. call the LLM (or mock). The LiteLLM call is synchronous; offload it so we
    #    never block the event loop. Mock + parsing are cheap and run inline.
    if _mock_enabled():
        response, raw = _get_response(messages, user_message)
    else:
        response, raw = await asyncio.to_thread(_get_response, messages, user_message)

    # 3b. Unparseable response: surface raw text, execute nothing (PLAN §13.10).
    if response is None:
        empty_actions = {"trades": [], "watchlist_changes": []}
        repository.insert_chat_message(db, "assistant", raw, empty_actions, user_id)
        db.commit()
        return {"message": raw, "actions": empty_actions, "raw": raw}

    # 4. auto-execute actions.
    actions = _execute_actions(db, cache, source, response, user_id)

    # 5. persist the assistant message with the actions JSON.
    repository.insert_chat_message(db, "assistant", response.message, actions, user_id)
    db.commit()

    # 6. return the API payload.
    return {"message": response.message, "actions": actions}
