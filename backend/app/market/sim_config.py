from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSpec:
    ticker: str
    seed_price: float
    sigma: float      # annualized volatility
    sector: str       # for correlation grouping


# The ten defaults match the watchlist seed in PLAN §7.
SEED: list[TickerSpec] = [
    TickerSpec("AAPL",  190.0, 0.28, "tech"),
    TickerSpec("GOOGL", 175.0, 0.30, "tech"),
    TickerSpec("MSFT",  420.0, 0.26, "tech"),
    TickerSpec("AMZN",  185.0, 0.34, "tech"),
    TickerSpec("TSLA",  250.0, 0.55, "tech"),
    TickerSpec("NVDA",  120.0, 0.50, "tech"),
    TickerSpec("META",  500.0, 0.36, "tech"),
    TickerSpec("JPM",   200.0, 0.24, "finance"),
    TickerSpec("V",     280.0, 0.22, "finance"),
    TickerSpec("NFLX",  650.0, 0.40, "tech"),
]
