"""Tests for main.py wiring: health, route registration, static serving."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_files import mount_static


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_all_api_routes_registered(client):
    routes = {r.path for r in client.app.routes}
    assert "/api/health" in routes
    assert "/api/portfolio" in routes
    assert "/api/portfolio/trade" in routes
    assert "/api/portfolio/history" in routes
    assert "/api/watchlist" in routes
    assert "/api/stream/prices" in routes
    assert "/api/chat" in routes


# Note: there is intentionally no HTTP round-trip test against /api/stream/prices.
# It's an infinite SSE generator; consuming it through the sync TestClient hangs
# (the context manager blocks on __enter__ and never returns). Its registration is
# already asserted in test_all_api_routes_registered above, and the SSE wire format
# + disconnect handling are covered directly in tests/market/test_stream.py.


# ---- static serving (mount_static in isolation) ----------------------------


def test_missing_static_dir_dev_root(tmp_path):
    app = FastAPI()
    mount_static(app, static_dir=tmp_path / "does-not-exist")
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_static_dir_serves_index(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>FinAlly</body></html>")
    app = FastAPI()
    mount_static(app, static_dir=static_dir)
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "FinAlly" in r.text


def test_static_spa_fallback_to_index(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>SPA</body></html>")
    app = FastAPI()
    mount_static(app, static_dir=static_dir)
    with TestClient(app) as c:
        # An unknown client-side route should fall back to index.html.
        r = c.get("/some/spa/route")
        assert r.status_code == 200
        assert "SPA" in r.text
