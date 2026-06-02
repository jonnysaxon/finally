from datetime import UTC, datetime, timedelta

from app.db import repository as repo

# --- users_profile -------------------------------------------------------------


def test_get_profile_returns_seeded_defaults(db):
    profile = repo.get_profile(db)
    assert profile["id"] == "default"
    assert profile["cash_balance"] == 10000.0
    assert "created_at" in profile


def test_get_profile_unknown_user_returns_empty(db):
    assert repo.get_profile(db, user_id="nobody") == {}


def test_update_cash(db):
    repo.update_cash(db, 12345.67)
    assert repo.get_profile(db)["cash_balance"] == 12345.67


# --- watchlist -----------------------------------------------------------------


def test_list_watchlist_returns_seeded_tickers(db):
    tickers = repo.list_watchlist(db)
    assert set(tickers) == {
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    }


def test_add_watchlist_appends(db):
    repo.add_watchlist(db, "PYPL")
    assert "PYPL" in repo.list_watchlist(db)


def test_add_watchlist_uppercases(db):
    repo.add_watchlist(db, "pypl")
    assert "PYPL" in repo.list_watchlist(db)


def test_add_watchlist_ignores_duplicate(db):
    before = len(repo.list_watchlist(db))
    repo.add_watchlist(db, "AAPL")  # already seeded
    assert len(repo.list_watchlist(db)) == before


def test_remove_watchlist_returns_true_when_removed(db):
    assert repo.remove_watchlist(db, "AAPL") is True
    assert "AAPL" not in repo.list_watchlist(db)


def test_remove_watchlist_returns_false_when_absent(db):
    assert repo.remove_watchlist(db, "NOPE") is False


# --- positions -----------------------------------------------------------------


def test_upsert_and_get_position(db):
    repo.upsert_position(db, "AAPL", 10, 190.0)
    pos = repo.get_position(db, "AAPL")
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 190.0
    assert "updated_at" in pos


def test_get_position_returns_none_when_absent(db):
    assert repo.get_position(db, "AAPL") is None


def test_upsert_position_updates_existing(db):
    repo.upsert_position(db, "AAPL", 10, 190.0)
    repo.upsert_position(db, "AAPL", 15, 195.0)
    pos = repo.get_position(db, "AAPL")
    assert pos["quantity"] == 15
    assert pos["avg_cost"] == 195.0
    # still one row (unique on user_id, ticker)
    assert len(repo.list_positions(db)) == 1


def test_upsert_position_uppercases(db):
    repo.upsert_position(db, "aapl", 5, 100.0)
    assert repo.get_position(db, "AAPL") is not None


def test_list_positions_ordered_by_ticker(db):
    repo.upsert_position(db, "TSLA", 1, 200.0)
    repo.upsert_position(db, "AAPL", 1, 190.0)
    tickers = [p["ticker"] for p in repo.list_positions(db)]
    assert tickers == ["AAPL", "TSLA"]


def test_delete_position(db):
    repo.upsert_position(db, "AAPL", 10, 190.0)
    repo.delete_position(db, "AAPL")
    assert repo.get_position(db, "AAPL") is None


# --- trades --------------------------------------------------------------------


def test_insert_trade_returns_full_row(db):
    trade = repo.insert_trade(db, "AAPL", "buy", 10, 190.0)
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 10
    assert trade["price"] == 190.0
    assert "id" in trade
    assert "executed_at" in trade


def test_insert_trade_persists(db):
    repo.insert_trade(db, "AAPL", "buy", 10, 190.0)
    trades = repo.list_trades(db)
    assert len(trades) == 1
    assert trades[0]["ticker"] == "AAPL"


def test_list_trades_newest_first(db):
    repo.insert_trade(db, "AAPL", "buy", 1, 100.0)
    repo.insert_trade(db, "MSFT", "buy", 1, 200.0)
    repo.insert_trade(db, "TSLA", "buy", 1, 300.0)
    trades = repo.list_trades(db)
    # newest first: TSLA inserted last
    assert trades[0]["ticker"] == "TSLA"


def test_list_trades_respects_limit(db):
    for i in range(5):
        repo.insert_trade(db, "AAPL", "buy", 1, 100.0 + i)
    assert len(repo.list_trades(db, limit=2)) == 2


# --- portfolio_snapshots -------------------------------------------------------


def test_insert_snapshot_persists(db):
    repo.insert_snapshot(db, 10000.0)
    snaps = repo.list_snapshots(db)
    assert len(snaps) == 1
    assert snaps[0]["total_value"] == 10000.0
    assert "recorded_at" in snaps[0]


def test_list_snapshots_ascending(db):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, val in enumerate([100.0, 200.0, 300.0]):
        ts = (base + timedelta(seconds=i)).isoformat()
        db.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
            "VALUES (?, 'default', ?, ?)",
            (f"id{i}", val, ts),
        )
    values = [s["total_value"] for s in repo.list_snapshots(db)]
    assert values == [100.0, 200.0, 300.0]


def test_insert_snapshot_prunes_older_than_7_days(db):
    old_ts = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES ('old', 'default', 999.0, ?)",
        (old_ts,),
    )
    repo.insert_snapshot(db, 10000.0)  # triggers prune
    values = [s["total_value"] for s in repo.list_snapshots(db)]
    assert 999.0 not in values
    assert 10000.0 in values


def test_insert_snapshot_keeps_recent(db):
    recent_ts = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES ('recent', 'default', 555.0, ?)",
        (recent_ts,),
    )
    repo.insert_snapshot(db, 10000.0)
    values = [s["total_value"] for s in repo.list_snapshots(db)]
    assert 555.0 in values


# --- chat_messages -------------------------------------------------------------


def test_insert_chat_message_user_no_actions(db):
    msg = repo.insert_chat_message(db, "user", "hello")
    assert msg["role"] == "user"
    assert msg["content"] == "hello"
    assert msg["actions"] is None


def test_insert_chat_message_with_actions_roundtrips(db):
    actions = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}]}
    repo.insert_chat_message(db, "assistant", "Bought AAPL", actions=actions)
    msgs = repo.list_chat_messages(db)
    assert msgs[-1]["actions"] == actions


def test_list_chat_messages_ascending(db):
    repo.insert_chat_message(db, "user", "first")
    repo.insert_chat_message(db, "assistant", "second")
    repo.insert_chat_message(db, "user", "third")
    contents = [m["content"] for m in repo.list_chat_messages(db)]
    assert contents == ["first", "second", "third"]


def test_list_chat_messages_limit_keeps_most_recent_ascending(db):
    for i in range(5):
        repo.insert_chat_message(db, "user", f"msg{i}")
    msgs = repo.list_chat_messages(db, limit=2)
    # most recent two, returned ascending
    assert [m["content"] for m in msgs] == ["msg3", "msg4"]


def test_chat_message_actions_stored_as_json_string(db):
    actions = {"watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}
    repo.insert_chat_message(db, "assistant", "added", actions=actions)
    raw = db.execute(
        "SELECT actions FROM chat_messages WHERE content='added'"
    ).fetchone()["actions"]
    assert isinstance(raw, str)


# --- user isolation ------------------------------------------------------------


def test_user_id_scoping_for_watchlist(db):
    repo.add_watchlist(db, "ZZZZ", user_id="other")
    assert "ZZZZ" not in repo.list_watchlist(db)  # default user
    assert "ZZZZ" in repo.list_watchlist(db, user_id="other")
