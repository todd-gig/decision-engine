"""Drift-signal emission — codified-module override-rate canary.

Per spec decision #9 ("Drift signal on de-codification candidate —
codified module with rising override rate triggers de-codification
flow"). When a codified module's override rate (overrides ÷ decisions
in that class over rolling 14d) climbs ≥10%, we log a structured
DriftSignal row.

v0.5 scope: detect + log + queue in `override_drift_signals` table.
Integration with `drift_sentinel/` (writing into `drift_history.db`
violations table) is out of scope — separate concern, separate PR.

penrose_signal: weakens
penrose_dimension: override_rate
why: Codified patterns can rot. A module that used to need no overrides
but now needs many is "decaying logic" — the canary is the override
rate. Emitting a drift signal closes the loop with drift_sentinel, which
already governs decisions about the engine itself (B-02 closed).
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import storage


logger = logging.getLogger(__name__)


# Threshold from spec — 10% over rolling 14d triggers the signal.
OVERRIDE_RATE_THRESHOLD = 0.10
ROLLING_WINDOW_DAYS = 14
MIN_SAMPLE_SIZE = 10  # don't fire on tiny samples (noise)


@dataclass
class OverrideDriftSignal:
    signal_id: str
    rule_id: str
    severity: str
    artifact: str
    decision_class: str
    override_rate_14d: float
    sample_size: int
    notes: str


def detect_drift_signals(
    decision_counts: dict[str, int],
    db_path: Optional[str] = None,
    *,
    threshold: float = OVERRIDE_RATE_THRESHOLD,
    window_days: int = ROLLING_WINDOW_DAYS,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> list[OverrideDriftSignal]:
    """Scan recent overrides per decision_class; emit signals where rate ≥ threshold.

    `decision_counts` maps decision_class → total decisions in the same
    rolling window (the caller supplies this — we don't have a decisions
    table in this engine; the bridge to decision-engine outcomes is a v0.6
    seam).

    For each class with sample_size ≥ min_sample AND override_rate ≥
    threshold, emit a signal and persist to override_drift_signals.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days))
    cutoff_iso = cutoff.isoformat()

    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT override_type, source_engine, decision_certificate_id,
                   freeform_metadata
            FROM human_overrides
            WHERE overridden_at >= ?
            """,
            (cutoff_iso,),
        ).fetchall()
    finally:
        conn.close()

    # Bucket override events by decision_class for rate calc.
    override_counts: dict[str, int] = {}
    artifacts: dict[str, str] = {}
    for row in rows:
        # Re-use the pattern detector's class-resolution heuristic.
        from .patterns import _resolve_decision_class
        cls = _resolve_decision_class(row)
        override_counts[cls] = override_counts.get(cls, 0) + 1
        # Capture an artifact pointer (best-effort — source_engine):
        artifacts.setdefault(cls, row["source_engine"])

    signals: list[OverrideDriftSignal] = []
    for cls, total in decision_counts.items():
        if total < min_sample:
            continue
        overrides_n = override_counts.get(cls, 0)
        rate = overrides_n / total if total > 0 else 0.0
        if rate < threshold:
            continue
        sig = OverrideDriftSignal(
            signal_id=str(uuid.uuid4()),
            rule_id="OVERRIDE-RATE-DECAY",
            severity="major",
            artifact=artifacts.get(cls, cls),
            decision_class=cls,
            override_rate_14d=round(rate, 4),
            sample_size=total,
            notes=(
                f"override_rate {rate:.2%} over last {window_days}d "
                f"(threshold {threshold:.0%}); {overrides_n}/{total} decisions "
                "overridden. Codified logic may be decaying — review for "
                "de-codification or recalibration."
            ),
        )
        signals.append(sig)
        logger.warning(
            "[human_override.drift_signal] %s override_rate=%.4f "
            "(overrides=%d, decisions=%d, threshold=%.2f)",
            cls, rate, overrides_n, total, threshold,
        )

    if signals:
        _persist_signals(signals, db_path=db_path)
    return signals


def _persist_signals(
    signals: list[OverrideDriftSignal],
    db_path: Optional[str] = None,
) -> None:
    conn = storage.get_connection(db_path)
    try:
        for s in signals:
            conn.execute(
                """
                INSERT INTO override_drift_signals (
                    signal_id, rule_id, severity, artifact,
                    decision_class, override_rate_14d, sample_size, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s.signal_id, s.rule_id, s.severity, s.artifact,
                    s.decision_class, s.override_rate_14d, s.sample_size,
                    s.notes,
                ),
            )
    finally:
        conn.close()


def list_drift_signals(
    db_path: Optional[str] = None,
    *,
    limit: int = 200,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT * FROM override_drift_signals
            ORDER BY detected_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
