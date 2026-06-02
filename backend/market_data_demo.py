"""
Live market data demo — runs the simulator and displays a live dashboard.

Usage:
    cd backend
    uv run market_data_demo.py

Requires: rich (included in dev dependencies)
Runs for 60 seconds or until Ctrl+C.
"""
import asyncio
import sys
import time

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
except ImportError:
    print("Install rich: uv add --dev rich")
    sys.exit(1)

from app.market.cache import PriceCache
from app.market.simulator import SimulatorSource
from app.market.sim_config import SEED

DURATION = 60


def make_table(cache: PriceCache) -> Table:
    table = Table(title="FinAlly Market Simulator", show_header=True, header_style="bold cyan")
    table.add_column("Ticker", style="bold white", width=8)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Change%", justify="right", width=10)
    table.add_column("Direction", justify="center", width=10)

    for q in sorted(cache.all().values(), key=lambda x: x.ticker):
        color = "green" if q.direction == "up" else ("red" if q.direction == "down" else "white")
        arrow = "▲" if q.direction == "up" else ("▼" if q.direction == "down" else "─")
        pct = f"{q.change_pct * 100:+.2f}%"
        table.add_row(
            q.ticker,
            Text(f"${q.price:.2f}", style=color),
            Text(pct, style=color),
            Text(arrow, style=color),
        )
    return table


async def main() -> None:
    cache = PriceCache()
    src = SimulatorSource(cache, seed=None)
    task = asyncio.create_task(src.run())

    console = Console()
    start = time.time()

    try:
        with Live(console=console, refresh_per_second=4) as live:
            while time.time() - start < DURATION:
                live.update(make_table(cache))
                await asyncio.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    console.print("[bold green]Demo finished.[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
