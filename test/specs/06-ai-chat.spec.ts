import { test, expect } from '@playwright/test';
import {
  sel,
  positionRow,
  readPositionQty,
  apiPortfolio,
  sendChat,
  ensureChatOpen,
} from './helpers';

/**
 * PLAN §12 — AI chat (mocked, LLM_MOCK=true):
 * send a message, receive a response, trade execution appears inline.
 *
 * Mock-trigger contract — confirmed by the LLM Engineer + backend/app/llm/mock.py:
 *   - "buy 5 AAPL" -> actions.trades[0] =
 *     {ticker:"AAPL", side:"buy", quantity:5, status:"executed", price, cash_balance};
 *     exact assistant reply "[mock] Executing: buy 5 AAPL." (match "Executing:",
 *     NOT "Bought" — that's the trade-bar phrasing).
 *   - "hello" -> no actions; exact reply
 *     "[mock] FinAlly here. I received your message but found no actions to take.".
 *
 * The frontend renders executed actions as chips inside a per-message
 * container data-testid="chat-actions"; a buy chip reads like "✓ buy 5 AAPL".
 */
const BUY_MSG = 'buy 5 AAPL';
const GREETING = 'hello';

test.describe('AI chat (mocked)', () => {
  test('greeting returns a response with no actions', async ({ page }) => {
    await page.goto('/');
    await sendChat(page, GREETING);

    // User message rendered.
    await expect(page.locator(sel.chatMsgUser).last()).toContainText(GREETING, {
      timeout: 10_000,
    });

    // Assistant reply rendered. Exact mock no-action reply is
    // "[mock] FinAlly here. I received your message but found no actions to take."
    const assistant = page.locator(sel.chatMsgAssistant).last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });
    await expect(assistant).toContainText('found no actions to take', {
      timeout: 15_000,
    });

    // No inline action chips for a plain greeting.
    await expect(assistant.locator(sel.chatActions)).toHaveCount(0);
  });

  test('"buy 5 AAPL" executes a trade shown inline and updates portfolio', async ({
    page,
    request,
  }) => {
    await page.goto('/');
    await ensureChatOpen(page);

    const before = await apiPortfolio(request);
    const qtyBefore =
      before.positions.find((p: any) => p.ticker === 'AAPL')?.quantity ?? 0;

    await sendChat(page, BUY_MSG);

    // User message + assistant reply appear.
    await expect(page.locator(sel.chatMsgUser).last()).toContainText('AAPL', {
      timeout: 10_000,
    });
    const assistant = page.locator(sel.chatMsgAssistant).last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });
    // Exact mock reply is "[mock] Executing: buy 5 AAPL." — match the stable
    // "Executing:" prefix (NOT "Bought", which is the trade-bar phrasing).
    await expect(assistant).toContainText('Executing:', { timeout: 15_000 });

    // Inline action chip for the executed trade.
    const actions = assistant.locator(sel.chatActions);
    await expect(actions).toBeVisible({ timeout: 15_000 });
    await expect(actions).toContainText('AAPL');

    // Position reflects +5 AAPL.
    await expect(positionRow(page, 'AAPL')).toBeVisible({ timeout: 10_000 });
    await expect
      .poll(async () => readPositionQty(page, 'AAPL'))
      .toBeCloseTo(qtyBefore + 5, 4);

    // Backend truth confirms the auto-executed trade.
    const after = await apiPortfolio(request);
    const pos = after.positions.find((p: any) => p.ticker === 'AAPL');
    expect(pos.quantity).toBeCloseTo(qtyBefore + 5, 4);
    expect(after.cash_balance).toBeLessThan(before.cash_balance);
  });

  test('chat API returns the structured response shape', async ({ request }) => {
    const res = await request.post('/api/chat', { data: { message: GREETING } });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(typeof body.message).toBe('string');
    expect(body.actions).toBeTruthy();
    expect(Array.isArray(body.actions.trades)).toBeTruthy();
    expect(Array.isArray(body.actions.watchlist_changes)).toBeTruthy();
    // Greeting triggers no actions.
    expect(body.actions.trades).toHaveLength(0);
    expect(body.actions.watchlist_changes).toHaveLength(0);
  });

  test('chat API auto-executes a buy with status "executed"', async ({
    request,
  }) => {
    // Per the LLM mock contract, each executed trade result carries
    // status:"executed" (or "error" with an error string).
    const res = await request.post('/api/chat', { data: { message: BUY_MSG } });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.actions.trades.length).toBeGreaterThanOrEqual(1);
    const trade = body.actions.trades[0];
    expect(trade.ticker).toBe('AAPL');
    expect(trade.side).toBe('buy');
    expect(trade.quantity).toBe(5);
    expect(trade.status).toBe('executed');
  });
});
