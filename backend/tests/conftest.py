"""Project-wide test guards.

The canonical command `uv run pytest` (with no LLM_MOCK in the environment) must
never hang and must never touch the network. The chat code path, when LLM_MOCK is
not enabled, would call `app.llm.client.complete_chat` -> `litellm.completion` and
block on a real socket to OpenRouter.

This session-wide autouse guard stubs `app.llm.client.complete_chat` to RAISE, so
any accidental real LLM call during a unit test fails loudly and instantly instead
of hanging. Tests that intentionally drive the chat pipeline set LLM_MOCK=true
(deterministic, offline) or patch `complete_chat` themselves; in both cases the
real client is never reached, so the guard stays dormant. Tests that specifically
exercise the real-client parsing path re-patch `complete_chat`, and because that
monkeypatch runs after this autouse fixture, it wins.

This file is intentionally minimal and shared: it only installs the no-network
guard. Per-area fixtures live in each subpackage's own conftest.
"""

import pytest


@pytest.fixture(autouse=True)
def _block_llm_network(monkeypatch):
    try:
        from app.llm import client
    except Exception:
        # LLM module not importable in this environment/run — nothing to guard.
        return

    def _blocked(messages):  # pragma: no cover - only hit on a misconfigured test
        raise RuntimeError(
            "app.llm.client.complete_chat was called during a unit test — the "
            "network is blocked. Set LLM_MOCK=true or patch complete_chat."
        )

    monkeypatch.setattr(client, "complete_chat", _blocked)
