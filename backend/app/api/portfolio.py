"""Portfolio REST endpoints (PLAN §8)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db import repository
from ..db.database import get_db
from ..services import portfolio as portfolio_service
from .schemas import (
    HistoryResponse,
    PortfolioOut,
    TradeRequest,
    TradeResponse,
)


def create_portfolio_router() -> APIRouter:
    router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

    @router.get("", response_model=PortfolioOut)
    def get_portfolio(request: Request, db: sqlite3.Connection = Depends(get_db)):
        cache = request.app.state.cache
        return portfolio_service.build_portfolio(db, cache)

    @router.post("/trade", response_model=TradeResponse)
    def trade(body: TradeRequest, request: Request, db: sqlite3.Connection = Depends(get_db)):
        cache = request.app.state.cache
        try:
            return portfolio_service.execute_trade(
                db, cache, body.ticker, body.side, body.quantity
            )
        except portfolio_service.TradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/history", response_model=HistoryResponse)
    def history(db: sqlite3.Connection = Depends(get_db)):
        return {"snapshots": repository.list_snapshots(db)}

    return router
