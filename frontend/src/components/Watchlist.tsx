"use client";

import { useEffect, useRef, useState } from "react";
import { Panel } from "./Panel";
import { Sparkline } from "./Sparkline";
import { useTerminal } from "@/hooks/useTerminalStore";
import { fmtPct, fmtPrice } from "@/lib/format";
import type { PriceEvent, WatchlistEntry } from "@/types/api";

export function Watchlist() {
  const { watchlist, addTicker } = useTerminal();
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const sym = draft.trim().toUpperCase();
    if (!sym) return;
    setAdding(true);
    try {
      await addTicker(sym);
      setDraft("");
    } catch {
      /* error surfaced via store.lastError */
    } finally {
      setAdding(false);
    }
  };

  return (
    <Panel
      label="Watchlist"
      testId="watchlist"
      bodyClassName="flex flex-col"
      accessory={
        <form onSubmit={onAdd} className="flex items-center gap-1.5">
          <input
            data-testid="watchlist-add-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder="ADD"
            spellCheck={false}
            maxLength={8}
            className="w-16 rounded border border-hairline bg-base px-2 py-1 text-micro uppercase tracking-widest text-ink placeholder:text-inkFaint focus:border-amber focus:outline-none"
          />
          <button
            type="submit"
            data-testid="watchlist-add-btn"
            disabled={adding}
            className="rounded border border-hairline bg-elevated px-2 py-1 text-micro font-600 uppercase tracking-wider text-inkMute transition-colors hover:border-amber hover:text-amber disabled:opacity-50"
          >
            +
          </button>
        </form>
      }
    >
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 border-b border-hairline px-3 py-1.5 text-micro uppercase tracking-wider text-inkFaint">
        <span>Symbol</span>
        <span className="text-right">Last</span>
        <span className="text-right">Change</span>
        <span className="pl-2 text-right">Trend</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="watchlist-rows">
        {watchlist.length === 0 ? (
          <div className="px-3 py-6 text-center text-data text-inkFaint">
            No tickers yet.
          </div>
        ) : (
          watchlist.map((entry) => <WatchlistRow key={entry.ticker} entry={entry} />)
        )}
      </div>
    </Panel>
  );
}

function WatchlistRow({ entry }: { entry: WatchlistEntry }) {
  const { quotes, buffer, bufferTick, selected, select, removeTicker } = useTerminal();
  const sym = entry.ticker.toUpperCase();
  const live: PriceEvent | undefined = quotes.get(sym);

  // Prefer the live SSE quote; fall back to the REST snapshot from the list.
  const price = live?.price ?? entry.price;
  const changePct = live?.change_pct ?? entry.change_pct;
  const direction = live?.direction ?? entry.direction ?? "flat";

  // Flash on every actual price change. We key the flash off the live price and
  // remember the previous to decide green vs red, then let the CSS animation
  // fade it out (PLAN §2: ~500ms fade).
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const prevPriceRef = useRef<number | null>(null);
  useEffect(() => {
    if (price == null) return;
    const prev = prevPriceRef.current;
    if (prev != null && price !== prev) {
      setFlash(price > prev ? "up" : "down");
    }
    prevPriceRef.current = price;
  }, [price]);

  const isSelected = selected === sym;
  const spark = buffer.tail(sym, 40);
  void bufferTick; // re-render trigger when the buffer grows

  return (
    <button
      type="button"
      data-testid={`watchlist-row-${sym}`}
      data-ticker={sym}
      data-selected={isSelected}
      onClick={() => select(sym)}
      onAnimationEnd={() => setFlash(null)}
      className={`group grid w-full grid-cols-[1fr_auto_auto_auto] items-center gap-x-3 border-l-2 px-3 py-2 text-left transition-colors ${
        isSelected
          ? "border-amber bg-elevated/70"
          : "border-transparent hover:bg-elevated/40"
      } ${flash === "up" ? "animate-flashUp" : ""} ${
        flash === "down" ? "animate-flashDown" : ""
      }`}
    >
      <span className="flex items-center gap-2 overflow-hidden">
        <span className="truncate font-600 text-data text-ink">{sym}</span>
        <span
          role="button"
          tabIndex={0}
          data-testid={`watchlist-remove-${sym}`}
          onClick={(e) => {
            e.stopPropagation();
            removeTicker(sym);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.stopPropagation();
              removeTicker(sym);
            }
          }}
          aria-label={`Remove ${sym}`}
          className="hidden shrink-0 cursor-pointer rounded px-1 text-micro text-inkFaint hover:text-down group-hover:inline"
        >
          ✕
        </span>
      </span>

      <span data-testid="watchlist-price" className="tnum text-right text-data text-ink">
        {fmtPrice(price)}
      </span>

      <span
        className={`tnum text-right text-data ${
          direction === "up"
            ? "text-up"
            : direction === "down"
              ? "text-down"
              : "text-inkMute"
        }`}
      >
        {fmtPct(changePct)}
      </span>

      <span className="flex justify-end pl-2">
        <Sparkline data={spark} />
      </span>
    </button>
  );
}
