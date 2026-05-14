"""ai_router — single chokepoint for every production LLM call.

Per specs/ai_routing_engine_v0.md. v0 ships as a sub-package of
decision-engine; graduates to standalone Cloud Run service when:
  - ≥ 5 engines integrated, OR
  - > 10K calls/day, OR
  - Provider failover latency starts impacting calling engine SLO

Public surface:
    from engine.ai_router import invoke, InvokeResult, ProviderUnavailable

Enforces CRIT-003 (prompt_version + schema_version) and CRIT-007
(provider + model) on every call. Every invocation writes a signed
audit row to llm_audit table.
"""
from __future__ import annotations

from .router import (
    InvokeResult,
    ProviderUnavailable,
    invoke,
)

__all__ = ["invoke", "InvokeResult", "ProviderUnavailable"]
