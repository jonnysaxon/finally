"""Tests for the watchlist REST endpoints (PLAN §8, §13.11)."""

DEFAULT_TICKERS = {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"}


def test_get_watchlist_returns_seeded_tickers_with_prices(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    tickers = r.json()["tickers"]
    symbols = {t["ticker"] for t in tickers}
    assert symbols == DEFAULT_TICKERS
    aapl = next(t for t in tickers if t["ticker"] == "AAPL")
    assert aapl["price"] == 190.0
    assert aapl["direction"] in ("up", "down", "flat")


def test_add_known_ticker(client):
    r = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert r.status_code == 200
    symbols = {t["ticker"] for t in r.json()["tickers"]}
    assert "PYPL" in symbols


def test_add_unknown_ticker_returns_400(client):
    r = client.post("/api/watchlist", json={"ticker": "ZZZZ"})
    assert r.status_code == 400
    assert "Unknown ticker" in r.json()["detail"]


def test_add_lowercase_is_normalized(client):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 200
    symbols = {t["ticker"] for t in r.json()["tickers"]}
    assert "PYPL" in symbols


def test_remove_ticker(client):
    r = client.delete("/api/watchlist/AAPL")
    assert r.status_code == 200
    symbols = {t["ticker"] for t in r.json()["tickers"]}
    assert "AAPL" not in symbols


def test_remove_lowercase(client):
    r = client.delete("/api/watchlist/aapl")
    assert r.status_code == 200
    symbols = {t["ticker"] for t in r.json()["tickers"]}
    assert "AAPL" not in symbols
