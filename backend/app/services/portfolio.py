"""Portfolio business rules: trade execution and valuation (PLAN §7, §13.5-13.7).

These functions are the single source of trade/valuation logic, used by BOTH the
REST trade endpoint and the LLM auto-executor. They depend only on the repository
layer (no raw SQL here) and the PriceCache (for current prices).
"""

from ..db import repository
from ..market.cache import PriceCache


class TradeError(Exception):
    """A trade failed validation. The message is user-safe and surfaced verbatim
    in the API 400 response and the chat panel."""


def _value_position(ticker: str, quantity: float, avg_cost: float, price: float | None) -> dict:
    """Build a fully valued position dict from a holding and the current price.

    A position with no cached price yet (price is None) reports current_price=None
    and zeroed market value / P&L — it cannot be valued until its first tick. This
    is the single valuation formula used by both execute_trade and build_portfolio.
    """
    if price is None:
        market_value = 0.0
        unrealized_pnl = 0.0
        pnl_pct = 0.0
    else:
        market_value = price * quantity
        cost_basis = avg_cost * quantity
        unrealized_pnl = market_value - cost_basis
        pnl_pct = (unrealized_pnl / cost_basis) if cost_basis else 0.0
    return {
        "ticker": ticker,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "current_price": price,
        "market_value": market_value,
        "unrealized_pnl": unrealized_pnl,
        "pnl_pct": pnl_pct,
    }


def execute_trade(
    db,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
    user_id: str = "default",
) -> dict:
    """Validate and execute a market order at the current cache price. Atomic.

    - price = cache.get_price(ticker); TradeError if no price yet.
    - buy: cost = price*qty; TradeError if cost > cash. Update cash, weighted-avg
      cost (PLAN §13.6).
    - sell: TradeError if qty > held (no shorting, PLAN §13.5). Reduce qty; delete
      the row at 0 (PLAN §13.7). avg_cost is unchanged on a sell.
    - Inserts a trade row and writes a fresh portfolio snapshot (PLAN §7).

    Returns {"trade": {...}, "position": {...}|None, "cash_balance": float}, where
    `position` is the fully valued post-trade holding (same shape as a
    build_portfolio entry: ticker, quantity, avg_cost, current_price, market_value,
    unrealized_pnl, pnl_pct) or None when the position was closed out.
    Raises TradeError on any validation failure.
    """
    ticker = ticker.upper()
    side = side.lower()
    if side not in ("buy", "sell"):
        raise TradeError(f"Invalid side '{side}'; must be 'buy' or 'sell'")
    if quantity <= 0:
        raise TradeError("Quantity must be greater than zero")

    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker}")

    profile = repository.get_profile(db, user_id)
    cash = profile["cash_balance"]
    existing = repository.get_position(db, ticker, user_id)

    if side == "buy":
        cost = price * quantity
        if cost > cash:
            raise TradeError(
                f"Insufficient cash: need ${cost:,.2f}, have ${cash:,.2f}"
            )
        if existing:
            old_qty = existing["quantity"]
            old_avg = existing["avg_cost"]
            new_qty = old_qty + quantity
            new_avg = (old_qty * old_avg + quantity * price) / new_qty
        else:
            new_qty = quantity
            new_avg = price
        new_cash = cash - cost
        repository.upsert_position(db, ticker, new_qty, new_avg, user_id)
        position = _value_position(ticker, new_qty, new_avg, price)
    else:  # sell
        held = existing["quantity"] if existing else 0.0
        if quantity > held:
            raise TradeError(
                f"Cannot sell {quantity} {ticker}: only {held} held (no shorting)"
            )
        proceeds = price * quantity
        new_cash = cash + proceeds
        new_qty = held - quantity
        if new_qty <= 0:
            repository.delete_position(db, ticker, user_id)
            position = None
        else:
            # avg_cost unchanged on a sell (PLAN §13.6).
            repository.upsert_position(db, ticker, new_qty, existing["avg_cost"], user_id)
            position = _value_position(ticker, new_qty, existing["avg_cost"], price)

    repository.update_cash(db, new_cash, user_id)
    trade = repository.insert_trade(db, ticker, side, quantity, price, user_id)

    # Snapshot total value immediately after the trade (PLAN §7). Reads see the
    # uncommitted writes above (same connection), so the snapshot is correct.
    total_value = compute_total_value(db, cache, user_id)
    repository.insert_snapshot(db, total_value, user_id)

    # Caller owns the commit (BUILD_CONTRACT): the request-scoped get_db commits on
    # clean exit; the LLM auto-executor and the snapshot task commit their own
    # connections. All writes here ran on the one passed connection, so they
    # commit atomically together.
    return {"trade": trade, "position": position, "cash_balance": new_cash}


def build_portfolio(db, cache: PriceCache, user_id: str = "default") -> dict:
    """Full portfolio snapshot for the API/LLM context.

    Returns {cash_balance, total_value, positions_value, positions:[...]}, where
    each position carries current_price/market_value/unrealized_pnl/pnl_pct from
    the live cache. A position with no cached price yet reports current_price=None
    and zeroed market value/P&L (it cannot be valued until its first tick).
    """
    profile = repository.get_profile(db, user_id)
    cash = profile["cash_balance"]

    positions = []
    positions_value = 0.0
    for row in repository.list_positions(db, user_id):
        price = cache.get_price(row["ticker"])
        position = _value_position(row["ticker"], row["quantity"], row["avg_cost"], price)
        positions_value += position["market_value"]
        positions.append(position)

    total_value = cash + positions_value
    return {
        "cash_balance": cash,
        "total_value": total_value,
        "positions_value": positions_value,
        "positions": positions,
    }


def compute_total_value(db, cache: PriceCache, user_id: str = "default") -> float:
    """Cash + market value of all positions (priceless positions contribute 0)."""
    profile = repository.get_profile(db, user_id)
    total = profile["cash_balance"]
    for row in repository.list_positions(db, user_id):
        price = cache.get_price(row["ticker"])
        if price is not None:
            total += price * row["quantity"]
    return total
