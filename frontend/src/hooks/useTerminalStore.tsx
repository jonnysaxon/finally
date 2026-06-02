"use client";

// The single source of truth for the trading workstation UI.
//
// Owns: the SSE connection + connection status, the latest price per ticker,
// session-local price buffers (sparkline + detail chart), the watchlist,
// portfolio, P&L history, the selected ticker, and the chat thread. Components
// read slices via the `useTerminal` hook; mutations go through the actions it
// exposes so the SSE/REST coordination lives in one place.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, ApiError } from "@/lib/api";
import { PriceBuffer } from "@/lib/priceBuffer";
import type {
  ChatResponse,
  PriceEvent,
  Portfolio,
  Snapshot,
  WatchlistEntry,
} from "@/types/api";

export type ConnState = "connecting" | "connected" | "disconnected";

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  raw?: string;
  actions?: ChatResponse["actions"];
  pending?: boolean;
}

interface TerminalState {
  conn: ConnState;
  quotes: Map<string, PriceEvent>;
  buffer: PriceBuffer;
  bufferTick: number; // bumps when buffers change, to drive chart re-render
  watchlist: WatchlistEntry[];
  portfolio: Portfolio | null;
  history: Snapshot[];
  selected: string | null;
  chat: ChatTurn[];
  chatBusy: boolean;
  // actions
  select: (ticker: string) => void;
  addTicker: (ticker: string) => Promise<void>;
  removeTicker: (ticker: string) => Promise<void>;
  trade: (
    ticker: string,
    quantity: number,
    side: "buy" | "sell",
  ) => Promise<void>;
  sendChat: (message: string) => Promise<void>;
  lastError: string | null;
  clearError: () => void;
}

const TerminalContext = createContext<TerminalState | null>(null);

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function TerminalProvider({ children }: { children: React.ReactNode }) {
  const [conn, setConn] = useState<ConnState>("connecting");
  const quotesRef = useRef<Map<string, PriceEvent>>(new Map());
  const [quotes, setQuotes] = useState<Map<string, PriceEvent>>(new Map());
  const bufferRef = useRef(new PriceBuffer());
  const [bufferTick, setBufferTick] = useState(0);

  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  // ---- REST refreshers ----------------------------------------------------
  const refreshPortfolio = useCallback(async () => {
    try {
      setPortfolio(await api.getPortfolio());
    } catch {
      /* transient; SSE keeps the UI alive */
    }
  }, []);

  const refreshWatchlist = useCallback(async () => {
    try {
      const res = await api.getWatchlist();
      setWatchlist(res.tickers);
      setSelected((cur) => cur ?? res.tickers[0]?.ticker ?? null);
    } catch {
      /* ignore */
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory((await api.getHistory()).snapshots);
    } catch {
      /* ignore */
    }
  }, []);

  // ---- SSE stream ---------------------------------------------------------
  useEffect(() => {
    let es: EventSource | null = null;
    let bufferFlush: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    const connect = () => {
      es = new EventSource("/api/stream/prices");
      setConn("connecting");

      es.onopen = () => setConn("connected");

      es.addEventListener("price", (ev) => {
        try {
          const data: PriceEvent = JSON.parse((ev as MessageEvent).data);
          const key = data.ticker.toUpperCase();
          quotesRef.current.set(key, data);
          bufferRef.current.push(key, data.price, data.timestamp);
        } catch {
          /* skip malformed event */
        }
      });

      es.onerror = () => {
        // EventSource auto-reconnects; reflect the gap in the status dot.
        setConn(es && es.readyState === EventSource.CLOSED ? "disconnected" : "connecting");
      };
    };

    connect();

    // Batch quote/buffer updates into the React tree at a steady cadence so a
    // 10-ticker 500ms stream doesn't thrash render. Matches the push rate.
    bufferFlush = setInterval(() => {
      if (closed) return;
      setQuotes(new Map(quotesRef.current));
      setBufferTick((n) => n + 1);
    }, 500);

    return () => {
      closed = true;
      if (bufferFlush) clearInterval(bufferFlush);
      es?.close();
    };
  }, []);

  // ---- Initial load + periodic portfolio/history refresh ------------------
  useEffect(() => {
    refreshWatchlist();
    refreshPortfolio();
    refreshHistory();
    // Portfolio value drifts with live prices; backend snapshots every 30s.
    const pid = setInterval(refreshPortfolio, 10_000);
    const hid = setInterval(refreshHistory, 30_000);
    return () => {
      clearInterval(pid);
      clearInterval(hid);
    };
  }, [refreshWatchlist, refreshPortfolio, refreshHistory]);

  // ---- Actions ------------------------------------------------------------
  const select = useCallback((ticker: string) => setSelected(ticker.toUpperCase()), []);
  const clearError = useCallback(() => setLastError(null), []);

  const addTicker = useCallback(
    async (ticker: string) => {
      const sym = ticker.trim().toUpperCase();
      if (!sym) return;
      try {
        const res = await api.addWatchlist(sym);
        setWatchlist(res.tickers);
        setSelected(sym);
      } catch (e) {
        setLastError(e instanceof ApiError ? e.message : "Could not add ticker");
        throw e;
      }
    },
    [],
  );

  const removeTicker = useCallback(async (ticker: string) => {
    const sym = ticker.toUpperCase();
    try {
      const res = await api.removeWatchlist(sym);
      setWatchlist(res.tickers);
      setSelected((cur) => (cur === sym ? res.tickers[0]?.ticker ?? null : cur));
    } catch (e) {
      setLastError(e instanceof ApiError ? e.message : "Could not remove ticker");
    }
  }, []);

  const trade = useCallback(
    async (ticker: string, quantity: number, side: "buy" | "sell") => {
      try {
        await api.trade(ticker.toUpperCase(), quantity, side);
        await Promise.all([refreshPortfolio(), refreshHistory()]);
      } catch (e) {
        setLastError(e instanceof ApiError ? e.message : "Trade failed");
        throw e;
      }
    },
    [refreshPortfolio, refreshHistory],
  );

  const sendChat = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text || chatBusy) return;
      const userTurn: ChatTurn = { id: uid(), role: "user", content: text };
      const pendingId = uid();
      setChat((c) => [
        ...c,
        userTurn,
        { id: pendingId, role: "assistant", content: "", pending: true },
      ]);
      setChatBusy(true);
      try {
        const res = await api.chat(text);
        setChat((c) =>
          c.map((t) =>
            t.id === pendingId
              ? {
                  ...t,
                  pending: false,
                  content: res.message,
                  raw: res.raw,
                  actions: res.actions,
                }
              : t,
          ),
        );
        // The assistant may have traded or edited the watchlist.
        await Promise.all([refreshPortfolio(), refreshWatchlist(), refreshHistory()]);
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Chat request failed";
        setChat((c) =>
          c.map((t) =>
            t.id === pendingId
              ? { ...t, pending: false, content: `⚠ ${msg}` }
              : t,
          ),
        );
      } finally {
        setChatBusy(false);
      }
    },
    [chatBusy, refreshPortfolio, refreshWatchlist, refreshHistory],
  );

  const value = useMemo<TerminalState>(
    () => ({
      conn,
      quotes,
      buffer: bufferRef.current,
      bufferTick,
      watchlist,
      portfolio,
      history,
      selected,
      chat,
      chatBusy,
      select,
      addTicker,
      removeTicker,
      trade,
      sendChat,
      lastError,
      clearError,
    }),
    [
      conn,
      quotes,
      bufferTick,
      watchlist,
      portfolio,
      history,
      selected,
      chat,
      chatBusy,
      select,
      addTicker,
      removeTicker,
      trade,
      sendChat,
      lastError,
      clearError,
    ],
  );

  return (
    <TerminalContext.Provider value={value}>{children}</TerminalContext.Provider>
  );
}

export function useTerminal(): TerminalState {
  const ctx = useContext(TerminalContext);
  if (!ctx) throw new Error("useTerminal must be used within TerminalProvider");
  return ctx;
}
