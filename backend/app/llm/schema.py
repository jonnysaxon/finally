"""Structured-output schema for the chat LLM (PLAN §9).

The model is asked to return JSON matching `ChatResponse`. Structured Outputs
(via LiteLLM `response_format`) constrains generation to this shape; we still
validate defensively on parse and fall back to raw text on failure (PLAN §13.10).
"""

from typing import Literal

from pydantic import BaseModel, Field


class TradeAction(BaseModel):
    """One trade the model wants auto-executed."""

    ticker: str = Field(description="Ticker symbol, e.g. AAPL")
    side: Literal["buy", "sell"] = Field(description="Trade side")
    quantity: float = Field(description="Number of shares (fractional allowed), > 0")


class WatchlistChange(BaseModel):
    """One watchlist modification the model wants applied."""

    ticker: str = Field(description="Ticker symbol, e.g. PYPL")
    action: Literal["add", "remove"] = Field(description="Add or remove from the watchlist")


class ChatResponse(BaseModel):
    """The complete structured response the assistant returns.

    `message` is the conversational text shown to the user. `trades` and
    `watchlist_changes` are optional action lists that get auto-executed
    (PLAN §9 auto-execution).
    """

    message: str = Field(description="Conversational reply shown to the user")
    trades: list[TradeAction] = Field(
        default_factory=list, description="Trades to auto-execute (may be empty)"
    )
    watchlist_changes: list[WatchlistChange] = Field(
        default_factory=list, description="Watchlist changes to apply (may be empty)"
    )
