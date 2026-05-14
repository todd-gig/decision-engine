"""Pricing bridge — adapts GigatonClient for decision-engine gate consumption.

Wraps the stdlib HTTP client from `gigaton_client.py` (sibling of this
engine package) with decision-domain helpers:

  - `is_pricing_decision(decision)` — heuristic that detects whether a
    DecisionObject's domain warrants a pricing-engine consultation.
  - `get_pricing_signal(decision)` — invokes gigaton-engine and returns
    a normalized envelope (`status`, `signal`, `engine_response`,
    `consulted_at`). Never raises — failure modes degrade to
    `{"status": "unavailable", "reason": "..."}` so callers can fall
    back without try/except plumbing.

v0 — observational only. Gates can attach the pricing signal to a
decision's evidence chain without blocking. v0.5 wires the signal into
gate-4 (reversibility) and gate-5 (risk containment) as input to the
margin-governance check (per CLAUDE.md B-05).

Reference: gigaton_client.py (sibling), engine/gates.py (caller surface).
"""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Add parent directory so `import gigaton_client` resolves outside `engine/`.
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from gigaton_client import GigatonClient, GigatonClientError  # noqa: E402

from engine.models import DecisionObject  # noqa: E402

logger = logging.getLogger(__name__)


# Token patterns that suggest the decision touches pricing / margin / rates.
_PRICING_TOKEN_RE = re.compile(
    r"\b(pric(?:e|ing)|rate|margin|markup|discount|fee|cost|adr|revpar|"
    r"yield|tariff|nightly|quote|payout)\b",
    re.IGNORECASE,
)


def is_pricing_decision(decision: DecisionObject) -> bool:
    """Return True if the decision likely warrants a pricing-engine consult.

    Heuristic over `requested_action`, `title`, `problem_statement`, and
    `decision_class.name`. Conservative: a True from this function is a
    signal, not a guarantee — callers decide whether to actually consult.
    """
    haystack_parts: list[str] = []
    for attr in ("requested_action", "title", "problem_statement"):
        v = getattr(decision, attr, None)
        if isinstance(v, str):
            haystack_parts.append(v)
    decision_class = getattr(decision, "decision_class", None)
    if decision_class is not None:
        name = getattr(decision_class, "name", "") or ""
        haystack_parts.append(str(name))

    haystack = " ".join(haystack_parts)
    return bool(_PRICING_TOKEN_RE.search(haystack))


def get_pricing_signal(
    decision: DecisionObject,
    *,
    client: Optional[GigatonClient] = None,
) -> dict[str, Any]:
    """Consult gigaton-engine for pricing input on a decision.

    Returns a normalized envelope:
      - `status`: "ok" | "unavailable" | "skipped"
      - `signal`: short-form summary (None when status != "ok")
      - `engine_response`: raw dict from gigaton-engine (None when status != "ok")
      - `consulted_at`: ISO8601 timestamp (always set)
      - `reason`: explanation when status != "ok"

    Never raises. Disabled when env var `DECISION_PRICING_BRIDGE_ENABLED` is
    set to "0" (default "1") — lets ops kill the bridge without redeploying.
    """
    now = datetime.now(tz=timezone.utc).isoformat()

    if os.environ.get("DECISION_PRICING_BRIDGE_ENABLED", "1") == "0":
        return {
            "status": "skipped",
            "signal": None,
            "engine_response": None,
            "consulted_at": now,
            "reason": "DECISION_PRICING_BRIDGE_ENABLED=0",
        }

    if not is_pricing_decision(decision):
        return {
            "status": "skipped",
            "signal": None,
            "engine_response": None,
            "consulted_at": now,
            "reason": "decision domain does not match pricing heuristics",
        }

    payload = _build_pricing_payload(decision)
    cl = client or GigatonClient()

    try:
        response = cl.get_pricing(payload)
    except GigatonClientError as exc:
        logger.warning(
            "pricing_bridge: gigaton-engine returned HTTP %s for decision %s",
            exc.status_code,
            getattr(decision, "decision_id", "?"),
        )
        return {
            "status": "unavailable",
            "signal": None,
            "engine_response": None,
            "consulted_at": now,
            "reason": f"gigaton-engine HTTP {exc.status_code}: {exc.body[:200]}",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pricing_bridge: unexpected error consulting gigaton-engine: %s",
            exc,
        )
        return {
            "status": "unavailable",
            "signal": None,
            "engine_response": None,
            "consulted_at": now,
            "reason": f"unexpected error: {exc!s}",
        }

    return {
        "status": "ok",
        "signal": _summarize_signal(response),
        "engine_response": response,
        "consulted_at": now,
        "reason": None,
    }


def _build_pricing_payload(decision: DecisionObject) -> dict[str, Any]:
    """Construct the gigaton-engine /pricing/quote payload from a decision.

    v0 — minimal: forwards the decision id + action text + any explicit
    `evidence_refs` that look like property ids or date ranges. v0.5 wires
    explicit fields once gigaton-engine documents a stable schema.
    """
    return {
        "source": "decision-engine",
        "decision_id": str(getattr(decision, "decision_id", "")),
        "decision_class": getattr(
            getattr(decision, "decision_class", None), "name", "unknown"
        ),
        "requested_action": getattr(decision, "requested_action", ""),
        "title": getattr(decision, "title", ""),
        "evidence_refs": list(getattr(decision, "evidence_refs", []) or [])[:10],
    }


def _summarize_signal(response: dict[str, Any]) -> dict[str, Any]:
    """Extract a stable subset of the engine response for evidence-chain use."""
    keys_of_interest = (
        "nightly_rate",
        "margin",
        "recommendation",
        "confidence",
        "guard_rail_status",
        "warning",
    )
    return {k: response[k] for k in keys_of_interest if k in response}
