import { test, expect } from '@playwright/test';
import {
  sel,
  readCash,
  positionRow,
  readPositionQty,
  apiPortfolio,
  waitForStreamingPrice,
} from './helpers';

/**
 * PLAN §12 — Sell shares: cash increases, position updates or disappears.
 *
 * Strategy: buy a known quantity to guarantee a position exists, then partial-
 * sell (position remains, qty drops, cash up) and full-sell (position row
 * disappears per PLAN §13.7).
 */
const TICKER = 'MSFT';

test.describe('Sell', () => {
  test('partial sell reduces quantity and credits cash', async ({
    page,
    request,
  }) => {
    await page.goto('/');
    await waitForStreamingPrice(page, TICKER);

    // Ensure we hold at least 4 shares to sell from.
    await page.locator(sel.tradeTicker).fill(TICKER);
    await page.locator(sel.tradeQty).fill('4');
    await page.locator(sel.tradeBuy).click();

    await expect(positionRow(page, TICKER)).toBeVisible({ timeout: 10_000 });
    await expect
      .poll(async () => readPositionQty(page, TICKER))
      .toBeGreaterThanOrEqual(4);

    const qtyBefore = await readPositionQty(page, TICKER);
    const cashBefore = await readCash(page);

    // Partial sell of 2.
    await page.locator(sel.tradeTicker).fill(TICKER);
    await page.locator(sel.tradeQty).fill('2');
    await page.locator(sel.tradeSell).click();

    // Trade bar reports success ("Sold 2 SYM").
    await expect(page.locator(sel.tradeFeedback)).toContainText(
      `Sold 2 ${TICKER}`,
      { timeout: 10_000 },
    );

    await expect
      .poll(async () => readPositionQty(page, TICKER))
      .toBeCloseTo(qtyBefore - 2, 4);
    await expect.poll(async () => readCash(page)).toBeGreaterThan(cashBefore);

    const after = await apiPortfolio(request);
    const pos = after.positions.find((p: any) => p.ticker === TICKER);
    expect(pos.quantity).toBeCloseTo(qtyBefore - 2, 4);
  });

  test('full sell removes the position row', async ({ page, request }) => {
    await page.goto('/');
    await waitForStreamingPrice(page, TICKER);

    // Read whatever we currently hold from the backend.
    const before = await apiPortfolio(request);
    const held =
      before.positions.find((p: any) => p.ticker === TICKER)?.quantity ?? 0;

    // Make sure we hold something, then sell exactly all of it.
    if (held <= 0) {
      await page.locator(sel.tradeTicker).fill(TICKER);
      await page.locator(sel.tradeQty).fill('3');
      await page.locator(sel.tradeBuy).click();
      await expect(positionRow(page, TICKER)).toBeVisible({ timeout: 10_000 });
    }

    const current = await apiPortfolio(request);
    const qty = current.positions.find(
      (p: any) => p.ticker === TICKER,
    )!.quantity;

    await page.locator(sel.tradeTicker).fill(TICKER);
    await page.locator(sel.tradeQty).fill(String(qty));
    await page.locator(sel.tradeSell).click();

    // Row disappears (PLAN §13.7: delete row at qty 0).
    await expect(positionRow(page, TICKER)).toHaveCount(0, { timeout: 10_000 });

    const after = await apiPortfolio(request);
    expect(after.positions.find((p: any) => p.ticker === TICKER)).toBeFalsy();
  });

  test('rejects selling more than held (no shorting)', async ({ request }) => {
    // Attempt to sell a huge quantity we don't own; backend rejects (PLAN §13.5).
    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: TICKER, quantity: 99999, side: 'sell' },
    });
    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(body.detail).toBeTruthy();
  });
});
