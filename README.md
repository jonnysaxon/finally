# FinAlly — AI Trading Workstation

A visually rich, AI-powered trading workstation. Stream live market data, trade a
simulated portfolio, and chat with an LLM copilot that can analyze positions and
execute trades on your behalf. Think Bloomberg terminal with an AI assistant.

This is the capstone project for an agentic AI coding course, built end-to-end by
coding agents that collaborate through files in `planning/`.

## Features

- Live-streaming watchlist with price-flash animations and sparklines
- Simulated portfolio starting at $10,000 — instant market-order buys and sells
- Portfolio heatmap, P&L chart, and positions table
- AI chat assistant that analyzes the portfolio and executes trades via natural language
- No login, no signup — open the browser and trade

## Architecture

Single Docker container on port 8000:

- **Frontend** — Next.js (TypeScript), static export served by FastAPI
- **Backend** — FastAPI (Python, managed with `uv`)
- **Database** — SQLite at `db/finally.db` (bind-mounted, auto-initialized)
- **Real-time** — Server-Sent Events for price streaming
- **Market data** — built-in simulator by default; real data via Massive API if a key is set
- **AI** — LiteLLM → OpenRouter (Cerebras) with structured outputs

See [`planning/PLAN.md`](planning/PLAN.md) for the full specification.

## Quick Start

```bash
cp .env.example .env        # add your OPENROUTER_API_KEY
./scripts/start_mac.sh      # build + run the container, then open http://localhost:8000
```

Stop with `./scripts/stop_mac.sh` (Windows: `start_windows.ps1` / `stop_windows.ps1`).
Data persists in `db/finally.db`; delete it to start fresh.

## Configuration

Set in `.env` (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Required — enables the AI chat assistant |
| `MASSIVE_API_KEY` | Optional — use real market data instead of the simulator |
| `LLM_MODEL` | LLM used for chat (default `openrouter/openai/gpt-oss-120b`) |
| `LLM_MOCK` | Set `true` for deterministic mock responses (testing) |

## Project Status

In active development. The shared specification lives in `planning/PLAN.md`.
