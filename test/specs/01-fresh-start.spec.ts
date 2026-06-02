import { test, expect } from '@playwright/test';
import {
  sel,
  DEFAULT_TICKERS,
  STARTING_CASH,
  readCash,
  watchlistRow,
  waitForStreamingPrice,
} from './helpers';

/**
 * PLAN §12 — Fresh start:
 * default 10-ticker watchlist appears, $10k balance shown, prices are streaming.
 *
 * Assumes a freshly-seeded DB (cash == $10,000). The compose path (DevOps) uses
 * an ephemeral tmpfs DB so this holds; run against a clean db/finally.db locally.
 */
test.describe('Fresh start', () => {
  test('loads the trading workstation', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator(sel.watchlist)).toBeVisible();
  });

  test('shows the default 10-ticker watchlist', async ({ page }) => {
    await page.goto('/');
    for (const ticker of DEFAULT_TICKERS) {
      await expect(
        watchlistRow(page, ticker),
        `watchlist should contain ${ticker}`,
      ).toBeVisible({ timeout: 15_000 });
    }
  });

  test('shows the starting cash balance of $10,000', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator(sel.cash)).toBeVisible();
    await expect
      .poll(async () => readCash(page), { timeout: 10_000 })
      .toBeCloseTo(STARTING_CASH, 2);
  });

  test('shows a portfolio total value', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator(sel.totalValue)).toBeVisible();
    // With no positions, total value == cash. Allow the first portfolio fetch
    // to populate the header.
    await expect
      .poll(async () => {
        const txt = await page.locator(sel.totalValue).first().textContent();
        return txt && /\d/.test(txt);
      })
      .toBeTruthy();
  });

  test('streams live prices into the watchlist', async ({ page }) => {
    await page.goto('/');
    await waitForStreamingPrice(page, 'AAPL');
  });

  test('shows a connected SSE status indicator', async ({ page }) => {
    await page.goto('/');
    const dot = page.locator(sel.connectionStatus);
    await expect(dot).toBeVisible();
    await expect(dot).toHaveAttribute('data-state', 'connected', {
      timeout: 15_000,
    });
  });
});
