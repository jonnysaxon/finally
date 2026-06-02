"""Connection management and lazy initialization for the SQLite database.

The backend never sets up the DB out of band: the first call to `init_db()`
(or any connection that triggers it) creates the schema and seeds defaults if
the file is missing or empty (PLAN.md §7). This keeps "delete the file to start
fresh" working with no migration step.
"""

import os
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

# Schema lives in backend/db/schema.sql (this file is backend/app/db/database.py).
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"

# Default seed (PLAN.md §7).
_DEFAULT_USER_ID = "default"
_DEFAULT_CASH = 10000.0
_DEFAULT_WATCHLIST = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def _db_path() -> Path:
    """Resolve the SQLite file path.

    `FINALLY_DB_PATH` overrides everything (tests point it at a tmp file). In the
    container the bind mount is `/app/db`; in dev we fall back to the repo's
    top-level `db/` directory (PLAN.md §3/§11).
    """
    override = os.environ.get("FINALLY_DB_PATH", "").strip()
    if override:
        return Path(override)

    container_dir = Path("/app/db")
    if container_dir.is_dir():
        return container_dir / "finally.db"

    # Dev: repo db/ dir (backend/app/db/database.py -> repo root is parents[3]).
    repo_db_dir = Path(__file__).resolve().parents[3] / "db"
    return repo_db_dir / "finally.db"


def _utc_now() -> str:
    """Current time as an ISO-8601 UTC string (PLAN.md §7)."""
    return datetime.now(UTC).isoformat()


def get_connection() -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced.

    Each caller owns its connection (BUILD_CONTRACT.md). Triggers a lazy
    `init_db()` on first use.

    check_same_thread=False: FastAPI runs the sync get_db dependency in a
    threadpool worker, but an `async def` handler then uses that connection on
    the event-loop thread. Access stays serialized per request (one connection,
    sequential awaits) and the snapshot loop uses its own connection, so a
    connection is never used concurrently from two threads — disabling the
    same-thread guard is the standard, safe FastAPI + SQLite pattern here.
    """
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _is_initialized(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users_profile'"
    ).fetchone()
    if row is None:
        return False
    seeded = conn.execute("SELECT 1 FROM users_profile LIMIT 1").fetchone()
    return seeded is not None


def init_db() -> None:
    """Create the schema and seed defaults if the database is empty. Idempotent."""
    conn = get_connection()
    try:
        if _is_initialized(conn):
            return
        conn.executescript(_SCHEMA_PATH.read_text())
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    """Insert the default user profile and watchlist (PLAN.md §7)."""
    now = _utc_now()
    conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (_DEFAULT_USER_ID, _DEFAULT_CASH, now),
    )
    for ticker in _DEFAULT_WATCHLIST:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), _DEFAULT_USER_ID, ticker, now),
        )


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yield a per-request connection, ensuring init.

    The connection is committed on clean exit and always closed.
    """
    init_db()
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
