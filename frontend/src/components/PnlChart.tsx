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
import { fmtMoney, fmtTime } from "@/lib/format";

const MAX_POINTS = 120; // downsample for display (PLAN §13.8)

export function PnlChart() {
  const { history } = useTerminal();

  const data = useMemo(() => {
    if (history.length === 0) return [];
    // Bucket-average down to MAX_POINTS keeping chronological order.
    const step = Math.max(1, Math.ceil(history.length / MAX_POINTS));
    const out: { t: number; v: number }[] = [];
    for (let i = 0; i < history.length; i += step) {
      const slice = history.slice(i, i + step);
      const avg = slice.reduce((s, p) => s + p.total_value, 0) / slice.length;
      const t = new Date(slice[slice.length - 1].recorded_at).getTime() / 1000;
      out.push({ t, v: avg });
    }
    return out;
  }, [history]);

  const first = data[0]?.v ?? 0;
  const last = data[data.length - 1]?.v ?? 0;
  const up = last >= first;
  const stroke = up ? "#1fd49a" : "#ff5d6c";

  return (
    <Panel label="P&L · Portfolio Value" testId="pnl-chart" bodyClassName="p-2">
      {data.length < 2 ? (
        <div className="flex h-full items-center justify-center px-6 text-center text-data text-inkFaint">
          Tracking portfolio value — the curve appears as snapshots accumulate.
        </div>
      ) : (
        <div className="h-full min-h-[180px] w-full" data-testid="pnl-chart-canvas">
          <ResponsiveContainer width="100%" height="100%" minHeight={180}>
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
              <defs>
                <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.26} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="t"
                tickFormatter={(t) => fmtTime(t)}
                stroke="#5c6878"
                tick={{ fontSize: 10, fill: "#5c6878", fontFamily: "JetBrains Mono" }}
                minTickGap={56}
                axisLine={{ stroke: "#232c3b" }}
                tickLine={false}
              />
              <YAxis
                domain={["auto", "auto"]}
                orientation="right"
                width={64}
                stroke="#5c6878"
                tick={{ fontSize: 10, fill: "#5c6878", fontFamily: "JetBrains Mono" }}
                tickFormatter={(v) => `$${Math.round(v).toLocaleString()}`}
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
                formatter={(v: number) => [fmtMoney(v), "Value"]}
                cursor={{ stroke: "#2f3a4d", strokeDasharray: "3 3" }}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke={stroke}
                strokeWidth={1.6}
                fill="url(#pnlFill)"
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
