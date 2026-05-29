# Massive API (formerly Polygon.io)

Reference for retrieving real-time and end-of-day US stock prices for multiple
tickers. Massive is the rebrand of Polygon.io (announced 30 Oct 2025); existing
API keys, account, and the `api.polygon.io` host continue to work unchanged.

This document covers only what FinAlly needs: **fetching the latest price for a
set of watched tickers on a polling interval**, plus the end-of-day endpoints we
may use for a session-open baseline.

---

## 1. Authentication & Base URL

- **Base URL:** `https://api.polygon.io`
- **Two equivalent auth methods:**
  - Header (preferred): `Authorization: Bearer <MASSIVE_API_KEY>`
  - Query param: `?apiKey=<MASSIVE_API_KEY>`

```bash
# Header auth
curl -H "Authorization: Bearer $MASSIVE_API_KEY" \
  "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT"

# Query-param auth (equivalent)
curl "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT&apiKey=$MASSIVE_API_KEY"
```

## 2. Rate Limits & Data Recency

| Tier | Requests / min | Data recency |
|------|----------------|--------------|
| Free | **5** | 15-minute delayed |
| Starter / Developer | higher | 15-minute delayed |
| Advanced / Business | unlimited | real-time |

FinAlly targets the **free tier** as the baseline: at 5 req/min we poll **one
snapshot request every ~15 seconds** for the union of all watched tickers. A
single snapshot request returns every ticker we ask for, so one request per poll
covers the whole watchlist regardless of size. Paid tiers can poll faster (2-15s)
by changing one interval constant.

---

## 3. Endpoints We Use

### 3.1 Full Market Snapshot (PRIMARY — multi-ticker latest price)

The core endpoint for FinAlly. Returns latest price + day OHLC + previous close
for a comma-separated list of tickers in **one request**.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `tickers` | comma-separated string | No | e.g. `AAPL,TSLA,NVDA`. Case-sensitive. Omit to return all ~10k tickers (avoid — large). |
| `include_otc` | boolean | No | Include OTC securities. Default `false`. |

**Response:**

```json
{
  "status": "OK",
  "count": 1,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": -0.124,
      "todaysChangePerc": -0.601,
      "updated": 1605192894630916600,
      "day":     { "o": 20.64, "h": 20.64, "l": 20.50, "c": 20.50, "v": 37216, "vw": 20.61 },
      "prevDay": { "o": 20.79, "h": 21.0,  "l": 20.50, "c": 20.63, "v": 292738, "vw": 20.69 },
      "lastTrade": { "p": 20.506, "s": 2416, "t": 1605192894630916600, "x": 4, "c": [14, 41] },
      "lastQuote": { "p": 20.50, "P": 20.60, "s": 13, "S": 22, "t": 1605192959994246100 },
      "min": { "t": 1684428600000, "o": 20.50, "h": 20.50, "l": 20.50, "c": 20.50, "v": 5000, "vw": 20.51 }
    }
  ]
}
```

**Field guide (what FinAlly reads):**

| Path | Meaning | FinAlly use |
|------|---------|-------------|
| `lastTrade.p` | Last trade price | **The "current price"** we push over SSE |
| `lastTrade.t` | Last trade timestamp (nanoseconds) | Convert to epoch seconds for our tick |
| `day.c` | Today's close-so-far | Fallback if `lastTrade` missing (pre-market) |
| `prevDay.c` | Previous day's close | Useful only as a real "daily change" baseline |
| `todaysChange` / `todaysChangePerc` | Change vs. previous close | Not used (FinAlly uses session-open baseline — see PLAN §13.2) |

> Important: a ticker can be absent from `tickers[]` if it has no data yet
> (e.g. before market open). Always guard against missing keys.

### 3.2 Single Ticker Snapshot

Same shape as one element of the array above. Rarely needed — the full snapshot
already batches everything — but useful for validating a symbol on watchlist-add.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}
```

### 3.3 Daily Market Summary (end-of-day OHLC, all tickers)

One request returns EOD OHLCV for **every** US stock on a given date. Useful for
seeding a session-open baseline at startup (the prior trading day's close) or for
offline analysis.

```
GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true
```

| Param | Notes |
|-------|-------|
| `date` (path) | `YYYY-MM-DD` trading date |
| `adjusted` | Split-adjusted prices. Default `true`. |

**Response:**

```json
{
  "status": "OK",
  "resultsCount": 9543,
  "results": [
    { "T": "AAPL", "o": 189.3, "h": 191.0, "l": 188.5, "c": 190.4, "v": 51234000, "vw": 189.9, "t": 1699000000000, "n": 480000 }
  ]
}
```

`T` = ticker, `o/h/l/c` = OHLC, `v` = volume, `vw` = VWAP, `t` = epoch ms, `n` = trade count.

### 3.4 Previous Close (single ticker)

```
GET /v2/aggs/ticker/{ticker}/prev?adjusted=true
```

Returns the previous trading day's OHLCV for one ticker. Handy for a real
prior-close baseline without pulling the whole market summary.

---

## 4. Official Python Client

Massive ships an official client. Install with `uv`:

```bash
uv add massive
```

```python
from massive import RESTClient

client = RESTClient(api_key="<MASSIVE_API_KEY>")  # reads no env var implicitly

# Multi-ticker latest price (PRIMARY path)
snapshots = client.get_snapshot_all(
    market_type="stocks",
    tickers=["AAPL", "MSFT", "NVDA"],
)
for s in snapshots:
    # s.ticker, s.last_trade.price, s.day.close, s.prev_day.close, s.todays_change_percent
    print(s.ticker, s.last_trade.price)

# Single ticker (validation on watchlist-add)
one = client.get_snapshot_ticker(market_type="stocks", ticker="AAPL")

# End-of-day OHLC for the whole market on a date
bars = client.get_grouped_daily_aggs(date="2026-05-29", adjusted=True)

# Previous close for one ticker
prev = client.get_previous_close_agg(ticker="AAPL", adjusted=True)
```

Relevant method signatures:

| Method | Key params |
|--------|-----------|
| `get_snapshot_all` | `market_type`, `tickers`, `include_otc` |
| `get_snapshot_ticker` | `market_type`, `ticker` |
| `get_grouped_daily_aggs` | `date`, `adjusted`, `include_otc` |
| `get_previous_close_agg` | `ticker`, `adjusted` |
| `get_daily_open_close_agg` | `ticker`, `date`, `adjusted` |

> The client is **synchronous** and uses `urllib3` under the hood. In FinAlly's
> async backend, run polling calls in a thread (`asyncio.to_thread(...)`) or use
> a plain `httpx.AsyncClient` against the REST endpoints directly to avoid
> blocking the event loop. See MARKET_INTERFACE.md §4.2.

---

## 5. FinAlly Polling Strategy (summary)

1. Maintain the union of watched tickers (the watchlist).
2. Every ~15s (free tier), call the **Full Market Snapshot** with that ticker list
   — one request, all prices.
3. For each returned ticker, read `lastTrade.p` (fall back to `day.c`) and the
   trade timestamp, and write `(ticker, price, timestamp)` into the shared price
   cache (PLAN §6 "single source of truth").
4. SSE readers push from the cache; emit only on actual change (PLAN §13.3).
5. On error / rate-limit (HTTP 429), back off and retry next interval; keep the
   last good cache value.

Detailed implementation lives in **MARKET_INTERFACE.md**.

---

## Sources

- [Stocks REST API — Overview (Massive)](https://massive.com/docs/rest/stocks/overview)
- [REST API Quickstart (Massive)](https://massive.com/docs/rest/quickstart)
- [Full Market Snapshot — Stocks (Massive)](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)
- [Daily Market Summary / Grouped Daily (Massive)](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary)
- [Request limit for Massive's RESTful APIs](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis)
- [Official Python client (massive-com/client-python)](https://github.com/massive-com/client-python)
