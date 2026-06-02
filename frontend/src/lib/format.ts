// Number/price formatting helpers. A terminal lives or dies on consistent,
// tabular-aligned numbers, so everything routes through here.

export function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `$${fmtPrice(v)}`;
}

export function fmtSignedMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}$${fmtPrice(Math.abs(v))}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

/** Quantity: up to 4 decimals for fractional shares, trailing zeros trimmed. */
export function fmtQty(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return parseFloat(v.toFixed(4)).toString();
}

export function fmtTime(epochOrIso: number | string): string {
  const d =
    typeof epochOrIso === "number"
      ? new Date(epochOrIso * 1000)
      : new Date(epochOrIso);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Direction → semantic color class for text. */
export function dirColor(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-inkMute";
  return v > 0 ? "text-up" : "text-down";
}
