"""Anthropic client wrapper. Server-side only — the key never leaves this process.

The rest of the application talks to Claude exclusively through here, which
keeps three guarantees in one place: the key is read from the environment, every
call has a timeout and a graceful failure mode, and the product degrades to
deterministic output rather than breaking when AI is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import settings

logger = logging.getLogger("revenueos.ai")


class AIUnavailable(RuntimeError):
    """Raised when no API key is configured or the provider call fails."""


@dataclass
class AIResponse:
    text: str
    stop_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    model: str | None = None


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings.anthropic_api_key:
        raise AIUnavailable(
            "ANTHROPIC_API_KEY is not set. RevenueOS runs fully without it — "
            "all analytics are deterministic — but narrative AI answers are disabled."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise AIUnavailable(
            "The 'anthropic' package is not installed. Run: pip install anthropic"
        ) from exc
    _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    return _client


def is_available() -> bool:
    return bool(settings.anthropic_api_key)


def complete(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.2,
) -> AIResponse:
    """One round-trip to Claude. Raises ``AIUnavailable`` on any failure."""
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens or settings.anthropic_max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    try:
        response = client.messages.create(**kwargs)
    except Exception as exc:
        logger.warning("Anthropic call failed: %s", exc)
        raise AIUnavailable(f"The AI service could not be reached: {exc}") from exc

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
        elif getattr(block, "type", None) == "tool_use":
            tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

    return AIResponse(
        text="\n".join(text_parts).strip(),
        stop_reason=response.stop_reason,
        tool_calls=tool_calls or None,
        usage={
            "inputTokens": response.usage.input_tokens,
            "outputTokens": response.usage.output_tokens,
        },
        model=response.model,
    )
