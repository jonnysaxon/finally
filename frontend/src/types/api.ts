// HTTP + SSE contract types — mirror BUILD_CONTRACT.md §"HTTP API Contract"
// and backend/app/market/types.py Quote.to_event(). Keep field names exact.

/** One `price` SSE event payload (Quote.to_event()). */
export interface PriceEvent {
  ticker: string;
  price: number;
  prev_price: number;
  open_price: number;
  change: number;
  change_pct: number;
  direction: "up" | "down" | "flat";
  timestamp: number; // epoch seconds
}

/** A row from GET /api/watchlist (prices may be null before first tick). */
export interface WatchlistEntry {
  ticker: string;
  price: number | null;
  prev_price: number | null;
  open_price: number | null;
  change: number | null;
  change_pct: number | null;
  direction: "up" | "down" | "flat" | null;
}

export interface WatchlistResponse {
  tickers: WatchlistEntry[];
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  pnl_pct: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  positions_value: number;
  positions: Position[];
}

export interface Trade {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executed_at: string;
}

export interface TradeResponse {
  trade: Trade;
  position: Position | null;
  cash_balance: number;
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface HistoryResponse {
  snapshots: Snapshot[];
}

export interface ChatTradeAction {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  status?: "executed" | "error";
  error?: string;
}

export interface ChatWatchlistAction {
  ticker: string;
  action: "add" | "remove";
  status?: "executed" | "error";
  error?: string;
}

export interface ChatResponse {
  message: string;
  actions: {
    trades: ChatTradeAction[];
    watchlist_changes: ChatWatchlistAction[];
  };
  raw?: string;
}
