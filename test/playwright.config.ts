import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the FinAlly E2E suite (PLAN §12).
 *
 * Target URL resolution:
 *   - BASE_URL env wins (used by docker-compose.test.yml to point at the
 *     in-compose app service, e.g. http://app:8000).
 *   - Defaults to http://localhost:8000 for a locally-running app.
 *
 * Tests assume the app runs with LLM_MOCK=true and simulator market data
 * (no MASSIVE_API_KEY) so chat responses and the ticker universe are
 * deterministic.
 *
 * Browser:
 *   - CI / docker-compose uses the prebuilt Playwright image, which ships the
 *     bundled chromium — the default.
 *   - On hosts where `playwright install` is blocked (e.g. corporate TLS
 *     interception on the browser CDN), set PW_CHANNEL=chrome to drive the
 *     locally-installed Google Chrome instead of a bundled browser.
 */
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8000';
const PW_CHANNEL = process.env.PW_CHANNEL; // e.g. "chrome" | "msedge"

export default defineConfig({
  testDir: './specs',
  // The portfolio mutates shared single-user state (one SQLite DB, one
  // "default" user), so trade/watchlist specs must not race each other.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }]]
    : [['list']],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Video recording needs ffmpeg, which ships with the bundled chromium (CI /
    // docker image) but NOT with a system browser channel. On the PW_CHANNEL
    // path (e.g. system Chrome) ffmpeg isn't available, so disable video there
    // to avoid a newPage failure; keep it for the default bundled-browser path.
    video: PW_CHANNEL ? 'off' : 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // When PW_CHANNEL is set, use that installed browser channel (e.g.
        // system Google Chrome) instead of the bundled chromium download.
        ...(PW_CHANNEL ? { channel: PW_CHANNEL } : {}),
      },
    },
  ],
});
