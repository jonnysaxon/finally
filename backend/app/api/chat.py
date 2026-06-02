"""Chat REST endpoint (PLAN §8, §9).

Delegates the full chat flow to the LLM service (owned by the LLM Engineer). The
import is lazy so the backend still boots and serves the other routes even if the
LLM module isn't present yet.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db.database import get_db
from .schemas import ChatRequest, ChatResponse


def create_chat_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.post("", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request, db: sqlite3.Connection = Depends(get_db)):
        try:
            from ..llm import service as llm_service
        except ImportError as exc:  # LLM module not wired in yet
            raise HTTPException(status_code=503, detail="Chat is not available") from exc

        cache = request.app.state.cache
        source = request.app.state.source
        return await llm_service.handle_chat(db, cache, source, body.message)

    return router
