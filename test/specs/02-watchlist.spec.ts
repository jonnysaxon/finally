import { test, expect } from '@playwright/test';
import { sel, watchlistRow, watchlistRemoveSel } from './helpers';

/**
 * PLAN §12 — Add and remove a ticker from the watchlist.
 *
 * Constraint (simulator mode): the data source universe is fixed to the 10
 * seeded tickers, so we cannot add a brand-new symbol — the backend rejects
 * unknown tickers (PLAN §13.11). We therefore exercise add+remove against a
 * default ticker (NFLX): remove it, confirm it's gone, re-add it, confirm it's
 * back. This leaves the watchlist in its original state for other specs.
 *
 * The remove control (✕) is hidden until the row is hovered (group-hover), so
 * we hover the row before clicking it.
 */
const TICKER = 'NFLX';

test.describe('Watchlist add/remove', () => {
  test('removes a ticker then re-adds it', async ({ page }) => {
    await page.goto('/');

    const row = watchlistRow(page, TICKER);
    await expect(row, `${TICKER} should start on the watchlist`).toBeVisible({
      timeout: 15_000,
    });

    // Reveal and click the remove control.
    await row.hover();
    const remove = page.locator(watchlistRemoveSel(TICKER));
    await remove.click();
    await expect(row, `${TICKER} should disappear after removal`).toHaveCount(0);

    // Re-add via the add-ticker input.
    await page.locator(sel.watchlistAddInput).fill(TICKER);
    await page.locator(sel.watchlistAddBtn).click();

    await expect(
      watchlistRow(page, TICKER),
      `${TICKER} should reappear after re-adding`,
    ).toBeVisible({ timeout: 10_000 });
  });

  test('rejects an unknown ticker in simulator mode', async ({ page }) => {
    await page.goto('/');
    await expect(watchlistRow(page, 'AAPL')).toBeVisible({ timeout: 15_000 });

    const rows = page.locator(
      `${sel.watchlistRows} [data-testid^="watchlist-row-"]`,
    );
    const countBefore = await rows.count();

    // ZZZZ is not in the simulator universe -> backend returns 400; the store
    // surfaces an error and must not add a row.
    await page.locator(sel.watchlistAddInput).fill('ZZZZ');
    await page.locator(sel.watchlistAddBtn).click();

    await expect.poll(async () => rows.count()).toBe(countBefore);
    await expect(watchlistRow(page, 'ZZZZ')).toHaveCount(0);
  });
});
