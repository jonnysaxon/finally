"""The LLM call itself: LiteLLM -> OpenRouter with the Cerebras provider.

Follows the project's `cerebras` skill exactly: model from `LLM_MODEL`
(default openrouter/openai/gpt-oss-120b), Cerebras forced via extra_body, and
Structured Outputs via `response_format=ChatResponse`.

The call is synchronous (LiteLLM `completion`); the async service offloads it to
a thread so it never blocks the event loop.
"""

from __future__ import annotations

import os

from .schema import ChatResponse

DEFAULT_MODEL = "openrouter/openai/gpt-oss-120b"
# Force OpenRouter to route to the Cerebras inference provider (cerebras skill).
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


def get_model() -> str:
    """Resolve the chat model from env, defaulting to the documented value."""
    return os.environ.get("LLM_MODEL") or DEFAULT_MODEL


def complete_chat(messages: list[dict]) -> str:
    """Call the LLM and return the raw response content string.

    Requests Structured Outputs against `ChatResponse`. Returns the raw JSON
    text; the caller validates/parses it (so it can fall back to raw on a parse
    failure per PLAN §13.10). litellm is imported lazily so importing this module
    (and running mock-mode tests) needs no network/runtime dependency loaded.
    """
    from litellm import completion

    response = completion(
        model=get_model(),
        messages=messages,
        response_format=ChatResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    return response.choices[0].message.content
