"""Pydantic request/response models for the FinAlly REST API (PLAN §8).

These mirror the HTTP contract in BUILD_CONTRACT.md exactly — the Frontend
Engineer builds against these shapes. Service-layer dicts are mapped onto these
models in the routers.
"""

from typing import Literal

from pydantic import BaseModel, field_validator

# --- Portfolio ---------------------------------------------------------------


class PositionOut(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    market_value: float
    unrealized_pnl: float
    pnl_pct: float


class PortfolioOut(BaseModel):
    cash_balance: float
    total_value: float
    positions_value: float
    positions: list[PositionOut]


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: Literal["buy", "sell"]

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("quantity")
    @classmethod
    def _positive_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be greater than zero")
        return v


class TradeOut(BaseModel):
    id: str
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str


class TradeResponse(BaseModel):
    trade: TradeOut
    position: PositionOut | None
    cash_balance: float


class SnapshotOut(BaseModel):
    total_value: float
    recorded_at: str


class HistoryResponse(BaseModel):
    snapshots: list[SnapshotOut]


# --- Watchlist ---------------------------------------------------------------


class WatchlistTickerOut(BaseModel):
    ticker: str
    price: float | None
    prev_price: float | None
    open_price: float | None
    change: float | None
    change_pct: float | None
    direction: str | None


class WatchlistResponse(BaseModel):
    tickers: list[WatchlistTickerOut]


class WatchlistAddRequest(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


# --- Chat --------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str


class ChatActions(BaseModel):
    trades: list[dict] = []
    watchlist_changes: list[dict] = []


class ChatResponse(BaseModel):
    message: str
    actions: ChatActions
    raw: str | None = None
