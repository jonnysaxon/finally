"""Watchlist REST endpoints (PLAN §8).

Responses carry live prices from the cache. A ticker that hasn't ticked yet
reports null price fields (PLAN: "null price ok if not yet ticked").
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db import repository
from ..db.database import get_db
from ..market.cache import PriceCache
from ..services import watchlist as watchlist_service
from .schemas import WatchlistAddRequest, WatchlistResponse


def _watchlist_payload(db: sqlite3.Connection, cache: PriceCache) -> dict:
    """Build the {tickers:[...]} response, joining the stored watchlist with
    the latest cached quote for each symbol."""
    tickers = []
    for ticker in repository.list_watchlist(db):
        quote = cache.get(ticker)
        if quote is None:
            tickers.append(
                {
                    "ticker": ticker,
                    "price": None,
                    "prev_price": None,
                    "open_price": None,
                    "change": None,
                    "change_pct": None,
                    "direction": None,
                }
            )
        else:
            tickers.append(
                {
                    "ticker": ticker,
                    "price": round(quote.price, 4),
                    "prev_price": round(quote.prev_price, 4),
                    "open_price": round(quote.open_price, 4),
                    "change": round(quote.change, 4),
                    "change_pct": round(quote.change_pct, 6),
                    "direction": quote.direction,
                }
            )
    return {"tickers": tickers}


def create_watchlist_router() -> APIRouter:
    router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

    @router.get("", response_model=WatchlistResponse)
    def get_watchlist(request: Request, db: sqlite3.Connection = Depends(get_db)):
        return _watchlist_payload(db, request.app.state.cache)

    @router.post("", response_model=WatchlistResponse)
    def add(body: WatchlistAddRequest, request: Request, db: sqlite3.Connection = Depends(get_db)):
        source = request.app.state.source
        try:
            watchlist_service.add_ticker(db, source, body.ticker)
        except watchlist_service.WatchlistError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _watchlist_payload(db, request.app.state.cache)

    @router.delete("/{ticker}", response_model=WatchlistResponse)
    def remove(ticker: str, request: Request, db: sqlite3.Connection = Depends(get_db)):
        watchlist_service.remove_ticker(db, ticker)
        return _watchlist_payload(db, request.app.state.cache)

    return router
