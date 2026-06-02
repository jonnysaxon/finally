import { test, expect } from '@playwright/test';
import {
  sel,
  readCash,
  positionRow,
  readPositionQty,
  apiPrice,
  apiPortfolio,
  waitForStreamingPrice,
} from './helpers';

/**
 * PLAN §12 — Buy shares: cash decreases, position appears, portfolio updates.
 *
 * We don't assert an exact post-trade cash figure against a DOM-scraped price
 * (the price ticks continuously); instead we cross-check the UI against the
 * backend's own /api/portfolio state, which is the source of truth.
 */
const TICKER = 'AAPL';
const QTY = 2;

test.describe('Buy', () => {
  test('buying shares debits cash and creates a position', async ({
    page,
    request,
  }) => {
    await page.goto('/');
    await waitForStreamingPrice(page, TICKER);

    const cashBefore = await readCash(page);
    const before = await apiPortfolio(request);
    const qtyBefore =
      before.positions.find((p: any) => p.ticker === TICKER)?.quantity ?? 0;

    // Execute the buy via the trade bar.
    await page.locator(sel.tradeTicker).fill(TICKER);
    await page.locator(sel.tradeQty).fill(String(QTY));
    await page.locator(sel.tradeBuy).click();

    // Trade bar reports success ("Bought N SYM").
    await expect(page.locator(sel.tradeFeedback)).toContainText(
      `Bought ${QTY} ${TICKER}`,
      { timeout: 10_000 },
    );

    // Position row appears (or quantity increases) for the ticker.
    await expect(positionRow(page, TICKER)).toBeVisible({ timeout: 10_000 });
    await expect
      .poll(async () => readPositionQty(page, TICKER))
      .toBeCloseTo(qtyBefore + QTY, 4);

    // Cash decreased in the header.
    await expect.poll(async () => readCash(page)).toBeLessThan(cashBefore);

    // UI agrees with backend truth.
    const after = await apiPortfolio(request);
    expect(after.cash_balance).toBeLessThan(before.cash_balance);
    const pos = after.positions.find((p: any) => p.ticker === TICKER);
    expect(pos).toBeTruthy();
    expect(pos.quantity).toBeCloseTo(qtyBefore + QTY, 4);

    // The debit roughly matches qty * a recent price (sanity, not exact —
    // price moves between read and fill).
    const px = await apiPrice(request, TICKER);
    const expectedDebit = QTY * px;
    const actualDebit = before.cash_balance - after.cash_balance;
    expect(actualDebit).toBeGreaterThan(expectedDebit * 0.8);
    expect(actualDebit).toBeLessThan(expectedDebit * 1.2);
  });
});
