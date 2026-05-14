"""Override recording + classification.

Per specs/human_override_engine_v0.md §Override types (taxonomy).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from . import storage


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


def record_override(record: OverrideRecord, db_path: str | None = None) -> dict:
    """Persist an override + its classification to the SQLite store.

    Returns the persisted row as dict for callers (test + API surface).
    """
    classification = classify_override(record)
    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO human_overrides (
                override_id, decision_id, decision_certificate_id,
                override_type, overridden_by_user_id, overridden_at,
                source_engine, surface, original_action, override_action,
                user_reasoning, freeform_metadata, classification
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
    finally:
        conn.close()
    return {
        **asdict(record),
        "classification": asdict(classification),
    }
