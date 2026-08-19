"""Anthropic client factory.

The key is read from the environment on the server and never leaves it. If no
key is configured the application still runs: every AI surface falls back to a
deterministic, data-derived summary that is clearly labelled as such, so nothing
in the product pretends to be reasoning when it is not.
"""
from __future__ import annotations

import os
from functools import lru_cache

MODEL = "claude-opus-5"
MAX_TOKENS = 16000


@lru_cache(maxsize=1)
def _client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is declared
        return None
    return anthropic.Anthropic(api_key=api_key)


def get_client():
    return _client()


def is_available() -> bool:
    return _client() is not None


def status() -> dict[str, object]:
    return {
        "available": is_available(),
        "model": MODEL if is_available() else None,
        "reason": None if is_available()
        else "ANTHROPIC_API_KEY is not set on the server. RevenueOS still computes every "
             "metric and shows deterministic summaries; conversational answers need the key.",
    }
