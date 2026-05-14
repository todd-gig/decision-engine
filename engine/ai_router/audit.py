"""Audit envelope construction — hashing + HMAC signing.

Full prompts/responses are NOT stored; only SHA-256 hashes. Each audit
row is HMAC-SHA256 signed across canonical fields so replay can verify
the row wasn't tampered with after the fact.

The HMAC key is read from env `LLM_AUDIT_HMAC_KEY`. For local dev a
deterministic default is used; production must set the env explicitly.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone


_DEFAULT_DEV_KEY = "dev-only-llm-audit-key-do-not-use-in-prod"


def _hmac_key() -> bytes:
    return os.environ.get("LLM_AUDIT_HMAC_KEY", _DEFAULT_DEV_KEY).encode("utf-8")


def hash_text(text: str) -> str:
    """SHA-256 hex digest of text. Empty string → fixed digest."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _canonical_payload(row: dict) -> str:
    """Build the canonical string over which we sign.

    Includes every field that should be tamper-evident. Excludes the
    audit_signature itself (chicken-and-egg) and the audit_metadata
    JSON blob (which is free-form caller info).
    """
    canonical_fields = [
        "audit_id", "invoked_at", "caller_engine", "caller_function",
        "provider_requested", "provider_used", "model_requested", "model_used",
        "prompt_version", "schema_version", "in_chars", "out_chars",
        "in_tokens", "out_tokens", "cost_usd", "latency_ms",
        "prompt_hash", "response_hash", "error",
    ]
    return "|".join(f"{k}={row.get(k)!r}" for k in canonical_fields)


def sign(row: dict) -> str:
    """Compute HMAC-SHA256 over canonical fields. Returns hex digest."""
    payload = _canonical_payload(row).encode("utf-8")
    return hmac.new(_hmac_key(), payload, hashlib.sha256).hexdigest()


def verify(row: dict) -> bool:
    """Verify an audit row's signature matches its canonical fields."""
    expected = sign(row)
    return hmac.compare_digest(expected, row.get("audit_signature", ""))


def new_audit_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
