import { test, expect } from '@playwright/test';
import { sel, readWatchlistPrice, waitForStreamingPrice } from './helpers';

/**
 * PLAN §12 — SSE resilience: disconnect and verify reconnection.
 *
 * Mechanism note (important): an ALREADY-OPEN EventSource cannot be torn down
 * from the client by page.route(...).abort() OR context.setOffline(true) OR
 * even CDP Network.emulateNetworkConditions{offline} — Chromium's network
 * emulation/route interception only affects NEW requests, while the long-lived
 * SSE response stays open (server keepalive holds it). Verified empirically.
 *
 * So we force a real disconnect by blocking ONLY the stream route, then
 * reloading: the page document + assets still load, but the freshly-created
 * EventSource hits the aborted route and fails immediately → the store's
 * onerror flips the status off "connected" (to "connecting"/"disconnected").
 * Unblocking lets EventSource's native retry reconnect → "connected", and we
 * confirm prices resume. This exercises the exact reconnect path PLAN §12 wants.
 *
 * Why CONTEXT.route, not page.route: page-level routes are re-armed only after
 * the reload navigation commits, leaving a race where the first post-reload
 * EventSource request can slip through and connect before the handler is
 * active (→ status legitimately reads "connected" and the assertion flakes,
 * ~1/8). context.route stays armed across the navigation, so the very first
 * post-reload stream request is reliably aborted.
 *
 * Status indicator exposes data-state ∈ {connecting, connected, disconnected}.
 */
test.describe('SSE resilience', () => {
  test('reconnects after a transient stream drop', async ({ page }) => {
    await page.goto('/');

    const dot = page.locator(sel.connectionStatus);
    await expect(dot).toHaveAttribute('data-state', 'connected', {
      timeout: 15_000,
    });
    await waitForStreamingPrice(page, 'AAPL');

    // Block ONLY the SSE stream at the CONTEXT level so the handler survives the
    // reload navigation (page.route would re-arm too late — see header note).
    await page.context().route('**/api/stream/prices', (route) => route.abort());
    // Reload so a fresh EventSource is created and immediately fails the abort.
    // Wait for the new document to commit so the stale pre-reload "connected"
    // DOM is gone before we assert.
    await page.reload({ waitUntil: 'domcontentloaded' });

    // Status stays off "connected" — every stream attempt is aborted while the
    // route is armed (becomes "connecting"/"disconnected").
    await expect(dot).not.toHaveAttribute('data-state', 'connected', {
      timeout: 20_000,
    });

    // Restore the stream; EventSource auto-reconnects on its next retry.
    await page.context().unroute('**/api/stream/prices');

    await expect(dot).toHaveAttribute('data-state', 'connected', {
      timeout: 30_000,
    });

    // Prices resume after reconnect: the value changes (simulator ticks).
    await waitForStreamingPrice(page, 'AAPL');
    const first = await readWatchlistPrice(page, 'AAPL');
    await expect
      .poll(async () => readWatchlistPrice(page, 'AAPL'), {
        timeout: 20_000,
        message: 'price should change after reconnect',
      })
      .not.toBe(first);
  });
});
