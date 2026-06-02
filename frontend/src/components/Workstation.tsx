"use client";

import { useState } from "react";
import { TerminalProvider } from "@/hooks/useTerminalStore";
import { Header } from "./Header";
import { Watchlist } from "./Watchlist";
import { DetailChart } from "./DetailChart";
import { Heatmap } from "./Heatmap";
import { PnlChart } from "./PnlChart";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { ChatPanel } from "./ChatPanel";
import { ErrorToast } from "./ErrorToast";

/**
 * Desktop-first terminal grid. A fixed header, a three-column body
 * (watchlist · charts+positions · AI copilot), and a docked trade bar.
 *
 * Each panel mounts exactly once. Below the `lg` breakpoint the grid collapses
 * to a single scrolling column (the copilot rail expands inline), so we never
 * duplicate components — keeping `data-testid`s unique for E2E selectors.
 */
export function Workstation() {
  const [chatCollapsed, setChatCollapsed] = useState(false);

  return (
    <TerminalProvider>
      <div className="flex h-screen flex-col overflow-hidden">
        <Header />

        <main className="grid min-h-0 flex-1 gap-3 overflow-y-auto p-3 lg:grid-cols-[300px_minmax(0,1fr)_auto] lg:overflow-hidden">
          {/* Left rail: watchlist */}
          <div className="h-[340px] min-h-0 lg:h-auto">
            <Watchlist />
          </div>

          {/* Center: charts, heatmap, positions, trade bar.
              Each panel wrapper stretches to fill its grid cell (`lg:h-full`,
              with grid's default align-items:stretch), so the panel's flex
              column and the charts' `h-full`/ResponsiveContainer resolve to a
              definite height. Below `lg` the layout stacks and uses fixed
              pixel heights instead. Using `h-auto` here would break the height
              chain and collapse the charts to 0px. */}
          <div className="grid min-h-0 gap-3 lg:grid-rows-[minmax(0,1.25fr)_minmax(0,1fr)_auto]">
            <div className="grid min-h-0 gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <div className="h-[300px] min-h-0 xl:h-full">
                <DetailChart />
              </div>
              <div className="h-[300px] min-h-0 xl:h-full">
                <Heatmap />
              </div>
            </div>
            <div className="grid min-h-0 gap-3 xl:grid-cols-2">
              <div className="h-[260px] min-h-0 xl:h-full">
                <PositionsTable />
              </div>
              <div className="h-[260px] min-h-0 xl:h-full">
                <PnlChart />
              </div>
            </div>
            <TradeBar />
          </div>

          {/* Right: AI copilot (collapsible on desktop) */}
          <div
            className={`min-h-0 ${
              chatCollapsed ? "lg:w-12" : "lg:w-[360px]"
            } h-[440px] transition-[width] duration-200 lg:h-auto`}
          >
            <ChatPanel
              collapsed={chatCollapsed}
              onToggle={() => setChatCollapsed((c) => !c)}
            />
          </div>
        </main>

        <ErrorToast />
      </div>
    </TerminalProvider>
  );
}
