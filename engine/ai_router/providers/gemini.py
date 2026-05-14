"""Gemini provider adapter — v0 stub.

Not wired yet. Raises NotImplementedError so fallback-chain logic in
router.py can distinguish "provider missing" from "provider failed".
"""
from __future__ import annotations

from . import ProviderResponse


PRICING = {
    "gemini-2-5-pro":     {"in_per_1k": 0.00125, "out_per_1k": 0.005},
    "gemini-2-5-flash":   {"in_per_1k": 0.000075, "out_per_1k": 0.0003},
}


def is_available() -> bool:
    return False  # v0: not wired


def call(**kwargs) -> ProviderResponse:
    raise NotImplementedError("Gemini provider not wired in v0 of ai_router")


def cost_usd(model: str, in_tokens: int | None, out_tokens: int | None) -> float | None:
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
