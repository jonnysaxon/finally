"""Tests for the portfolio REST endpoints (PLAN §8)."""


def test_get_portfolio_fresh(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["cash_balance"] == 10000.0
    assert body["total_value"] == 10000.0
    assert body["positions_value"] == 0.0
    assert body["positions"] == []


def test_buy_updates_portfolio(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["side"] == "buy"
    assert body["position"]["quantity"] == 10
    assert body["cash_balance"] == 10000.0 - 190.0 * 10

    # Reflected in GET /api/portfolio.
    p = client.get("/api/portfolio").json()
    assert p["positions"][0]["ticker"] == "AAPL"
    assert p["cash_balance"] == 10000.0 - 1900.0


def test_sell_after_buy(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "sell"})
    assert r.status_code == 200
    assert r.json()["position"] is None
    p = client.get("/api/portfolio").json()
    assert p["positions"] == []
    assert p["cash_balance"] == 10000.0


def test_buy_insufficient_cash_returns_400(client):
    r = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1000, "side": "buy"}
    )
    assert r.status_code == 400
    assert "Insufficient cash" in r.json()["detail"]


def test_sell_more_than_held_returns_400(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "sell"})
    assert r.status_code == 400
    assert "shorting" in r.json()["detail"]


def test_trade_zero_quantity_rejected(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0, "side": "buy"})
    assert r.status_code == 422  # pydantic validation


def test_trade_bad_side_rejected(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "hold"})
    assert r.status_code == 422


def test_history_has_snapshot_after_trade(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "buy"})
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    snaps = r.json()["snapshots"]
    assert len(snaps) >= 1
    assert "total_value" in snaps[0]
    assert "recorded_at" in snaps[0]
