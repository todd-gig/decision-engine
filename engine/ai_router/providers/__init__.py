"""Provider adapters. Each provider defines a `call()` that returns
ProviderResponse and a PRICING dict for cost accounting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderResponse:
    text: str
    model_used: str
    in_tokens: Optional[int]
    out_tokens: Optional[int]
    error: Optional[str] = None
