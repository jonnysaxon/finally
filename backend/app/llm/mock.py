"""Deterministic mock LLM (PLAN §9 LLM Mock Mode).

Active when `LLM_MOCK=true`. Returns a canned `ChatResponse` keyed off the
user's message text so E2E tests can assert exact behavior without a network
call. Triggers are intentionally simple and documented here so the
integration-tester can rely on them.

Trigger contract (case-insensitive substring match, evaluated in order):
  - "buy <N> <TICKER>"            -> trades=[{TICKER, buy, N}]
  - "sell <N> <TICKER>"           -> trades=[{TICKER, sell, N}]
  - "add <TICKER>" / "watch <TICKER>"   -> watchlist_changes=[{TICKER, add}]
  - "remove <TICKER>" / "unwatch <TICKER>" -> watchlist_changes=[{TICKER, remove}]
  - anything else                 -> message only, no actions

`<N>` is an integer or decimal; `<TICKER>` is 1-5 uppercase letters. The verbs
above are matched as whole words. Multiple verbs in one message each fire.
"""

from __future__ import annotations

import re

from .schema import ChatResponse, TradeAction, WatchlistChange

_BUY_RE = re.compile(r"\bbuy\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,5})\b", re.IGNORECASE)
_SELL_RE = re.compile(r"\bsell\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,5})\b", re.IGNORECASE)
_ADD_RE = re.compile(r"\b(?:add|watch)\s+([A-Za-z]{1,5})\b", re.IGNORECASE)
_REMOVE_RE = re.compile(r"\b(?:remove|unwatch)\s+([A-Za-z]{1,5})\b", re.IGNORECASE)


def mock_response(user_message: str) -> ChatResponse:
    """Build a deterministic ChatResponse from the message text."""
    trades: list[TradeAction] = []
    watchlist_changes: list[WatchlistChange] = []

    for qty, ticker in _BUY_RE.findall(user_message):
        trades.append(TradeAction(ticker=ticker.upper(), side="buy", quantity=float(qty)))
    for qty, ticker in _SELL_RE.findall(user_message):
        trades.append(TradeAction(ticker=ticker.upper(), side="sell", quantity=float(qty)))

    # Skip the trade verbs' ticker so "buy 5 AAPL" doesn't also "add AAPL".
    traded_tickers = {t.ticker for t in trades}
    for ticker in _ADD_RE.findall(user_message):
        if ticker.upper() not in traded_tickers:
            watchlist_changes.append(WatchlistChange(ticker=ticker.upper(), action="add"))
    for ticker in _REMOVE_RE.findall(user_message):
        watchlist_changes.append(WatchlistChange(ticker=ticker.upper(), action="remove"))

    message = _summarize(user_message, trades, watchlist_changes)
    return ChatResponse(message=message, trades=trades, watchlist_changes=watchlist_changes)


def _summarize(
    user_message: str,
    trades: list[TradeAction],
    watchlist_changes: list[WatchlistChange],
) -> str:
    parts: list[str] = []
    for t in trades:
        parts.append(f"{t.side} {t.quantity:g} {t.ticker}")
    for w in watchlist_changes:
        verb = "Added" if w.action == "add" else "Removed"
        parts.append(f"{verb.lower()} {w.ticker} {'to' if w.action == 'add' else 'from'} watchlist")
    if parts:
        return "[mock] Executing: " + "; ".join(parts) + "."
    return "[mock] FinAlly here. I received your message but found no actions to take."
