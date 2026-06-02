"""Pure data access for FinAlly (no business rules).

Everything outside `app/db/` imports from here; nobody else writes raw SQL
(BUILD_CONTRACT.md). Functions take an open `sqlite3.Connection` as their first
argument and leave transaction control (commit) to the caller — except where a
returned row must reflect a write, in which case the row is read back within the
same connection before returning.

Conventions: timestamps are ISO-8601 UTC strings, ids are `uuid.uuid4()` hex,
`user_id` defaults to "default" (single-user).
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

_SNAPSHOT_RETENTION_DAYS = 7  # PLAN.md §13.8


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# --- users_profile -------------------------------------------------------------


def get_profile(db: sqlite3.Connection, user_id: str = "default") -> dict:
    """{id, cash_balance, created_at} for the user."""
    row = db.execute(
        "SELECT id, cash_balance, created_at FROM users_profile WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else {}


def update_cash(db: sqlite3.Connection, new_balance: float, user_id: str = "default") -> None:
    db.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (new_balance, user_id),
    )


# --- watchlist -----------------------------------------------------------------


def list_watchlist(db: sqlite3.Connection, user_id: str = "default") -> list[str]:
    """Tickers in insertion order, e.g. ["AAPL", ...]."""
    rows = db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker",
        (user_id,),
    ).fetchall()
    return [r["ticker"] for r in rows]


def add_watchlist(db: sqlite3.Connection, ticker: str, user_id: str = "default") -> None:
    """Add a ticker; a duplicate (UNIQUE on user_id, ticker) is silently ignored."""
    db.execute(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, ticker.upper(), _utc_now()),
    )


def remove_watchlist(db: sqlite3.Connection, ticker: str, user_id: str = "default") -> bool:
    """Remove a ticker; returns True if a row was actually deleted."""
    cur = db.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker.upper()),
    )
    return cur.rowcount > 0


# --- positions -----------------------------------------------------------------


def list_positions(db: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    """[{ticker, quantity, avg_cost, updated_at}], ordered by ticker."""
    rows = db.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_position(db: sqlite3.Connection, ticker: str, user_id: str = "default") -> dict | None:
    row = db.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? AND ticker = ?",
        (user_id, ticker.upper()),
    ).fetchone()
    return dict(row) if row else None


def upsert_position(
    db: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = "default",
) -> None:
    """Insert or update a position (one row per ticker per user)."""
    db.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (_new_id(), user_id, ticker.upper(), quantity, avg_cost, _utc_now()),
    )


def delete_position(db: sqlite3.Connection, ticker: str, user_id: str = "default") -> None:
    db.execute(
        "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker.upper()),
    )


# --- trades --------------------------------------------------------------------


def insert_trade(
    db: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = "default",
) -> dict:
    """Append a trade to the log; returns the full inserted row."""
    trade_id = _new_id()
    executed_at = _utc_now()
    db.execute(
        """
        INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (trade_id, user_id, ticker.upper(), side, quantity, price, executed_at),
    )
    return {
        "id": trade_id,
        "user_id": user_id,
        "ticker": ticker.upper(),
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": executed_at,
    }


def list_trades(db: sqlite3.Connection, limit: int = 100, user_id: str = "default") -> list[dict]:
    """Most recent `limit` trades, newest first."""
    rows = db.execute(
        "SELECT id, user_id, ticker, side, quantity, price, executed_at FROM trades "
        "WHERE user_id = ? ORDER BY executed_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --- portfolio_snapshots -------------------------------------------------------


def insert_snapshot(
    db: sqlite3.Connection, total_value: float, user_id: str = "default"
) -> None:
    """Record a portfolio value snapshot and prune rows older than 7 days.

    Prune-on-insert keeps the table bounded with no separate cleanup job
    (PLAN.md §13.8).
    """
    now = datetime.now(UTC)
    db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, total_value, now.isoformat()),
    )
    cutoff = (now - timedelta(days=_SNAPSHOT_RETENTION_DAYS)).isoformat()
    db.execute(
        "DELETE FROM portfolio_snapshots WHERE user_id = ? AND recorded_at < ?",
        (user_id, cutoff),
    )


def list_snapshots(db: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    """[{total_value, recorded_at}] ascending by time (for the P&L chart)."""
    rows = db.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots "
        "WHERE user_id = ? ORDER BY recorded_at ASC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- chat_messages -------------------------------------------------------------


def insert_chat_message(
    db: sqlite3.Connection,
    role: str,
    content: str,
    actions: dict | None = None,
    user_id: str = "default",
) -> dict:
    """Persist a chat message; `actions` (dict|None) is stored as JSON.

    Returns the full row with `actions` as the original dict|None.
    """
    msg_id = _new_id()
    created_at = _utc_now()
    actions_json = json.dumps(actions) if actions is not None else None
    db.execute(
        """
        INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (msg_id, user_id, role, content, actions_json, created_at),
    )
    return {
        "id": msg_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": created_at,
    }


def list_chat_messages(
    db: sqlite3.Connection, limit: int = 20, user_id: str = "default"
) -> list[dict]:
    """Most recent `limit` messages, returned ascending; `actions` parsed back to dict|None."""
    rows = db.execute(
        """
        SELECT id, user_id, role, content, actions, created_at FROM (
            SELECT id, user_id, role, content, actions, created_at
            FROM chat_messages
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ) ORDER BY created_at ASC, id ASC
        """,
        (user_id, limit),
    ).fetchall()
    result = []
    for r in rows:
        msg = dict(r)
        msg["actions"] = json.loads(msg["actions"]) if msg["actions"] is not None else None
        result.append(msg)
    return result
