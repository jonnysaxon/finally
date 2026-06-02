import { test, expect } from '@playwright/test';

/**
 * Backend API smoke checks (PLAN §8 / BUILD_CONTRACT HTTP contract).
 *
 * These run first (00- prefix) as a fast gate: if the API contract is broken,
 * the UI specs will fail in confusing ways, so surface contract issues here.
 */
test.describe('API smoke', () => {
  test('health endpoint is ok', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('ok');
  });

  test('watchlist endpoint returns priced tickers', async ({ request }) => {
    const res = await request.get('/api/watchlist');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.tickers)).toBeTruthy();
    expect(body.tickers.length).toBeGreaterThan(0);
    const row = body.tickers[0];
    for (const field of [
      'ticker',
      'price',
      'prev_price',
      'open_price',
      'change',
      'change_pct',
      'direction',
    ]) {
      expect(row, `watchlist row should have ${field}`).toHaveProperty(field);
    }
  });

  test('portfolio endpoint returns the expected shape', async ({ request }) => {
    const res = await request.get('/api/portfolio');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    for (const field of [
      'cash_balance',
      'total_value',
      'positions_value',
      'positions',
    ]) {
      expect(body).toHaveProperty(field);
    }
    expect(Array.isArray(body.positions)).toBeTruthy();
  });

  test('history endpoint returns a snapshots array', async ({ request }) => {
    const res = await request.get('/api/portfolio/history');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.snapshots)).toBeTruthy();
  });

  test('trade with insufficient cash is rejected', async ({ request }) => {
    // Buying an absurd quantity must exceed $10k and return 400.
    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'AAPL', quantity: 1000000, side: 'buy' },
    });
    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(body.detail).toBeTruthy();
  });
});
