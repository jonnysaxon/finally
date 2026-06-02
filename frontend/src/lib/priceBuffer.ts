// Session-local rolling price history per ticker (PLAN §13.12 / §13.13).
//
// One buffer per ticker, fed by the SSE stream. The sparkline reads a short
// tail; the detail chart reads the whole buffer. Empty on load, fills in
// progressively — no history endpoint, no persistence across reload/restart.

export interface PricePoint {
  t: number; // epoch seconds
  p: number; // price
}

const MAX_POINTS = 500; // ~PLAN §13.13 "last 500 ticks"

export class PriceBuffer {
  private buffers = new Map<string, PricePoint[]>();

  push(ticker: string, price: number, t: number): void {
    const key = ticker.toUpperCase();
    let buf = this.buffers.get(key);
    if (!buf) {
      buf = [];
      this.buffers.set(key, buf);
    }
    // Drop duplicate-timestamp/no-op repeats to keep the line meaningful.
    const last = buf[buf.length - 1];
    if (last && last.t === t && last.p === price) return;
    buf.push({ t, p: price });
    if (buf.length > MAX_POINTS) buf.shift();
  }

  /** Full buffer for the detail chart. */
  series(ticker: string): PricePoint[] {
    return this.buffers.get(ticker.toUpperCase()) ?? [];
  }

  /** Short tail (last `n`) for sparklines. */
  tail(ticker: string, n = 40): number[] {
    const buf = this.buffers.get(ticker.toUpperCase());
    if (!buf) return [];
    return buf.slice(-n).map((pt) => pt.p);
  }
}
