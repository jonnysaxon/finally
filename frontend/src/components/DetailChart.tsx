"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel } from "./Panel";
import { useTerminal } from "@/hooks/useTerminalStore";
import { fmtPct, fmtPrice, fmtTime } from "@/lib/format";
import type { PriceEvent } from "@/types/api";

export function DetailChart() {
  const { selected, quotes, buffer, bufferTick } = useTerminal();
  const sym = selected?.toUpperCase() ?? null;
  const live: PriceEvent | undefined = sym ? quotes.get(sym) : undefined;

  const data = useMemo(() => {
    if (!sym) return [];
    return buffer.series(sym).map((pt) => ({ t: pt.t, p: pt.p }));
    // bufferTick is the intentional re-render signal as the buffer grows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sym, bufferTick, buffer]);

  const up = (live?.change_pct ?? 0) >= 0;
  const stroke = up ? "#1fd49a" : "#ff5d6c";

  return (
    <Panel
      label="Chart"
      testId="detail-chart"
      bodyClassName="flex flex-col"
      accessory={
        sym ? (
          <div className="flex items-baseline gap-3">
            <span className="font-display text-sm font-700 tracking-wide text-ink">
              {sym}
            </span>
            <span className="tnum text-data text-ink">{fmtPrice(live?.price)}</span>
            <span className={`tnum text-data ${up ? "text-up" : "text-down"}`}>
              {fmtPct(live?.change_pct)}
            </span>
          </div>
        ) : null
      }
    >
      {!sym ? (
        <Empty msg="Select a ticker from the watchlist." />
      ) : data.length < 2 ? (
        <Empty msg={`Streaming ${sym} — chart fills in from live ticks…`} />
      ) : (
        <div className="h-full min-h-[180px] w-full p-2" data-testid="detail-chart-canvas">
          <ResponsiveContainer width="100%" height="100%" minHeight={180}>
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
              <defs>
                <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="t"
                tickFormatter={(t) => fmtTime(t)}
                stroke="#5c6878"
                tick={{ fontSize: 10, fill: "#5c6878", fontFamily: "JetBrains Mono" }}
                minTickGap={48}
                axisLine={{ stroke: "#232c3b" }}
                tickLine={false}
              />
              <YAxis
                domain={["auto", "auto"]}
                orientation="right"
                width={56}
                stroke="#5c6878"
                tick={{ fontSize: 10, fill: "#5c6878", fontFamily: "JetBrains Mono" }}
                tickFormatter={(v) => fmtPrice(v)}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#11161f",
                  border: "1px solid #2f3a4d",
                  borderRadius: 6,
                  fontFamily: "JetBrains Mono",
                  fontSize: 12,
                }}
                labelFormatter={(t) => fmtTime(Number(t))}
                formatter={(v: number) => [fmtPrice(v), "Price"]}
                cursor={{ stroke: "#2f3a4d", strokeDasharray: "3 3" }}
              />
              <Area
                type="monotone"
                dataKey="p"
                stroke={stroke}
                strokeWidth={1.6}
                fill="url(#priceFill)"
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

function Empty({ msg }: { msg: string }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-data text-inkFaint">
      {msg}
    </div>
  );
}
