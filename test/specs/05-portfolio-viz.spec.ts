import { test, expect } from '@playwright/test';
import {
  sel,
  positionRow,
  heatmapTileSel,
  waitForStreamingPrice,
} from './helpers';

/**
 * PLAN §12 — Portfolio visualization:
 * heatmap renders with colored tiles, P&L chart has data points.
 *
 * Implementation specifics (verified against the frontend):
 *  - Heatmap is an <svg data-testid="heatmap-svg"> with per-position groups
 *    <g data-testid="heatmap-tile-${SYM}"> each containing a <rect fill=...>
 *    where fill is the P&L color. We assert the rect carries a color fill.
 *  - PnlChart renders its chart (data-testid="pnl-chart-canvas") only once it
 *    has >= 2 snapshots; with < 2 it shows a placeholder. Each trade writes a
 *    snapshot (PLAN §7), so we make TWO trades to guarantee >= 2 points.
 */
test.describe('Portfolio visualization', () => {
  test('heatmap renders colored tiles for positions', async ({ page }) => {
    await page.goto('/');
    await waitForStreamingPrice(page, 'AAPL');

    // Create two positions so the heatmap has multiple tiles.
    for (const [ticker, qty] of [
      ['AAPL', '3'],
      ['NVDA', '5'],
    ] as const) {
      await page.locator(sel.tradeTicker).fill(ticker);
      await page.locator(sel.tradeQty).fill(qty);
      await page.locator(sel.tradeBuy).click();
      await expect(positionRow(page, ticker)).toBeVisible({ timeout: 10_000 });
    }

    await expect(page.locator(sel.heatmapSvg)).toBeVisible({ timeout: 10_000 });

    // Each position should produce a tile <g>; its <rect> carries a P&L color.
    for (const ticker of ['AAPL', 'NVDA']) {
      const tile = page.locator(heatmapTileSel(ticker));
      await expect(tile, `heatmap tile for ${ticker}`).toBeVisible({
        timeout: 10_000,
      });
      const fill = await tile.locator('rect').first().getAttribute('fill');
      expect(fill, `${ticker} tile rect should have a color fill`).toBeTruthy();
      expect(fill).toMatch(/^#|rgb/i);
    }
  });

  test('P&L chart renders with data points after multiple snapshots', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForStreamingPrice(page, 'AAPL');

    // Two trades -> two snapshots -> PnlChart crosses its >=2-point threshold.
    for (const qty of ['1', '1']) {
      await page.locator(sel.tradeTicker).fill('AAPL');
      await page.locator(sel.tradeQty).fill(qty);
      await page.locator(sel.tradeBuy).click();
      await expect(positionRow(page, 'AAPL')).toBeVisible({ timeout: 10_000 });
      // Let the post-trade history refresh settle before the next trade.
      await page.waitForTimeout(300);
    }

    // The chart container (Panel) is always present; the rendered chart appears
    // once there are >= 2 snapshots.
    await expect(page.locator(sel.pnlPanel)).toBeVisible();
    await expect(page.locator(sel.pnlCanvas)).toBeVisible({ timeout: 15_000 });

    // Recharts draws an SVG with a path for the area series — proves points.
    await expect
      .poll(async () =>
        page.locator(sel.pnlCanvas).locator('svg path').count(),
      )
      .toBeGreaterThan(0);
  });

  test('P&L history endpoint returns snapshots', async ({ request }) => {
    const res = await request.get('/api/portfolio/history');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.snapshots)).toBeTruthy();
    expect(body.snapshots.length).toBeGreaterThanOrEqual(1);
    for (const s of body.snapshots) {
      expect(typeof s.total_value).toBe('number');
      expect(typeof s.recorded_at).toBe('string');
    }
  });
});
