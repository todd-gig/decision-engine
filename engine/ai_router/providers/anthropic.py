"""Anthropic provider adapter for ai_router.

Uses the official `anthropic` SDK when ANTHROPIC_API_KEY is set; raises
RuntimeError if not configured (caller handles fallback chain).

The `call(...)` signature requires `prompt_version` + `schema_version` —
the chokepoint enforces CRIT-003 at the provider boundary as well as in
the public router; ai_router cannot itself drift on the rule it polices.

penrose_signal: weakens
penrose_dimension: provider_neutrality
"""
from __future__ import annotations

import os
from typing import Optional

from . import ProviderResponse

try:
    import anthropic as _anthropic
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


# Pricing per 1K tokens; updated alongside Anthropic price changes.
# Test asserts non-decreasing prices (we never silently undercharge).
PRICING = {
    "claude-opus-4-7":    {"in_per_1k": 0.015, "out_per_1k": 0.075},
    "claude-opus-4-6":    {"in_per_1k": 0.015, "out_per_1k": 0.075},
    "claude-sonnet-4-6":  {"in_per_1k": 0.003, "out_per_1k": 0.015},
    "claude-haiku-4-5":   {"in_per_1k": 0.001, "out_per_1k": 0.005},
}

_client: "Optional[object]" = None


def is_available() -> bool:
    return _AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> "object":
    global _client
    if _client is None:
        if not is_available():
            raise RuntimeError("Anthropic SDK or ANTHROPIC_API_KEY missing")
        _client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def reset_client_for_tests() -> None:
    """Allow tests to inject monkeypatched env without sticky client."""
    global _client
    _client = None


def call(
    *,
    prompt: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout_seconds: int = 30,
) -> ProviderResponse:
    """Invoke Anthropic; return ProviderResponse. Raises on SDK error.

    `prompt_version` + `schema_version` are required (CRIT-003): the
    chokepoint cannot itself drift on the rule it enforces. Both are
    forwarded into the SDK `metadata` envelope so they appear at the
    actual call site (where the drift scanner inspects).
    """
    if not prompt_version:
        raise ValueError("prompt_version is required (CRIT-003)")
    if not schema_version:
        raise ValueError("schema_version is required (CRIT-003)")
    client = _get_client()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
        metadata={
            "prompt_version": prompt_version,
            "schema_version": schema_version,
        },
    )
    text = msg.content[0].text if msg.content else ""
    usage = getattr(msg, "usage", None)
    in_tokens = getattr(usage, "input_tokens", None) if usage else None
    out_tokens = getattr(usage, "output_tokens", None) if usage else None
    return ProviderResponse(
        text=text,
        model_used=getattr(msg, "model", model),
        in_tokens=in_tokens,
        out_tokens=out_tokens,
    )


def cost_usd(model: str, in_tokens: int | None, out_tokens: int | None) -> float | None:
    """Compute USD cost from token counts. None when token counts unknown."""
    if in_tokens is None or out_tokens is None:
        return None
    pricing = PRICING.get(model)
    if pricing is None:
        return None
    return round(
        (in_tokens / 1000.0) * pricing["in_per_1k"]
        + (out_tokens / 1000.0) * pricing["out_per_1k"],
        6,
    )
