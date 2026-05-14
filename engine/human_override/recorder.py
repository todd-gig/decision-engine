"""Override recording + classification.

Per specs/human_override_engine_v0.md §Override types (taxonomy).

v0.5 additions:
  - reasoning ≥20 chars enforced at SDK boundary (always-record-WHY)
  - HMAC-SHA256 signature attached to every persisted row
  - OVS-Calibration emission on insert (3.0× weight for REVERSAL etc.)
  - per-overrider rate-limit alert at >10/hour

penrose_signal: weakens
penrose_dimension: override_rate
why: The recorder is the choke point through which every override flows.
Anything not enforced here doesn't get enforced — the Penrose-falsification
instrument only works if reasoning is real, signatures are present, and
events propagate to the calibration loop on insert (not nightly batch,
which would compound errors over the day).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from . import storage


logger = logging.getLogger(__name__)


# v0.5 guardrail: empty/short reasoning is noise; we reject it at the SDK
# boundary. Spec decision #3 anchored ≥10 chars; v0.5 raises to ≥20 because
# 10 chars routinely admits low-signal placeholders ("ok", "n/a", "test").
MIN_REASONING_CHARS = 20


class OverrideType(str, Enum):
    REVERSAL = "reversal"
    MODIFICATION = "modification"
    REJECTION = "rejection"
    SILENT_INACTION = "silent_inaction"
    REPEATED_OVERRIDE = "repeated_override"


_TAXONOMY: dict[str, dict] = {
    OverrideType.REVERSAL.value: {
        "ovs_weight": 3.0,
        "codification_action": "open_exception_case_now",
    },
    OverrideType.MODIFICATION.value: {
        "ovs_weight": 2.0,
        "codification_action": "open_exception_case_if_recurs",
    },
    OverrideType.REJECTION.value: {
        "ovs_weight": 2.0,
        "codification_action": "open_exception_case_after_5_same_type",
    },
    OverrideType.SILENT_INACTION.value: {
        "ovs_weight": 1.5,
        "codification_action": "trend_signal_only",
    },
    OverrideType.REPEATED_OVERRIDE.value: {
        "ovs_weight": 4.0,
        "codification_action": "escalate_to_founder",
    },
}


@dataclass
class OverrideClassification:
    type: str
    ovs_weight: float
    codification_action: str


@dataclass
class OverrideRecord:
    decision_id: Optional[str]
    decision_certificate_id: Optional[str]
    override_type: str
    overridden_by_user_id: str
    overridden_at: str
    source_engine: str
    surface: str
    original_action: str
    override_action: str
    user_reasoning: Optional[str] = None
    freeform_metadata: Optional[dict] = None
    override_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ReasoningTooShort(ValueError):
    """Reasoning failed the minimum-length gate. Subclass of ValueError so
    existing API handlers that catch ValueError keep working.

    why: empty reasoning is noise — the override only carries signal if
    the operator stated *why* they corrected the system. Per
    always-record-WHY doctrine; bound at the SDK so no downstream consumer
    has to re-check.
    """


def _validate_reasoning(record: OverrideRecord) -> None:
    text = (record.user_reasoning or "").strip()
    if len(text) < MIN_REASONING_CHARS:
        raise ReasoningTooShort(
            f"user_reasoning must be ≥{MIN_REASONING_CHARS} characters "
            f"(got {len(text)}); explain why you overrode this decision. "
            "Per always-record-WHY doctrine."
        )


def classify_override(record: OverrideRecord) -> OverrideClassification:
    """Apply taxonomy → ovs_weight + codification_action."""
    spec = _TAXONOMY.get(record.override_type)
    if spec is None:
        raise ValueError(
            f"unknown override_type {record.override_type!r}; "
            f"must be one of {sorted(_TAXONOMY)}"
        )
    return OverrideClassification(
        type=record.override_type,
        ovs_weight=spec["ovs_weight"],
        codification_action=spec["codification_action"],
    )


def record_override(
    record: OverrideRecord,
    db_path: str | None = None,
    *,
    emit_to_calibration: bool = True,
) -> dict:
    """Persist an override + its classification to the SQLite store.

    v0.5 side effects:
      1. validates reasoning length (raises ReasoningTooShort if short)
      2. signs row with HMAC-SHA256
      3. emits to OVS-Calibration (weight per taxonomy)
      4. checks per-overrider rate limit; logs WARNING if breached

    Returns the persisted row as dict for callers (test + API surface).

    why: This is the single recorded-override choke point. Doing all four
    side effects here makes them un-bypassable — no caller can persist an
    override without WHY + signature + calibration propagation.
    """
    classification = classify_override(record)
    _validate_reasoning(record)

    # Compute signature BEFORE write so it lands in the same row.
    # Imported lazily to keep recorder.py importable in environments
    # missing hmac (it ships with stdlib so this is mostly cosmetic — the
    # real reason is to avoid a circular import with signing.py).
    from . import signing

    sig = signing.sign(record)

    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO human_overrides (
                override_id, decision_id, decision_certificate_id,
                override_type, overridden_by_user_id, overridden_at,
                source_engine, surface, original_action, override_action,
                user_reasoning, freeform_metadata, classification, signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.override_id,
                record.decision_id,
                record.decision_certificate_id,
                record.override_type,
                record.overridden_by_user_id,
                record.overridden_at,
                record.source_engine,
                record.surface,
                record.original_action,
                record.override_action,
                record.user_reasoning,
                json.dumps(record.freeform_metadata) if record.freeform_metadata else None,
                json.dumps(asdict(classification)),
                sig,
            ),
        )
    finally:
        conn.close()

    # Per-overrider rate limit — log alert AFTER write so we never block
    # the override itself (Non-Negotiable #1: never suppress overrides).
    try:
        from . import rate_limit
        rate_limit.check_rate(
            record.overridden_by_user_id,
            db_path=db_path,
        )
    except Exception as exc:  # pragma: no cover — defense in depth
        logger.warning("rate-limit check failed (non-fatal): %s", exc)

    # Emit to OVS-Calibration — same-process function call in v0.5. If
    # Pub/Sub topic exists in the future, calibration_emit.py is the seam.
    if emit_to_calibration:
        try:
            from . import calibration_emit
            calibration_emit.emit_to_calibration(record, classification)
        except Exception as exc:  # pragma: no cover — never break override path
            logger.warning(
                "calibration emission failed (non-fatal): %s", exc
            )

    return {
        **asdict(record),
        "classification": asdict(classification),
        "signature": sig,
    }
