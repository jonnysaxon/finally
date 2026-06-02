// Same-origin REST client. All endpoints are relative ("/api/*") so the static
// export works wherever FastAPI serves it (no base URL, no CORS).

import type {
  ChatResponse,
  HistoryResponse,
  Portfolio,
  TradeResponse,
  WatchlistResponse,
} from "@/types/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    // Backend returns `{detail}` on 400s.
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  getPortfolio: () => request<Portfolio>("/api/portfolio"),

  getHistory: () => request<HistoryResponse>("/api/portfolio/history"),

  trade: (ticker: string, quantity: number, side: "buy" | "sell") =>
    request<TradeResponse>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify({ ticker, quantity, side }),
    }),

  getWatchlist: () => request<WatchlistResponse>("/api/watchlist"),

  addWatchlist: (ticker: string) =>
    request<WatchlistResponse>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),

  removeWatchlist: (ticker: string) =>
    request<WatchlistResponse>(`/api/watchlist/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    }),

  chat: (message: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
