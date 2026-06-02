"use client";

import { useEffect, useState } from "react";
import { useTerminal } from "@/hooks/useTerminalStore";
import { fmtMoney } from "@/lib/format";

// Market orders, instant fill, no confirmation dialog (PLAN §2).
export function TradeBar() {
  const { selected, quotes, trade } = useTerminal();
  const [ticker, setTicker] = useState("");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  // Track the selected ticker by default; let the user override by typing.
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!touched && selected) setTicker(selected);
  }, [selected, touched]);

  const sym = ticker.trim().toUpperCase();
  const live = sym ? quotes.get(sym) : undefined;
  const qtyNum = parseFloat(qty);
  const estCost =
    live && Number.isFinite(qtyNum) && qtyNum > 0 ? live.price * qtyNum : null;

  const submit = async (side: "buy" | "sell") => {
    setFeedback(null);
    if (!sym) return setFeedback({ kind: "err", text: "Enter a ticker." });
    if (!Number.isFinite(qtyNum) || qtyNum <= 0)
      return setFeedback({ kind: "err", text: "Enter a positive quantity." });
    setBusy(true);
    try {
      await trade(sym, qtyNum, side);
      setFeedback({
        kind: "ok",
        text: `${side === "buy" ? "Bought" : "Sold"} ${qtyNum} ${sym}`,
      });
      setQty("");
    } catch (e) {
      setFeedback({ kind: "err", text: e instanceof Error ? e.message : "Trade failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="trade-bar"
      className="flex flex-wrap items-end gap-3 rounded-md border border-hairline bg-panel px-3 py-2.5 shadow-panel"
    >
      <Field label="Ticker">
        <input
          data-testid="trade-ticker"
          value={ticker}
          onChange={(e) => {
            setTouched(true);
            setTicker(e.target.value.toUpperCase());
          }}
          placeholder="AAPL"
          spellCheck={false}
          maxLength={8}
          className="w-24 rounded border border-hairline bg-base px-2.5 py-1.5 text-data uppercase tracking-wide text-ink placeholder:text-inkFaint focus:border-blue focus:outline-none"
        />
      </Field>

      <Field label="Quantity">
        <input
          data-testid="trade-qty"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          inputMode="decimal"
          placeholder="0"
          className="tnum w-24 rounded border border-hairline bg-base px-2.5 py-1.5 text-data text-ink placeholder:text-inkFaint focus:border-blue focus:outline-none"
        />
      </Field>

      <div className="flex flex-col gap-0.5">
        <span className="text-micro uppercase tracking-[0.16em] text-inkFaint">
          Est. Cost
        </span>
        <span className="tnum py-1.5 text-data text-inkMute" data-testid="trade-est">
          {estCost != null ? fmtMoney(estCost) : "—"}
        </span>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          data-testid="trade-buy"
          disabled={busy}
          onClick={() => submit("buy")}
          className="rounded border border-up/40 bg-up/15 px-5 py-1.5 text-data font-600 uppercase tracking-wider text-up transition-colors hover:bg-up/25 disabled:opacity-50"
        >
          Buy
        </button>
        <button
          type="button"
          data-testid="trade-sell"
          disabled={busy}
          onClick={() => submit("sell")}
          className="rounded border border-down/40 bg-down/15 px-5 py-1.5 text-data font-600 uppercase tracking-wider text-down transition-colors hover:bg-down/25 disabled:opacity-50"
        >
          Sell
        </button>
      </div>

      {feedback && (
        <span
          data-testid="trade-feedback"
          className={`ml-auto self-center text-data ${
            feedback.kind === "ok" ? "text-up" : "text-down"
          }`}
        >
          {feedback.text}
        </span>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-micro uppercase tracking-[0.16em] text-inkFaint">
        {label}
      </span>
      {children}
    </div>
  );
}
