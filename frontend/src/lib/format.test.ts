import { describe, expect, it } from "vitest";
import {
  fmtMoney,
  fmtPct,
  fmtPrice,
  fmtQty,
  fmtSignedMoney,
} from "./format";

describe("format", () => {
  it("formats prices to 2dp with thousands separators", () => {
    expect(fmtPrice(1234.5)).toBe("1,234.50");
    expect(fmtPrice(0)).toBe("0.00");
  });

  it("renders em-dash for null/NaN", () => {
    expect(fmtPrice(null)).toBe("—");
    expect(fmtPrice(undefined)).toBe("—");
    expect(fmtMoney(NaN)).toBe("—");
  });

  it("formats money with $ and signed money with sign", () => {
    expect(fmtMoney(10)).toBe("$10.00");
    expect(fmtSignedMoney(10)).toBe("+$10.00");
    expect(fmtSignedMoney(-10)).toBe("-$10.00");
    expect(fmtSignedMoney(0)).toBe("$0.00");
  });

  it("formats percentages from fractional change", () => {
    expect(fmtPct(0.0123)).toBe("+1.23%");
    expect(fmtPct(-0.05)).toBe("-5.00%");
    expect(fmtPct(0)).toBe("0.00%");
  });

  it("trims trailing zeros on fractional quantities", () => {
    expect(fmtQty(10)).toBe("10");
    expect(fmtQty(1.5)).toBe("1.5");
    expect(fmtQty(0.123456)).toBe("0.1235");
  });
});
