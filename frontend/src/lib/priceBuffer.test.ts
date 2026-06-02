import { describe, expect, it } from "vitest";
import { PriceBuffer } from "./priceBuffer";

describe("PriceBuffer", () => {
  it("accumulates points per ticker, case-insensitively", () => {
    const b = new PriceBuffer();
    b.push("aapl", 100, 1);
    b.push("AAPL", 101, 2);
    expect(b.series("AAPL")).toHaveLength(2);
    expect(b.tail("aapl")).toEqual([100, 101]);
  });

  it("starts empty for unknown tickers", () => {
    const b = new PriceBuffer();
    expect(b.series("MSFT")).toEqual([]);
    expect(b.tail("MSFT")).toEqual([]);
  });

  it("drops exact duplicate ticks (same t and price)", () => {
    const b = new PriceBuffer();
    b.push("X", 5, 1);
    b.push("X", 5, 1);
    expect(b.series("X")).toHaveLength(1);
  });

  it("keeps distinct prices at the same timestamp", () => {
    const b = new PriceBuffer();
    b.push("X", 5, 1);
    b.push("X", 6, 1);
    expect(b.series("X")).toHaveLength(2);
  });

  it("caps the buffer at 500 points (drops oldest)", () => {
    const b = new PriceBuffer();
    for (let i = 0; i < 600; i++) b.push("X", i, i);
    const s = b.series("X");
    expect(s).toHaveLength(500);
    expect(s[0].p).toBe(100); // first 100 evicted
    expect(s[s.length - 1].p).toBe(599);
  });

  it("tail returns at most the requested count", () => {
    const b = new PriceBuffer();
    for (let i = 0; i < 100; i++) b.push("X", i, i);
    expect(b.tail("X", 10)).toHaveLength(10);
    expect(b.tail("X", 10)[9]).toBe(99);
  });
});
