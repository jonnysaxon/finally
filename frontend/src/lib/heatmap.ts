// Pure layout/color helpers for the portfolio heatmap, split out so they can be
// unit-tested without rendering SVG.

import type { Position } from "@/types/api";

export interface Tile {
  pos: Position;
  marketValue: number;
  pnlPct: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface SqItem {
  value: number;
  pos: Position;
  pnlPct: number;
}

/**
 * Squarified treemap (Bruls et al.): lay tiles in rows/columns minimizing the
 * worst aspect ratio so each position reads as a near-square rectangle sized by
 * portfolio weight (= market value).
 */
export function squarify(
  items: SqItem[],
  x: number,
  y: number,
  w: number,
  h: number,
): Tile[] {
  const total = items.reduce((s, i) => s + i.value, 0);
  if (total <= 0 || items.length === 0) return [];
  const scale = (w * h) / total;
  const scaled = items.map((i) => ({ ...i, area: i.value * scale }));

  const tiles: Tile[] = [];
  let rect = { x, y, w, h };

  const worst = (r: (SqItem & { area: number })[], length: number) => {
    if (r.length === 0) return Infinity;
    const sum = r.reduce((s, i) => s + i.area, 0);
    const max = Math.max(...r.map((i) => i.area));
    const min = Math.min(...r.map((i) => i.area));
    const l2 = length * length;
    const s2 = sum * sum;
    return Math.max((l2 * max) / s2, s2 / (l2 * min));
  };

  const layoutRow = (r: (SqItem & { area: number })[], horizontal: boolean) => {
    const sum = r.reduce((s, i) => s + i.area, 0);
    if (horizontal) {
      const rowH = sum / rect.w;
      let cx = rect.x;
      for (const it of r) {
        const tw = it.area / rowH;
        tiles.push({ pos: it.pos, marketValue: it.value, pnlPct: it.pnlPct, x: cx, y: rect.y, w: tw, h: rowH });
        cx += tw;
      }
      rect = { x: rect.x, y: rect.y + rowH, w: rect.w, h: rect.h - rowH };
    } else {
      const rowW = sum / rect.h;
      let cy = rect.y;
      for (const it of r) {
        const th = it.area / rowW;
        tiles.push({ pos: it.pos, marketValue: it.value, pnlPct: it.pnlPct, x: rect.x, y: cy, w: rowW, h: th });
        cy += th;
      }
      rect = { x: rect.x + rowW, y: rect.y, w: rect.w - rowW, h: rect.h };
    }
  };

  const remaining = [...scaled];
  let row: (SqItem & { area: number })[] = [];
  while (remaining.length > 0) {
    const horizontal = rect.w >= rect.h;
    const length = horizontal ? rect.w : rect.h;
    const next = remaining[0];
    if (row.length === 0 || worst([...row, next], length) <= worst(row, length)) {
      row.push(next);
      remaining.shift();
    } else {
      layoutRow(row, horizontal);
      row = [];
    }
  }
  if (row.length > 0) layoutRow(row, rect.w >= rect.h);
  return tiles;
}

/** P&L% → tile background. Green for gains, red for losses, saturating at ±8%. */
export function pnlColor(pct: number): string {
  const clamped = Math.max(-0.08, Math.min(0.08, pct));
  const intensity = Math.abs(clamped) / 0.08; // 0..1
  const a = 0.18 + intensity * 0.55;
  return pct >= 0
    ? `rgba(31,212,154,${a.toFixed(3)})`
    : `rgba(255,93,108,${a.toFixed(3)})`;
}
