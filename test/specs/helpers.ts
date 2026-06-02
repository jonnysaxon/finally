import { Page, Locator, expect, APIRequestContext } from '@playwright/test';

/**
 * Centralized selectors and helpers for the FinAlly E2E suite.
 *
 * Selectors mirror the data-testid attributes the Frontend Engineer actually
 * ships (verified against frontend/src/components/*). Per-row / per-message
 * elements use a `${testid}-${SYMBOL|role}` suffix convention rather than a
 * generic testid + data-attribute.
 */
export const sel = {
  // Header (Header.tsx)
  cash: '[data-testid="header-cash"]',
  totalValue: '[data-testid="header-total-value"]',
  connectionStatus: '[data-testid="connection-status"]', // has data-state

  // Watchlist (Watchlist.tsx)
  watchlist: '[data-testid="watchlist"]',
  watchlistRows: '[data-testid="watchlist-rows"]',
  watchlistAddInput: '[data-testid="watchlist-add-input"]',
  watchlistAddBtn: '[data-testid="watchlist-add-btn"]',

  // Trade bar (TradeBar.tsx)
  tradeBar: '[data-testid="trade-bar"]',
  tradeTicker: '[data-testid="trade-ticker"]',
  tradeQty: '[data-testid="trade-qty"]',
  tradeBuy: '[data-testid="trade-buy"]',
  tradeSell: '[data-testid="trade-sell"]',
  tradeFeedback: '[data-testid="trade-feedback"]',

  // Positions (PositionsTable.tsx) — rows carry per-cell testids
  positionsTable: '[data-testid="positions-table"]',
  positionQuantity: '[data-testid="position-quantity"]',
  positionAvgCost: '[data-testid="position-avg-cost"]',
  positionCurrentPrice: '[data-testid="position-current-price"]',
  positionPnl: '[data-testid="position-pnl"]',
  watchlistPrice: '[data-testid="watchlist-price"]',

  // Heatmap (Heatmap.tsx)
  heatmapPanel: '[data-testid="heatmap"]',
  heatmapSvg: '[data-testid="heatmap-svg"]',

  // P&L chart (PnlChart.tsx)
  pnlPanel: '[data-testid="pnl-chart"]',
  pnlCanvas: '[data-testid="pnl-chart-canvas"]', // only rendered with >=2 snapshots

  // Chat (ChatPanel.tsx)
  chatPanel: '[data-testid="chat-panel"]',
  chatToggle: '[data-testid="chat-toggle"]', // shown only when collapsed
  chatHistory: '[data-testid="chat-history"]',
  chatInput: '[data-testid="chat-input"]',
  chatSend: '[data-testid="chat-send"]',
  chatMsgUser: '[data-testid="chat-msg-user"]',
  chatMsgAssistant: '[data-testid="chat-msg-assistant"]',
  chatActions: '[data-testid="chat-actions"]', // per-message action chip container
} as const;

export const DEFAULT_TICKERS = [
  'AAPL',
  'GOOGL',
  'MSFT',
  'AMZN',
  'TSLA',
  'NVDA',
  'META',
  'JPM',
  'V',
  'NFLX',
] as const;

export const STARTING_CASH = 10000.0;

/** Per-symbol element selectors. */
export const watchlistRowSel = (sym: string) =>
  `[data-testid="watchlist-row-${sym.toUpperCase()}"]`;
export const watchlistRemoveSel = (sym: string) =>
  `[data-testid="watchlist-remove-${sym.toUpperCase()}"]`;
export const positionRowSel = (sym: string) =>
  `[data-testid="position-row-${sym.toUpperCase()}"]`;
export const heatmapTileSel = (sym: string) =>
  `[data-testid="heatmap-tile-${sym.toUpperCase()}"]`;

export function watchlistRow(page: Page, ticker: string): Locator {
  return page.locator(watchlistRowSel(ticker));
}
export function positionRow(page: Page, ticker: string): Locator {
  return page.locator(positionRowSel(ticker));
}

/** Parse a numeric value out of text that may contain $, commas, %, spaces. */
export function parseNumber(text: string | null | undefined): number {
  if (!text) return NaN;
  const cleaned = text.replace(/[^0-9.+\-]/g, '');
  return parseFloat(cleaned);
}

/** Read the cash balance shown in the header as a number. */
export async function readCash(page: Page): Promise<number> {
  return parseNumber(await page.locator(sel.cash).first().textContent());
}

/** Read the "Last" price cell text for a watchlist row (data-testid=watchlist-price). */
async function watchlistPriceText(
  page: Page,
  ticker: string,
): Promise<string | null> {
  return watchlistRow(page, ticker).locator(sel.watchlistPrice).textContent();
}

/**
 * Wait until a watchlist row shows a non-empty, positive price — proving the
 * SSE stream delivered at least one tick (sim ticks ~500ms).
 */
export async function waitForStreamingPrice(page: Page, ticker = 'AAPL') {
  await expect(watchlistRow(page, ticker)).toBeVisible({ timeout: 15_000 });
  await expect
    .poll(
      async () => {
        const n = parseNumber(await watchlistPriceText(page, ticker));
        return Number.isFinite(n) && n > 0;
      },
      { timeout: 15_000, message: `expected ${ticker} to show a streaming price` },
    )
    .toBe(true);
}

/** Read the current displayed watchlist price for a ticker. */
export async function readWatchlistPrice(
  page: Page,
  ticker: string,
): Promise<number> {
  return parseNumber(await watchlistPriceText(page, ticker));
}

/**
 * Position-table rows carry per-cell testids (position-quantity,
 * position-avg-cost, position-current-price, position-pnl), scoped within the
 * row for the given ticker.
 */
export async function readPositionQty(
  page: Page,
  ticker: string,
): Promise<number> {
  return parseNumber(
    await positionRow(page, ticker).locator(sel.positionQuantity).textContent(),
  );
}

/**
 * Open the chat panel if it's collapsed. The panel renders only `chat-toggle`
 * when collapsed; clicking it reveals `chat-panel` with the input.
 */
export async function ensureChatOpen(page: Page) {
  if (await page.locator(sel.chatPanel).count()) return;
  const toggle = page.locator(sel.chatToggle);
  if (await toggle.count()) {
    await toggle.click();
  }
  await expect(page.locator(sel.chatPanel)).toBeVisible({ timeout: 10_000 });
}

/** Send a chat message (opens the panel first if needed). */
export async function sendChat(page: Page, msg: string) {
  await ensureChatOpen(page);
  await page.locator(sel.chatInput).fill(msg);
  await page.locator(sel.chatSend).click();
}

// --- Backend API helpers (source of truth, immune to UI timing) -------------

export async function apiPrice(
  request: APIRequestContext,
  ticker: string,
): Promise<number> {
  const res = await request.get('/api/watchlist');
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  const row = body.tickers.find(
    (t: { ticker: string }) => t.ticker === ticker,
  );
  expect(row, `ticker ${ticker} present in /api/watchlist`).toBeTruthy();
  return row.price as number;
}

export async function apiPortfolio(request: APIRequestContext) {
  const res = await request.get('/api/portfolio');
  expect(res.ok()).toBeTruthy();
  return res.json();
}
