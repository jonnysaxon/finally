"use client";

import { Panel } from "./Panel";
import { useTerminal } from "@/hooks/useTerminalStore";
import { fmtPct, fmtPrice, fmtQty, fmtSignedMoney } from "@/lib/format";

export function PositionsTable() {
  const { portfolio, quotes, select } = useTerminal();
  const positions = portfolio?.positions ?? [];

  return (
    <Panel label="Positions" testId="positions" bodyClassName="overflow-auto">
      <table className="w-full text-data" data-testid="positions-table">
        <thead className="sticky top-0 bg-surface/95 backdrop-blur">
          <tr className="text-micro uppercase tracking-wider text-inkFaint">
            <Th className="text-left">Symbol</Th>
            <Th className="text-right">Qty</Th>
            <Th className="text-right">Avg Cost</Th>
            <Th className="text-right">Price</Th>
            <Th className="text-right">Mkt Value</Th>
            <Th className="text-right">Unreal. P&L</Th>
            <Th className="text-right">%</Th>
          </tr>
        </thead>
        <tbody>
          {positions.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-3 py-6 text-center text-inkFaint">
                No open positions.
              </td>
            </tr>
          ) : (
            positions.map((p) => {
              const sym = p.ticker.toUpperCase();
              const live = quotes.get(sym);
              const price = live?.price ?? p.current_price ?? p.avg_cost;
              const mv = p.quantity * price;
              const pnl = mv - p.quantity * p.avg_cost;
              const pnlPct = p.avg_cost > 0 ? (price - p.avg_cost) / p.avg_cost : 0;
              const cls = pnl > 0 ? "text-up" : pnl < 0 ? "text-down" : "text-inkMute";
              return (
                <tr
                  key={sym}
                  data-testid={`position-row-${sym}`}
                  data-ticker={sym}
                  onClick={() => select(sym)}
                  className="cursor-pointer border-t border-hairline/60 hover:bg-elevated/40"
                >
                  <Td className="text-left font-600 text-ink">{sym}</Td>
                  <Td testId="position-quantity" className="tnum text-right text-ink">
                    {fmtQty(p.quantity)}
                  </Td>
                  <Td testId="position-avg-cost" className="tnum text-right text-inkMute">
                    {fmtPrice(p.avg_cost)}
                  </Td>
                  <Td testId="position-current-price" className="tnum text-right text-ink">
                    {fmtPrice(price)}
                  </Td>
                  <Td className="tnum text-right text-ink">{fmtPrice(mv)}</Td>
                  <Td testId="position-pnl" className={`tnum text-right ${cls}`}>
                    {fmtSignedMoney(pnl)}
                  </Td>
                  <Td className={`tnum text-right ${cls}`}>{fmtPct(pnlPct)}</Td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </Panel>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <th className={`px-3 py-2 font-500 ${className}`}>{children}</th>;
}
function Td({
  children,
  className = "",
  testId,
}: {
  children: React.ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <td data-testid={testId} className={`px-3 py-1.5 ${className}`}>
      {children}
    </td>
  );
}
