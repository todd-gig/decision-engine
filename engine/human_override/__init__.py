"""human_override — capture every human override of an engine decision.

Per specs/human_override_engine_v0.md + v0.5 hardening (this module).

v0 surface:
  - record_override(override): write to human_overrides table
  - classify_override(override): apply taxonomy + downstream weights
  - storage: SQLite schema + connection

v0.5 surface additions:
  - signing.sign(record) / signing.verify(record, signature) — HMAC chain
  - patterns.detect_patterns(window_days) — cluster repeat overrides
  - sweep.run_nightly_sweep() — nightly entrypoint, emits to codification
  - calibration_emit.emit_to_calibration(record) — 3× weight outcome
  - drift_signal.detect_drift_signals(decision_counts) — rate-decay canary
  - rate_limit.check_rate(user_id) — >10/hour alert (no block)
  - anonymize.hash_user_id(user_id) — cross-org redaction
  - storage.NotSupported / storage.delete_override → forbidden

penrose_signal: weakens
penrose_dimension: override_rate
"""
from __future__ import annotations

from .recorder import (
    MIN_REASONING_CHARS,
    OverrideClassification,
    OverrideRecord,
    OverrideType,
    ReasoningTooShort,
    classify_override,
    record_override,
)
from .storage import NotSupported, delete_override

__all__ = [
    "OverrideRecord",
    "OverrideClassification",
    "OverrideType",
    "ReasoningTooShort",
    "MIN_REASONING_CHARS",
    "record_override",
    "classify_override",
    "NotSupported",
    "delete_override",
]
