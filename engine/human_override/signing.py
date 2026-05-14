"""HMAC-SHA256 chain signing for OverrideEvent rows.

Each override row is signed across canonical fields so tampering can be
detected on read. The HMAC key is read from env `OVERRIDE_HMAC_KEY` with
a deterministic dev default; production must set the env explicitly.

penrose_signal: weakens
penrose_dimension: override_rate
why: Without tamper-evident signatures, override events are mutable logs
that an adversary (or sloppy migration) can quietly rewrite. The
Penrose-falsification instrument for Override Rate requires append-only
HMAC-chained events so the rate trend is provably from real human
corrections, not from rewritten history.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from .recorder import OverrideRecord


_DEFAULT_DEV_KEY = "dev-only-override-hmac-key-do-not-use-in-prod"


def _hmac_key() -> bytes:
    """Resolve the HMAC key. Production reads `OVERRIDE_HMAC_KEY`; falls
    back to the same `LLM_AUDIT_HMAC_KEY` used by ai_router/audit so a
    single rotation rotates both surfaces; final fallback is a deterministic
    dev key so local tests work without env wiring.
    """
    key = os.environ.get("OVERRIDE_HMAC_KEY")
    if key:
        return key.encode("utf-8")
    # Reuse the existing audit key when present — single rotation surface.
    key = os.environ.get("LLM_AUDIT_HMAC_KEY")
    if key:
        return key.encode("utf-8")
    return _DEFAULT_DEV_KEY.encode("utf-8")


# Canonical signable fields — match storage.py columns that are
# tamper-relevant. Excludes the signature itself and freeform_metadata
# (free-form caller info; signed via hash below).
_CANONICAL_FIELDS: tuple[str, ...] = (
    "override_id",
    "decision_id",
    "decision_certificate_id",
    "override_type",
    "overridden_by_user_id",
    "overridden_at",
    "source_engine",
    "surface",
    "original_action",
    "override_action",
    "user_reasoning",
)


def _canonical_payload(record: OverrideRecord) -> str:
    """Stable canonical string over which we sign.

    Free-form metadata is hashed (not embedded raw) so signature length
    is bounded; tamper-detection still works because any metadata change
    changes the hash.
    """
    parts: list[str] = []
    for field in _CANONICAL_FIELDS:
        value = getattr(record, field)
        parts.append(f"{field}={value!r}")
    meta = record.freeform_metadata or {}
    if meta:
        # Sort keys for deterministic hashing.
        canonical_meta = "&".join(
            f"{k}={meta[k]!r}" for k in sorted(meta)
        )
        meta_hash = hashlib.sha256(canonical_meta.encode("utf-8")).hexdigest()
    else:
        meta_hash = ""
    parts.append(f"freeform_metadata_sha256={meta_hash!r}")
    return "|".join(parts)


def sign(record: OverrideRecord) -> str:
    """Compute the HMAC-SHA256 hex digest of `record`'s canonical fields."""
    payload = _canonical_payload(record).encode("utf-8")
    return hmac.new(_hmac_key(), payload, hashlib.sha256).hexdigest()


def verify(record: OverrideRecord, signature: str) -> bool:
    """Verify a signature against the canonical payload of `record`.

    Returns True iff `signature` matches an HMAC computed with the
    current key. Uses constant-time compare to avoid timing leaks.
    """
    expected = sign(record)
    return hmac.compare_digest(expected, signature or "")
