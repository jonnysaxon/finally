// Throwaway mock backend for local visual verification of the static export.
// Serves out/ plus stub /api/* responses + an SSE price stream. Not shipped.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../out");
const TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];
const seed = { AAPL: 190, GOOGL: 175, MSFT: 420, AMZN: 185, TSLA: 250, NVDA: 1200, META: 500, JPM: 200, V: 280, NFLX: 600 };
const state = {};
for (const t of TICKERS) state[t] = { price: seed[t], open: seed[t], prev: seed[t] };
const positions = [
  { ticker: "AAPL", quantity: 10, avg_cost: 180 },
  { ticker: "NVDA", quantity: 2, avg_cost: 1100 },
  { ticker: "TSLA", quantity: 5, avg_cost: 270 },
];
const snapshots = [];
let cash = 10000 - 10 * 180 - 2 * 1100 - 5 * 270;

function portfolio() {
  const pos = positions.map((p) => {
    const price = state[p.ticker].price;
    const mv = p.quantity * price;
    return { ...p, current_price: price, market_value: mv, unrealized_pnl: mv - p.quantity * p.avg_cost, pnl_pct: (price - p.avg_cost) / p.avg_cost };
  });
  const positions_value = pos.reduce((s, p) => s + p.market_value, 0);
  return { cash_balance: cash, positions_value, total_value: cash + positions_value, positions: pos };
}

setInterval(() => {
  for (const t of TICKERS) {
    const s = state[t];
    s.prev = s.price;
    s.price = Math.max(1, s.price * (1 + (Math.random() - 0.5) * 0.01));
  }
}, 500);
setInterval(() => snapshots.push({ total_value: portfolio().total_value, recorded_at: new Date().toISOString() }), 2000);

const json = (res, obj, code = 200) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  const p = url.pathname;
  if (p === "/api/stream/prices") {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
    res.write("retry: 3000\n\n");
    const iv = setInterval(() => {
      for (const t of TICKERS) {
        const s = state[t];
        const ev = { ticker: t, price: +s.price.toFixed(4), prev_price: +s.prev.toFixed(4), open_price: s.open, change: +(s.price - s.open).toFixed(4), change_pct: +((s.price - s.open) / s.open).toFixed(6), direction: s.price > s.prev ? "up" : s.price < s.prev ? "down" : "flat", timestamp: Date.now() / 1000 };
        res.write(`event: price\ndata: ${JSON.stringify(ev)}\n\n`);
      }
    }, 500);
    req.on("close", () => clearInterval(iv));
    return;
  }
  if (p === "/api/portfolio") return json(res, portfolio());
  if (p === "/api/portfolio/history") return json(res, { snapshots });
  if (p === "/api/watchlist") return json(res, { tickers: TICKERS.map((t) => ({ ticker: t, price: state[t].price, prev_price: state[t].prev, open_price: state[t].open, change: state[t].price - state[t].open, change_pct: (state[t].price - state[t].open) / state[t].open, direction: "flat" })) });
  if (p === "/api/chat") return json(res, { message: "Your portfolio is up modestly, led by NVDA. Tech concentration is ~80% — consider diversifying.", actions: { trades: [], watchlist_changes: [] } });
  if (p.startsWith("/api/")) return json(res, { ok: true });

  // static files
  let file = path.join(root, p === "/" ? "index.html" : p);
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, "index.html");
  const ext = path.extname(file);
  const type = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".txt": "text/plain", ".json": "application/json" }[ext] || "application/octet-stream";
  res.writeHead(200, { "Content-Type": type });
  fs.createReadStream(file).pipe(res);
});
server.listen(8000, () => console.log("mock on :8000"));
