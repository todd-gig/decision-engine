"""OVS-Calibration emission for human-override events.

Per spec decision #6 ("Override events emit to OVS-Calibration as outcomes
immediately — not nightly batch") and decision #1 ("Override events are
first-class outcomes for OVS-Calibration — weight 3× ordinary outcomes").

v0.5 wire: this is a function-call seam — the consumer side will be wired
in the OVS-Calibration v0.5 PR. We persist the emitted record to the
JSONL append-only log used by `engine.learning_loop.LearningStore` so
that aggregate calibration reads pick up override-derived outcomes
alongside expected/actual outcome records.

penrose_signal: weakens
penrose_dimension: override_rate
why: An override that doesn't propagate to calibration is a one-off log
line; an override that propagates is a 3×-weight outcome that pulls the
calibration vector toward what the operator chose. Without this emission,
the OVS variance trend (Penrose-Falsification Scoreboard signal #4)
stays unaffected by human corrections.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .recorder import OverrideClassification, OverrideRecord


logger = logging.getLogger(__name__)


@dataclass
class CalibrationEmission:
    """A v0.5 OutcomeEvent emitted from a human override.

    Fields chosen to overlap with `engine.learning_loop.OutcomeRecord` so
    a future OVS-Calibration consumer can ingest both shapes uniformly.
    """

    override_id: str
    decision_id: Optional[str]
    decision_class: str
    source: str = "override"
    weight: float = 3.0  # default per spec; recorder passes per-type value
    override_type: str = ""
    reasoning: str = ""
    source_engine: str = ""
    emitted_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )


def _default_log_path() -> Path:
    """Where calibration emissions land in v0.5.

    Lives alongside `learning_records.jsonl` (the file
    `engine.learning_loop.LearningStore` reads/writes) so an OVS-Calibration
    consumer that already scans the data directory picks these up for free.
    """
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "override_calibration_emissions.jsonl"


def emit_to_calibration(
    record: OverrideRecord,
    classification: Optional[OverrideClassification] = None,
    *,
    log_path: str | Path | None = None,
) -> CalibrationEmission:
    """Build the CalibrationEmission for `record` and append it to the JSONL log.

    `classification.ovs_weight` carries through as the emission weight so
    callers don't need to know the taxonomy (REVERSAL=3.0, MODIFICATION=2.0,
    REJECTION=2.0, SILENT_INACTION=1.5, REPEATED_OVERRIDE=4.0).

    Returns the constructed CalibrationEmission so callers can inspect it
    (esp. in tests).
    """
    if classification is None:
        # Late import avoids circular import (recorder imports this module).
        from .recorder import classify_override
        classification = classify_override(record)

    decision_class = ""
    if record.freeform_metadata:
        decision_class = str(
            record.freeform_metadata.get("decision_class", "")
        )
    if not decision_class and record.decision_certificate_id:
        decision_class = record.decision_certificate_id.split("-")[0]

    emission = CalibrationEmission(
        override_id=record.override_id,
        decision_id=record.decision_id,
        decision_class=decision_class,
        weight=float(classification.ovs_weight),
        override_type=record.override_type,
        reasoning=record.user_reasoning or "",
        source_engine=record.source_engine,
    )

    log_target = Path(log_path) if log_path else _default_log_path()
    try:
        with open(log_target, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(emission)) + "\n")
    except OSError as exc:
        # Don't break the override path — log and continue. Non-Negotiable #1.
        logger.warning(
            "failed to write calibration emission for %s: %s",
            record.override_id,
            exc,
        )
    return emission


def emissions_log_path() -> Path:
    """Expose the default log path for callers (drift_signal scanner, tests)."""
    override = os.environ.get("OVERRIDE_CALIBRATION_LOG")
    return Path(override) if override else _default_log_path()
