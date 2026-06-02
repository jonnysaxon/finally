"use client";

import { useTerminal, type ConnState } from "@/hooks/useTerminalStore";
import { fmtMoney } from "@/lib/format";

const CONN_META: Record<ConnState, { dot: string; label: string; text: string }> = {
  connected: { dot: "bg-up", label: "LIVE", text: "text-up" },
  connecting: { dot: "bg-amber", label: "SYNCING", text: "text-amber" },
  disconnected: { dot: "bg-down", label: "OFFLINE", text: "text-down" },
};

/**
 * Live total = cash + Σ(qty × live price). We recompute from streaming quotes
 * rather than waiting on the 10s portfolio poll, so the header ticks in real
 * time. Falls back to the backend's total when a position has no live quote.
 */
function useLiveTotal(): { total: number | null; cash: number | null } {
  const { portfolio, quotes } = useTerminal();
  if (!portfolio) return { total: null, cash: null };
  let positionsValue = 0;
  for (const pos of portfolio.positions) {
    const q = quotes.get(pos.ticker.toUpperCase());
    const price = q?.price ?? pos.current_price ?? pos.avg_cost;
    positionsValue += pos.quantity * price;
  }
  return { total: portfolio.cash_balance + positionsValue, cash: portfolio.cash_balance };
}

export function Header() {
  const { conn } = useTerminal();
  const { total, cash } = useLiveTotal();
  const meta = CONN_META[conn];

  return (
    <header
      data-testid="header"
      className="flex items-center justify-between gap-6 border-b border-hairline bg-surface/70 px-5 py-3 backdrop-blur"
    >
      <div className="flex items-baseline gap-3">
        <span className="font-display text-lg font-700 tracking-tight text-ink">
          Fin<span className="text-amber">Ally</span>
        </span>
        <span className="hidden text-micro uppercase tracking-[0.2em] text-inkFaint sm:inline">
          AI Trading Workstation
        </span>
      </div>

      <div className="flex items-center gap-7">
        <Stat label="Portfolio Value">
          <span data-testid="header-total-value" className="tnum text-base font-600 text-ink">
            {fmtMoney(total)}
          </span>
        </Stat>
        <span className="hidden h-7 w-px bg-hairline md:block" aria-hidden />
        <Stat label="Cash">
          <span data-testid="header-cash" className="tnum text-base font-600 text-blue">
            {fmtMoney(cash)}
          </span>
        </Stat>
        <span className="hidden h-7 w-px bg-hairline md:block" aria-hidden />
        <div
          className="flex items-center gap-2"
          data-testid="connection-status"
          // `data-state` ∈ connecting|connected|disconnected — what the E2E specs assert.
          data-state={conn}
          title={`Stream: ${meta.label}`}
        >
          <span
            className={`h-2.5 w-2.5 rounded-full ${meta.dot} ${
              conn !== "disconnected" ? "animate-pulseDot" : ""
            }`}
            style={{
              boxShadow:
                conn === "connected"
                  ? "0 0 10px 1px rgba(31,212,154,0.6)"
                  : conn === "connecting"
                    ? "0 0 10px 1px rgba(236,173,10,0.6)"
                    : "none",
            }}
          />
          <span className={`text-micro font-600 tracking-[0.16em] ${meta.text}`}>
            {meta.label}
          </span>
        </div>
      </div>
    </header>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="text-micro uppercase tracking-[0.16em] text-inkFaint">
        {label}
      </span>
      {children}
    </div>
  );
}
