"""HME event emitter — fire gamification events from decision-engine.

When a decision-engine pipeline finishes, this module emits a gamification
event to HME (Human Management Engine) via the gateway. Closes the loop
between decision-engine execution and HME's coaching / analysis / weekly
reports — users get credit for the decisions they shepherd through the
authorization gates.

Event-type mapping per HME's GAMIFICATION_EVENT_TYPES enum:
  - AUTO_EXECUTE         → InitiativeAdvanced
  - ESCALATE_TIER_*      → InitiativeProgressed (still moving forward,
                            just needs review)
  - BLOCK / NEEDS_DATA   → no event (no positive forward motion)

Design:
  - Fire-and-forget HTTP POST to GATEWAY_URL/v1/events
  - Stdlib-only (urllib.request) — no httpx dep added
  - Identity token via metadata server (same pattern as gigaton_client)
  - Silent failure: any error returns False and is logged; decision
    pipeline is NEVER blocked by HME unavailability
  - Disabled when GATEWAY_URL is unset (local dev / tests)
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


# UUID adjacent to "initiative" keyword — used to detect initiative-related decisions
_INITIATIVE_UUID_RE = re.compile(
    r"initiative[\s_:/-]*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def infer_initiative_id(*texts: Optional[str]) -> Optional[str]:
    """Scan text for an initiative_id UUID adjacent to 'initiative' keyword."""
    for t in texts:
        if not t:
            continue
        m = _INITIATIVE_UUID_RE.search(t)
        if m:
            return m.group(1)
    return None


def emit_initiative_webhook(
    *,
    initiative_id: str,
    decision_id: str,
    to_stage: str = "IN_PROGRESS",
    reasoning: str = "decision-engine AUTO_EXECUTE",
    decision_certificate_id: Optional[str] = None,
) -> bool:
    """POST /v1/webhooks/inferred-transition for an initiative-related decision.

    Fire-and-forget. Never raises. Returns True on 2xx, False on any failure.
    """
    gateway_url = os.environ.get("GATEWAY_URL") or os.environ.get("HME_EVENTS_URL")
    if not gateway_url:
        return False
    if os.environ.get("DECISION_HME_EMIT_DISABLED") == "1":
        return False

    payload = {
        "initiative_id": initiative_id,
        "to_stage": to_stage,
        "reasoning": f"[decision-engine {decision_id}] {reasoning}",
        "source_engine": "decision-engine",
    }
    if decision_certificate_id:
        payload["decision_certificate_id"] = decision_certificate_id

    url = gateway_url.rstrip("/") + "/v1/webhooks/inferred-transition"
    headers = {"Content-Type": "application/json"}

    token = _identity_token(gateway_url)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        logger.info(
            "hme_event_emitter: webhook %s for initiative %s failed: %s",
            url, initiative_id, exc,
        )
        return False
    except Exception:  # noqa: BLE001
        return False


_VERDICT_TO_EVENT_TYPE = {
    "AUTO_EXECUTE": "InitiativeAdvanced",
    "ESCALATE_TIER_1": "InitiativeProgressed",
    "ESCALATE_TIER_2": "InitiativeProgressed",
    "ESCALATE_TIER_3": "InitiativeProgressed",
    # BLOCK / NEEDS_DATA produce no event (caller checks for None return)
}


def emit_decision_event(
    *,
    decision_id: str,
    verdict: str,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    decision_class: Optional[str] = None,
    requested_action: Optional[str] = None,
) -> bool:
    """Fire a gamification event for a decision pipeline outcome.

    Returns True on successful submit (HTTP 2xx), False on any failure
    (including no-event verdicts like BLOCK).

    Never raises — pipeline must not be affected by HME availability.
    """
    event_type = _VERDICT_TO_EVENT_TYPE.get(verdict)
    if event_type is None:
        return False  # BLOCK / NEEDS_DATA — no positive event to emit

    gateway_url = os.environ.get("GATEWAY_URL") or os.environ.get("HME_EVENTS_URL")
    if not gateway_url:
        return False  # disabled in local dev / tests
    if os.environ.get("DECISION_HME_EMIT_DISABLED") == "1":
        return False  # kill-switch for ops

    # Caller is responsible for providing a UUID-shaped user_id. Pipeline
    # doesn't always carry one, so we emit on a sentinel zero-uuid in that
    # case; HME accepts it (validated against UUID format, not membership).
    if not user_id:
        user_id = "00000000-0000-0000-0000-000000000000"

    payload = {
        "user_id": user_id,
        "event_type": event_type,
        "source_engine": "decision-engine",
        "event_payload": {
            "decision_id": decision_id,
            "verdict": verdict,
            "decision_class": decision_class,
            "requested_action": (requested_action or "")[:300],  # cap size
        },
    }
    if org_id:
        payload["org_id"] = org_id

    url = gateway_url.rstrip("/") + "/v1/events"
    headers = {"Content-Type": "application/json"}

    token = _identity_token(gateway_url)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.info(
            "hme_event_emitter: HTTP %s emitting %s for %s",
            exc.code, event_type, decision_id,
        )
        return False
    except urllib.error.URLError as exc:
        logger.info(
            "hme_event_emitter: network error emitting %s for %s: %s",
            event_type, decision_id, exc.reason,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "hme_event_emitter: unexpected error: %s",
            exc,
        )
        return False


def _identity_token(audience: str) -> Optional[str]:
    """Fetch GCP identity token via metadata server (Cloud Run pattern).

    Pattern from gigaton_client.py — google-auth's id_token.fetch_id_token
    doesn't work for Cloud Run-attached SAs without a key file. Metadata
    server is the documented path.
    """
    if os.environ.get("DECISION_HME_DISABLE_OIDC") == "1":
        return None
    try:
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            f"service-accounts/default/identity?audience={audience}",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode("utf-8")
        return body or None
    except Exception:
        return None
