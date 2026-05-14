"""OpenAI provider adapter — v0 stub.

Not wired yet. Raises NotImplementedError so fallback-chain logic in
router.py can distinguish "provider missing" from "provider failed".

Pricing table is populated so cost-accounting tests can verify shape
without an SDK installed.
"""
from __future__ import annotations

from . import ProviderResponse


PRICING = {
    "gpt-5":                {"in_per_1k": 0.005, "out_per_1k": 0.015},
    "gpt-5-mini":           {"in_per_1k": 0.0015, "out_per_1k": 0.006},
    "gpt-4-turbo":          {"in_per_1k": 0.010, "out_per_1k": 0.030},
    "gpt-4o":               {"in_per_1k": 0.005, "out_per_1k": 0.015},
}


def is_available() -> bool:
    return False  # v0: not wired


def call(**kwargs) -> ProviderResponse:
    raise NotImplementedError("OpenAI provider not wired in v0 of ai_router")


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
