"""LLM chat integration (PLAN §9).

Public surface:
- schema.ChatResponse — the structured-output contract {message, trades, watchlist_changes}
- service.handle_chat — the full chat orchestration entry point
"""

from .schema import ChatResponse, TradeAction, WatchlistChange
from .service import handle_chat

__all__ = ["ChatResponse", "TradeAction", "WatchlistChange", "handle_chat"]
