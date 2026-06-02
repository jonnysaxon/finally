import sqlite3

from app.db import database


def test_init_db_creates_all_tables(db):
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    expected = {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }
    assert expected.issubset(names)


def test_init_db_seeds_default_profile(db):
    row = db.execute("SELECT cash_balance FROM users_profile WHERE id='default'").fetchone()
    assert row is not None
    assert row["cash_balance"] == 10000.0


def test_init_db_seeds_ten_default_tickers(db):
    rows = db.execute("SELECT ticker FROM watchlist WHERE user_id='default'").fetchall()
    tickers = {r["ticker"] for r in rows}
    assert tickers == {
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    }


def test_init_db_is_idempotent(db_path):
    database.init_db()
    database.init_db()
    conn = database.get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM watchlist").fetchone()["n"]
        profiles = conn.execute("SELECT COUNT(*) AS n FROM users_profile").fetchone()["n"]
    finally:
        conn.close()
    assert count == 10
    assert profiles == 1


def test_get_connection_uses_row_factory(db):
    row = db.execute("SELECT id FROM users_profile WHERE id='default'").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["id"] == "default"


def test_get_connection_enforces_foreign_keys(db):
    fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_get_db_dependency_yields_and_closes(db_path):
    gen = database.get_db()
    conn = next(gen)
    assert conn.execute("SELECT 1").fetchone()[0] == 1
    # exhausting the generator commits and closes the connection
    try:
        next(gen)
    except StopIteration:
        pass
    # connection should now be closed
    try:
        conn.execute("SELECT 1")
        closed = False
    except sqlite3.ProgrammingError:
        closed = True
    assert closed


def test_db_file_created_on_disk(db_path):
    database.init_db()
    assert db_path.exists()
