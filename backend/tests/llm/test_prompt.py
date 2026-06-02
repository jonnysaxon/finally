"""Prompt / context construction (PLAN §9)."""

from app.llm.prompt import SYSTEM_PROMPT, build_messages, build_portfolio_context


def _portfolio():
    return {
        "cash_balance": 5000.0,
        "total_value": 7000.0,
        "positions_value": 2000.0,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10,
                "avg_cost": 150.0,
                "current_price": 190.0,
                "market_value": 1900.0,
                "unrealized_pnl": 400.0,
                "pnl_pct": 26.67,
            }
        ],
    }


def test_context_includes_numbers():
    ctx = build_portfolio_context(
        _portfolio(), [{"ticker": "AAPL", "price": 190.0, "change_pct": 0.05}]
    )
    assert "$5,000.00" in ctx
    assert "AAPL" in ctx
    assert "+5.00%" in ctx


def test_context_handles_empty():
    ctx = build_portfolio_context(
        {"cash_balance": 10000.0, "total_value": 10000.0, "positions_value": 0.0, "positions": []},
        [],
    )
    assert "Positions: none" in ctx
    assert "Watchlist: empty" in ctx


def test_context_handles_null_price():
    ctx = build_portfolio_context(
        {"cash_balance": 100.0, "total_value": 100.0, "positions_value": 0.0, "positions": []},
        [{"ticker": "NEW", "price": None, "change_pct": None}],
    )
    assert "NEW" in ctx
    assert "n/a" in ctx


def test_build_messages_structure():
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    messages = build_messages(_portfolio(), [], history, "new question")
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["role"] == "system"  # portfolio context
    assert messages[-1] == {"role": "user", "content": "new question"}
    # history is preserved in between
    assert {"role": "assistant", "content": "earlier answer"} in messages


def test_build_messages_skips_blank_history():
    history = [{"role": "user", "content": ""}, {"role": "system", "content": "x"}]
    messages = build_messages(_portfolio(), [], history, "q")
    # only the two leading system messages + final user message
    assert len(messages) == 3
