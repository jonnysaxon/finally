"use client";

import { useMemo } from "react";
import { Panel } from "./Panel";
import { useTerminal } from "@/hooks/useTerminalStore";
import { fmtPct, fmtMoney } from "@/lib/format";
import { pnlColor, squarify } from "@/lib/heatmap";

const W = 1000;
const H = 560;

export function Heatmap() {
  const { portfolio, quotes, select } = useTerminal();

  const tiles = useMemo(() => {
    if (!portfolio || portfolio.positions.length === 0) return [];
    const items = portfolio.positions
      .map((pos) => {
        const live = quotes.get(pos.ticker.toUpperCase());
        const price = live?.price ?? pos.current_price ?? pos.avg_cost;
        const mv = pos.quantity * price;
        const pnlPct = pos.avg_cost > 0 ? (price - pos.avg_cost) / pos.avg_cost : 0;
        return { value: mv, pos, pnlPct };
      })
      .filter((i) => i.value > 0)
      .sort((a, b) => b.value - a.value);
    return squarify(items, 0, 0, W, H);
  }, [portfolio, quotes]);

  return (
    <Panel label="Portfolio Heatmap" testId="heatmap" bodyClassName="p-2">
      {tiles.length === 0 ? (
        <div className="flex h-full items-center justify-center text-data text-inkFaint">
          No positions yet — make a trade to populate the heatmap.
        </div>
      ) : (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="h-full w-full"
          data-testid="heatmap-svg"
        >
          {tiles.map((t) => {
            const pad = 2;
            const showLabel = t.w > 60 && t.h > 34;
            return (
              <g
                key={t.pos.ticker}
                data-testid={`heatmap-tile-${t.pos.ticker.toUpperCase()}`}
                data-ticker={t.pos.ticker.toUpperCase()}
                onClick={() => select(t.pos.ticker)}
                className="cursor-pointer"
              >
                <rect
                  x={t.x + pad}
                  y={t.y + pad}
                  width={Math.max(0, t.w - pad * 2)}
                  height={Math.max(0, t.h - pad * 2)}
                  rx={4}
                  fill={pnlColor(t.pnlPct)}
                  stroke="#0d1117"
                  strokeWidth={2}
                />
                {showLabel && (
                  <>
                    <text
                      x={t.x + 12}
                      y={t.y + 26}
                      fill="#e9edf4"
                      fontFamily="Space Grotesk, sans-serif"
                      fontWeight={700}
                      fontSize={Math.min(22, t.w / 4)}
                    >
                      {t.pos.ticker.toUpperCase()}
                    </text>
                    <text
                      x={t.x + 12}
                      y={t.y + 26 + 18}
                      fill="#e9edf4"
                      fontFamily="JetBrains Mono, monospace"
                      fontSize={13}
                      opacity={0.92}
                    >
                      {fmtPct(t.pnlPct)}
                    </text>
                  </>
                )}
                <title>{`${t.pos.ticker.toUpperCase()}  ${fmtMoney(t.marketValue)}  ${fmtPct(t.pnlPct)}`}</title>
              </g>
            );
          })}
        </svg>
      )}
    </Panel>
  );
}
