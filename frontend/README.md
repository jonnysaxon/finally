# FinAlly — Frontend

Next.js + TypeScript + Tailwind trading workstation, built as a **static export**
(`output: 'export'`) and served by the FastAPI backend at `/`. Talks to the
backend over same-origin `/api/*` (REST) and `/api/stream/prices` (SSE via native
`EventSource`). No CORS, no env config.

## Commands

```bash
npm install
npm run build      # → static export in ./out  (this is what Docker copies)
npm run dev        # local dev server on :3000 (proxy /api to the backend)
npm test           # vitest unit tests
npx tsc --noEmit   # type check
```

**Build output dir:** `frontend/out/` (contains `index.html`, `404.html`,
`_next/`). DevOps copies this into the image's static dir.

## Architecture

- `src/hooks/useTerminalStore.tsx` — the single store: owns the SSE connection +
  connection status, latest quote per ticker, session-local price buffers
  (sparkline + detail chart, PLAN §13.12/13.13), watchlist, portfolio, P&L
  history, selected ticker, and the chat thread. All mutations route through it.
- `src/lib/api.ts` — same-origin REST client (typed against BUILD_CONTRACT §8).
- `src/lib/priceBuffer.ts` — rolling per-ticker history fed by SSE.
- `src/lib/heatmap.ts` — squarified treemap layout + P&L→color (pure, tested).
- `src/lib/format.ts` — tabular price/money/pct/qty formatters.
- `src/components/*` — Header, Watchlist, DetailChart, Heatmap, PnlChart,
  PositionsTable, TradeBar, ChatPanel, ErrorToast, Panel/Sparkline primitives.

The whole workstation is client-only (`dynamic(..., { ssr: false })`) because it
uses `EventSource` + Recharts; the export still emits a valid `index.html` shell.

## Stable E2E selectors (`data-testid`)

| Testid | Element |
|--------|---------|
| `header`, `header-total-value`, `header-cash`, `connection-status` | header; `connection-status` has `data-state="connecting\|connected\|disconnected"` |
| `watchlist`, `watchlist-rows`, `watchlist-add-input`, `watchlist-add-btn` | watchlist panel + add control |
| `watchlist-row-{SYM}` | one per row (also carries `data-ticker="{SYM}"` and `data-selected="true\|false"`); contains `watchlist-price` and a `watchlist-remove-{SYM}` control (the ✕ is shown on row hover) |
| `detail-chart`, `detail-chart-canvas` | main chart (canvas present once ≥2 ticks buffered) |
| `heatmap`, `heatmap-svg`, `heatmap-tile-{SYM}` | portfolio treemap; each tile also carries `data-ticker="{SYM}"` and an inner `<rect fill>` colored by P&L |
| `pnl-chart`, `pnl-chart-canvas` | P&L line chart (canvas needs ≥2 snapshots) |
| `positions`, `positions-table`, `position-row-{SYM}` | positions table; row cells are positional — `td[1]`=Qty, `td[2]`=AvgCost, `td[3]`=Price (also tagged `position-quantity`/`position-avg-cost`/`position-current-price`/`position-pnl`) |
| `trade-bar`, `trade-ticker`, `trade-qty`, `trade-est`, `trade-buy`, `trade-sell`, `trade-feedback` | trade bar |
| `chat-panel`, `chat-toggle`/`chat-collapse`, `chat-history`, `chat-input`, `chat-send`, `chat-typing`, `chat-msg-user`/`chat-msg-assistant`, `chat-actions` (container; individual chips also tagged `chat-action`) | AI copilot |
| `error-toast` | transient error banner |

`{SYM}` is the uppercased ticker. Each component mounts exactly once, so every
testid is unique in the DOM (the layout reflows responsively without duplicating
components).

`scripts/mockserver.mjs` is a throwaway stub backend (static files + `/api/*`
stubs + SSE) used only for local visual checks — not shipped.
