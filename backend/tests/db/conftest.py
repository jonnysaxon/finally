import sqlite3

import pytest

from app.db import database


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Point the database at a throwaway file via the FINALLY_DB_PATH override."""
    path = tmp_path / "finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    return path


@pytest.fixture
def db(db_path) -> sqlite3.Connection:
    """An initialized (schema + seed) connection on a temp database."""
    database.init_db()
    conn = database.get_connection()
    yield conn
    conn.close()
