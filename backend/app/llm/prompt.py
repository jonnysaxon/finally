"""System prompt + conversation/context construction for the chat LLM (PLAN §9).

`build_messages` assembles the LiteLLM `messages` list:
  [system, <portfolio context as system>, ...recent history..., new user message]

The context is rendered as compact, data-dense text rather than raw JSON so the
model spends its attention on the numbers, not on punctuation.
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are FinAlly, an AI trading assistant embedded in a simulated trading "
    "workstation.\n\n"
    "You help the user understand and manage a virtual portfolio (fake money, zero "
    "real-world stakes). You can:\n"
    "- Analyze portfolio composition, risk concentration, diversification, and P&L.\n"
    "- Suggest trades with clear, data-driven reasoning.\n"
    "- Execute trades when the user asks or agrees (market orders, instant fill at "
    "the current price).\n"
    "- Manage the watchlist proactively (add/remove tickers).\n\n"
    "Rules:\n"
    "- Be concise and data-driven. Reference the user's actual numbers.\n"
    "- Only emit a trade in `trades` when the user is asking to trade or has agreed "
    "to a suggestion. Do not trade unprompted.\n"
    "- For buys, respect available cash; for sells, the user cannot sell more shares "
    "than they hold (no shorting). If a request is not feasible, say so in `message` "
    "and omit the action.\n"
    "- Quantities are share counts (fractional allowed) and must be positive.\n"
    "- Watchlist additions are validated against symbols the data source knows; "
    "unknown symbols will be rejected.\n"
    "- Always respond with valid JSON matching the required schema: a `message` "
    "string, plus optional `trades` and `watchlist_changes` arrays. When you have no "
    "actions, return empty arrays.\n"
)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def build_portfolio_context(portfolio: dict, watchlist: list[dict]) -> str:
    """Render the live portfolio + watchlist snapshot as a compact text block.

    `portfolio` is the dict from services.portfolio.build_portfolio.
    `watchlist` is a list of {ticker, price, change_pct, ...} (price may be None
    if a ticker has not ticked yet).
    """
    lines: list[str] = ["PORTFOLIO SNAPSHOT"]
    lines.append(f"Cash: {_fmt_money(portfolio.get('cash_balance'))}")
    lines.append(f"Total value: {_fmt_money(portfolio.get('total_value'))}")
    lines.append(f"Positions value: {_fmt_money(portfolio.get('positions_value'))}")

    positions = portfolio.get("positions") or []
    if positions:
        lines.append("Positions (ticker qty avg_cost current mkt_value unrealized_pnl pnl%):")
        for p in positions:
            lines.append(
                "  {ticker} {qty:g} @ {avg} -> {cur} | mkt {mkt} | "
                "P&L {pnl} ({pct:+.2f}%)".format(
                    ticker=p.get("ticker"),
                    qty=p.get("quantity", 0),
                    avg=_fmt_money(p.get("avg_cost")),
                    cur=_fmt_money(p.get("current_price")),
                    mkt=_fmt_money(p.get("market_value")),
                    pnl=_fmt_money(p.get("unrealized_pnl")),
                    pct=(p.get("pnl_pct") or 0.0),
                )
            )
    else:
        lines.append("Positions: none")

    if watchlist:
        lines.append("Watchlist (ticker current change%):")
        for w in watchlist:
            price = w.get("price")
            pct = w.get("change_pct")
            pct_str = f"{pct * 100:+.2f}%" if isinstance(pct, (int, float)) else "n/a"
            lines.append(f"  {w.get('ticker')} {_fmt_money(price)} {pct_str}")
    else:
        lines.append("Watchlist: empty")

    return "\n".join(lines)


def build_messages(
    portfolio: dict,
    watchlist: list[dict],
    history: list[dict],
    user_message: str,
) -> list[dict]:
    """Assemble the messages list for the LLM call.

    `history` is the last-N chat_messages (ascending), each {role, content, ...}.
    The new `user_message` is appended last.
    """
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": build_portfolio_context(portfolio, watchlist)},
    ]
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages
