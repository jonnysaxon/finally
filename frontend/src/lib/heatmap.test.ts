import { describe, expect, it } from "vitest";
import { pnlColor, squarify } from "./heatmap";
import type { Position } from "@/types/api";

function pos(ticker: string): Position {
  return {
    ticker,
    quantity: 1,
    avg_cost: 1,
    current_price: 1,
    market_value: 1,
    unrealized_pnl: 0,
    pnl_pct: 0,
  };
}

describe("squarify", () => {
  it("returns no tiles for empty input", () => {
    expect(squarify([], 0, 0, 100, 100)).toEqual([]);
  });

  it("fills the whole area (sum of tile areas ≈ canvas area)", () => {
    const items = [
      { value: 50, pos: pos("A"), pnlPct: 0.1 },
      { value: 30, pos: pos("B"), pnlPct: -0.1 },
      { value: 20, pos: pos("C"), pnlPct: 0 },
    ];
    const tiles = squarify(items, 0, 0, 200, 100);
    expect(tiles).toHaveLength(3);
    const area = tiles.reduce((s, t) => s + t.w * t.h, 0);
    expect(area).toBeCloseTo(200 * 100, 1);
  });

  it("sizes tiles proportionally to value", () => {
    const items = [
      { value: 75, pos: pos("BIG"), pnlPct: 0 },
      { value: 25, pos: pos("SMALL"), pnlPct: 0 },
    ];
    const tiles = squarify(items, 0, 0, 100, 100);
    const big = tiles.find((t) => t.pos.ticker === "BIG")!;
    const small = tiles.find((t) => t.pos.ticker === "SMALL")!;
    expect(big.w * big.h).toBeCloseTo(7500, 1);
    expect(small.w * small.h).toBeCloseTo(2500, 1);
  });
});

describe("pnlColor", () => {
  it("is green for gains and red for losses", () => {
    expect(pnlColor(0.05)).toContain("31,212,154");
    expect(pnlColor(-0.05)).toContain("255,93,108");
  });

  it("saturates alpha at ±8% and stays within bounds", () => {
    const max = pnlColor(0.2);
    const mid = pnlColor(0.04);
    const aMax = Number(max.match(/,([\d.]+)\)/)![1]);
    const aMid = Number(mid.match(/,([\d.]+)\)/)![1]);
    expect(aMax).toBeCloseTo(0.73, 2);
    expect(aMax).toBeGreaterThan(aMid);
  });
});
