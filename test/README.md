# FinAlly E2E Tests

Playwright end-to-end suite for the FinAlly AI trading workstation (PLAN §12).

## Recommended: one command (Docker)

On any Docker-capable host, run the whole stack (app + Playwright runner) with a
single command from the **repo root**:

```bash
docker compose -f test/docker-compose.test.yml up --build \
  --abort-on-container-exit --exit-code-from playwright
```

The `playwright` service's exit code is the suite result (0 = green). Tear down:

```bash
docker compose -f test/docker-compose.test.yml down -v
```

This starts the app with `LLM_MOCK=true` and the built-in simulator (no API
keys), on an ephemeral tmpfs DB so every run starts from clean seed data, and
points Playwright at `http://app:8000`. Browsers are preinstalled in the
`mcr.microsoft.com/playwright:v1.49.0-jammy` image — no CDN download needed.

## Prerequisites (when running locally instead of via compose)

The app must be built and running in **simulator mode** with the **mock LLM**:

```bash
LLM_MOCK=true            # deterministic chat responses
# MASSIVE_API_KEY unset  -> built-in market simulator (fixed 10-ticker universe)
```

**IMPORTANT — fresh DB per run.** The suite executes real trades and watchlist
edits against the single shared "default" user, so it MUST start from a
freshly-seeded `db/finally.db` (cash == $10,000, the 10 default tickers). The
fresh-start spec asserts the $10k balance, and the buy/chat specs assume enough
cash — a DB left dirty by a previous run will fail those. Reset before each run:

```bash
rm -f db/finally.db   # repo-root db/ in dev (NOT backend/db/); re-seeds on next request
```

In dev the backend writes the SQLite file to the **repo-root `db/finally.db`**
(see `_db_path()` — `FINALLY_DB_PATH` overrides it; the container uses
`/app/db`). The compose path guarantees a clean seed via tmpfs `/app/db` every
run. The suite mutates shared single-user state, so it runs serially
(`workers: 1`).

## Running locally

Install once:

```bash
cd test
npm install
npm run install:browsers   # downloads the bundled chromium
```

Against a locally-running app (default `http://localhost:8000`):

```bash
npm test
```

Override the base URL (e.g. another port/host):

```bash
BASE_URL=http://localhost:8000 npm test
```

### If `playwright install` is blocked (corporate TLS / no CDN access)

Set `PW_CHANNEL=chrome` to drive a locally-installed Google Chrome instead of
the bundled chromium download:

```bash
PW_CHANNEL=chrome npm test
```

## Scenarios (one spec file each)

| File | PLAN §12 scenario |
|------|-------------------|
| `00-api-smoke.spec.ts` | HTTP contract gate (health, watchlist, portfolio, history, validation) |
| `01-fresh-start.spec.ts` | default 10-ticker watchlist, $10k cash, prices streaming, connected status |
| `02-watchlist.spec.ts` | add + remove a ticker; unknown-ticker rejection (sim universe) |
| `03-buy.spec.ts` | buy → cash down, position appears, portfolio updates |
| `04-sell.spec.ts` | partial sell, full sell removes row, no-shorting rejection |
| `05-portfolio-viz.spec.ts` | heatmap colored tiles, P&L chart has data points |
| `06-ai-chat.spec.ts` | mocked chat: send msg → response → inline trade execution |
| `07-sse-resilience.spec.ts` | SSE drop → reconnect → prices resume |

**Status: 25/25 passing** against a live backend (simulator + `LLM_MOCK=true`,
fresh DB). Verified locally with system Chrome:

```bash
# 1) boot the backend on a fresh DB (LLM_MOCK + simulator)
rm -f db/finally.db                  # repo-root db/, not backend/db/
cd backend && LLM_MOCK=true uvicorn app.main:app --host 127.0.0.1 --port 8000
# 2) run the suite against it
cd test && PW_CHANNEL=chrome npx playwright test
```

## Selectors & contracts

All DOM lookups go through `specs/helpers.ts` (`sel` + per-symbol selector
builders), keyed on the `data-testid` attributes the Frontend Engineer ships
(verified against `frontend/src/components/*`). Notable conventions:

- Per-row/message elements use a suffixed testid: `watchlist-row-AAPL`,
  `watchlist-remove-AAPL`, `position-row-AAPL`, `heatmap-tile-AAPL`,
  `chat-msg-user` / `chat-msg-assistant`.
- The connection dot exposes `data-state` ∈ `connecting | connected |
  disconnected` (`connection-status`).
- The P&L chart (`pnl-chart-canvas`) renders only with ≥ 2 snapshots; the
  viz spec makes two trades to cross that threshold.

Mock-chat triggers are verified against `backend/app/llm/mock.py`:
`buy 5 AAPL` auto-executes a buy (inline `chat-actions` chip + portfolio
update); `hello` returns a message with no actions.
