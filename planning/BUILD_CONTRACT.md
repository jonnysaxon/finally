# FinAlly Build Contract — Module Boundaries & Interfaces

This document is the shared contract for the team building the rest of FinAlly on
top of the completed market-data subsystem (`backend/app/market/`). It defines who
owns which files and the exact Python/HTTP interfaces between modules so work can
proceed in parallel without collisions.

**Authoritative sources:** `PLAN.md` (product spec), `MARKET_INTERFACE.md` (market
data API), `MARKET_DATA_SUMMARY.md` (what exists). This file only adds the
*new* cross-module contracts.

## File Ownership (do not edit files outside your area without coordinating)

| Owner | Owns |
|-------|------|
| **Database Engineer** | `backend/app/db/` (all of it), `backend/db/` schema SQL |
| **Backend API Engineer** | `backend/app/api/`, `backend/app/services/`, `backend/app/main.py`, `backend/app/static_files.py` |
| **LLM Engineer** | `backend/app/llm/` (all of it) |
| **Frontend Engineer** | `frontend/` (all of it) |
| **DevOps Engineer** | `Dockerfile`, `docker-compose.yml`, `scripts/`, `test/docker-compose.test.yml`, `.dockerignore` |
| **Integration Tester** | `test/` (Playwright specs, fixtures, config) |

`backend/app/market/` is DONE — read it, import it, do not modify it without raising it to the team lead.

## Python Module Interfaces

### Database (`backend/app/db/`) — owned by Database Engineer

Provides connection management + a repository layer. Everything else imports from here; nobody else writes raw SQL.

```python
# backend/app/db/database.py
def init_db() -> None: ...                 # lazy: create schema + seed if empty. Idempotent.
def get_connection() -> sqlite3.Connection: ...   # row_factory=sqlite3.Row, FK on
# FastAPI dependency:
def get_db() -> Iterator[sqlite3.Connection]: ...  # yields a connection per request

# backend/app/db/repository.py  (pure data access, no business rules)
# users_profile
def get_profile(db, user_id="default") -> dict: ...        # {id, cash_balance, created_at}
def update_cash(db, new_balance: float, user_id="default") -> None: ...
# watchlist
def list_watchlist(db, user_id="default") -> list[str]: ...      # ["AAPL", ...]
def add_watchlist(db, ticker: str, user_id="default") -> None: ...  # UNIQUE-safe (ignore dup)
def remove_watchlist(db, ticker: str, user_id="default") -> bool: ... # True if a row was removed
# positions
def list_positions(db, user_id="default") -> list[dict]: ...  # [{ticker, quantity, avg_cost, updated_at}]
def get_position(db, ticker, user_id="default") -> dict | None: ...
def upsert_position(db, ticker, quantity, avg_cost, user_id="default") -> None: ...
def delete_position(db, ticker, user_id="default") -> None: ...
# trades
def insert_trade(db, ticker, side, quantity, price, user_id="default") -> dict: ...  # returns full row
def list_trades(db, limit=100, user_id="default") -> list[dict]: ...
# portfolio_snapshots
def insert_snapshot(db, total_value: float, user_id="default") -> None: ...  # also prunes >7d (PLAN §13.8)
def list_snapshots(db, user_id="default") -> list[dict]: ...  # [{total_value, recorded_at}] ascending
# chat_messages
def insert_chat_message(db, role, content, actions=None, user_id="default") -> dict: ...  # actions: dict|None -> stored as JSON
def list_chat_messages(db, limit=20, user_id="default") -> list[dict]: ...  # ascending; actions parsed back to dict|None
```

Schema = PLAN §7 exactly. Seed = PLAN §7 default seed (cash 10000, 10 tickers). Timestamps ISO 8601 UTC strings. UUIDs via `uuid.uuid4()`.

### Portfolio service (`backend/app/services/portfolio.py`) — owned by Backend API Engineer

Business rules for trades + valuation. Used by BOTH the trade API endpoint AND the LLM auto-executor.

```python
class TradeError(Exception): ...   # message is user-safe (e.g. "Insufficient cash")

def execute_trade(db, cache, ticker: str, side: str, quantity: float, user_id="default") -> dict:
    """Validate + execute a market order at the current cache price. Atomic.
    - price = cache.get_price(ticker); error if no price.
    - buy: cost = price*qty; error if cost > cash. Update cash, weighted-avg cost (PLAN §13.6).
    - sell: error if qty > held (no shorting, PLAN §13.5). Reduce qty; delete row at 0 (PLAN §13.7).
      avg_cost unchanged on sell.
    - inserts a trade row, writes a fresh portfolio snapshot (PLAN §7).
    Returns {trade: {...}, position: {...}|None, cash_balance: float}.
    Raises TradeError on validation failure."""

def build_portfolio(db, cache, user_id="default") -> dict:
    """{cash_balance, total_value, positions:[{ticker, quantity, avg_cost, current_price,
       market_value, unrealized_pnl, pnl_pct}], positions_value}. current_price from cache."""

def compute_total_value(db, cache, user_id="default") -> float: ...  # cash + sum(positions market value)
```

### Watchlist service — owned by Backend API Engineer

```python
# backend/app/services/watchlist.py
class WatchlistError(Exception): ...
def add_ticker(db, source, ticker: str, user_id="default") -> None:
    """Validate against source.knows(ticker) (PLAN §13.11); WatchlistError if unknown. Then repository.add_watchlist."""
def remove_ticker(db, ticker: str, user_id="default") -> None: ...
```

### LLM (`backend/app/llm/`) — owned by LLM Engineer

```python
# backend/app/llm/service.py
async def handle_chat(db, cache, source, user_message: str, user_id="default") -> dict:
    """Full chat flow (PLAN §9):
    1. persist user message
    2. build context (cash, positions+P&L via services.portfolio.build_portfolio, watchlist+prices, last 20 msgs)
    3. call LLM (or mock if LLM_MOCK=true) requesting structured output {message, trades[], watchlist_changes[]}
    4. auto-execute trades via services.portfolio.execute_trade and watchlist_changes via services.watchlist;
       collect per-action results/errors
    5. persist assistant message with actions JSON
    6. return {message, actions:{trades:[...], watchlist_changes:[...]}, raw?:str}
    On unparseable LLM JSON: return raw text, execute nothing (PLAN §13.10)."""
```
LLM Engineer: use the **cerebras** skill for the LiteLLM→OpenRouter call. Model from `LLM_MODEL` env (default `openrouter/openai/gpt-oss-120b`). Honor `LLM_MOCK=true` with deterministic responses keyed off message content so E2E tests can assert (e.g. message containing "buy 5 AAPL" mock-executes that trade).

The LLM service imports `services.portfolio.execute_trade` / `services.watchlist.add_ticker` — coordinate with Backend API Engineer; those signatures above are the contract.

### main.py wiring — owned by Backend API Engineer

- Call `init_db()` on startup (lifespan), before the market source needs the watchlist.
- Replace `_placeholder_watchlist` with a real callback reading `repository.list_watchlist` from a connection.
- Mount routers: portfolio, watchlist, chat, plus existing stream router + `/api/health`.
- Background task: portfolio snapshot every 30s (PLAN §7/§13.8), runs always.
- Static file serving (PLAN §3/§11): serve the Next.js export from `app/static/` at `/`, with SPA fallback to `index.html`, mounted AFTER `/api/*` routes. Tolerate a missing static dir in dev.

## HTTP API Contract (frontend ↔ backend) — PLAN §8

All under same origin. Response shapes (Frontend Engineer builds against these):

- `GET /api/portfolio` → `{cash_balance, total_value, positions_value, positions:[{ticker, quantity, avg_cost, current_price, market_value, unrealized_pnl, pnl_pct}]}`
- `POST /api/portfolio/trade` body `{ticker, quantity, side}` → `200 {trade, position, cash_balance}` | `400 {detail}`
- `GET /api/portfolio/history` → `{snapshots:[{total_value, recorded_at}]}`
- `GET /api/watchlist` → `{tickers:[{ticker, price, prev_price, open_price, change, change_pct, direction}]}` (prices from cache; null price ok if not yet ticked)
- `POST /api/watchlist` body `{ticker}` → `200 {tickers:[...]}` (or `201`) | `400 {detail}`
- `DELETE /api/watchlist/{ticker}` → `200 {tickers:[...]}`
- `POST /api/chat` body `{message}` → `200 {message, actions:{trades, watchlist_changes}}`
- `GET /api/stream/prices` → SSE, event data JSON per `Quote.to_event()` (already built). Field names: see `backend/app/market/types.py`.
- `GET /api/health` → `{status:"ok"}`

Frontend: SSE via native `EventSource('/api/stream/prices')`. Sparklines + detail chart accumulate session-local from SSE (PLAN §13.12/13.13). "Change" not "Daily change" (PLAN §13.2). Next.js `output: 'export'`, Tailwind dark theme, colors: accent `#ecad0a`, blue `#209dd7`, purple `#753991`, bg `#0d1117`.

## Conventions

- Python: `uv` for everything (`cd backend && uv run pytest`, `uv run ruff check .`). Match existing style.
- Tests: each engineer writes pytest unit tests for their module under `backend/tests/<area>/`. Keep the existing 92 market tests green.
- Verify SQLite is accessed safely across async (snapshot task uses its own connection; never share a connection across threads).
- The `default` `user_id` is hardcoded everywhere (single-user).
</content>
</invoke>
