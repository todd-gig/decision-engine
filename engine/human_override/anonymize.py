"""Anonymization helpers for cross-org views.

Per spec decision #11: "No personal-identifying details in cross-org
views — anonymized. Why: privacy boundary mirrors Network Intelligence
Layer doctrine; aggregate signal valuable; identity disclosure is opt-in
escalation."

We hash overrider_user_id with HMAC-SHA256 keyed on `OVERRIDE_ANON_SALT`
(falls back to a deterministic dev salt). The hash is *stable* — same
input → same output — so cross-org consumers can still count "how many
overrides did this anonymous person do" without learning who they are.

penrose_signal: weakens
penrose_dimension: override_rate
why: Cross-org pattern sharing is how Penrose-falsification scales —
one operator's correction informs another org's calibration. Privacy is
the constraint that lets that sharing happen. Without anonymization the
cross-org view leaks user identity; with anonymization it's a
super-additive signal source.
"""
from __future__ import annotations

import hashlib
import hmac
import os


_DEFAULT_DEV_SALT = "dev-only-override-anon-salt"


def _salt() -> bytes:
    return os.environ.get("OVERRIDE_ANON_SALT", _DEFAULT_DEV_SALT).encode("utf-8")


def hash_user_id(user_id: str) -> str:
    """Return a stable HMAC-SHA256 hash of a user id for cross-org sharing.

    The output is hex-encoded and truncated to 16 chars — enough collision
    resistance for a cross-org grouping key, short enough to read in a UI.
    """
    if not user_id:
        return ""
    digest = hmac.new(_salt(), user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"anon:{digest[:16]}"


def redact_row(row: dict) -> dict:
    """Return a shallow copy of `row` with overrider_user_id hashed."""
    redacted = dict(row)
    if "overridden_by_user_id" in redacted:
        redacted["overridden_by_user_id"] = hash_user_id(
            redacted["overridden_by_user_id"] or ""
        )
    return redacted
