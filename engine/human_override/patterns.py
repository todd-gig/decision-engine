"""Pattern detector — cluster recent overrides into actionable signals.

Per spec decision #5 ("Pattern detection runs nightly. Clusters by
signature.") and decision #8 ("Negative-polarity codification candidates
— pattern of 'always overrides X with Y' → codify Y, not X.").

Clustering key: (decision_class, override_type, original_action_signature)
where original_action_signature is the trimmed/normalized
`original_action` string. A cluster with ≥3 matching events in the
window becomes an OverridePattern row.

penrose_signal: weakens
penrose_dimension: override_rate
why: Without clustering, every override is an isolated event. Clustering
converts a stream of corrections into "the engine keeps doing X; humans
keep choosing Y" — which is exactly the shape Codification consumes as a
negative-polarity proposal (codify Y, not X). This is the bridge between
override events and the codification flywheel.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import storage


logger = logging.getLogger(__name__)


# Cluster boundary. Spec doesn't pin a number for "promotes to pattern";
# operational default: 3 same-shape events in window = pattern. 5+ is
# the threshold the nightly sweep uses to emit codification candidates
# (set in sweep.py STABLE_CLUSTER_SIZE).
PATTERN_MIN_CLUSTER = 3


@dataclass
class OverridePattern:
    pattern_id: str
    decision_class: str
    override_type: str
    original_action_sig: str
    cluster_size: int
    window_start: str
    window_end: str
    span_seconds: int
    polarity: str  # 'negative' (always overrides X with Y) | 'positive'
    recommended_action: str
    emitted_codification: Optional[str] = None


def _normalize_action_sig(action: str) -> str:
    """Normalize `original_action` for clustering — strip whitespace + lower.

    Keep this conservative: heavy normalization risks collapsing distinct
    decisions; light normalization risks missing duplicates. Spec leaves
    the exact shape open; v0.5 uses strip+lower which is the same shape
    Codification uses for prompt_version clustering.
    """
    return (action or "").strip().lower()


def _resolve_decision_class(row: sqlite3.Row | dict) -> str:
    """Pull a decision_class out of the override row.

    Today we don't have a dedicated column — we read from
    `freeform_metadata.decision_class` if present, else fall back to the
    certificate id prefix, else the source_engine. (Adding a dedicated
    column is v0.6 schema work; v0.5 stays migration-free.)
    """
    meta_raw = row["freeform_metadata"] if "freeform_metadata" in row.keys() else None
    if meta_raw:
        try:
            meta = json.loads(meta_raw)
            cls = meta.get("decision_class")
            if cls:
                return str(cls)
        except (json.JSONDecodeError, TypeError):
            pass
    cert_id = row["decision_certificate_id"] if "decision_certificate_id" in row.keys() else None
    if cert_id:
        return str(cert_id).split("-")[0]
    return str(row["source_engine"])


def detect_patterns(
    window_days: int = 7,
    db_path: Optional[str] = None,
    *,
    min_cluster: int = PATTERN_MIN_CLUSTER,
) -> list[OverridePattern]:
    """Cluster overrides in the last `window_days` and return patterns.

    A "pattern" is any (decision_class, override_type, original_action_sig)
    bucket with ≥`min_cluster` rows in the window. Patterns are returned
    sorted by cluster_size DESC.

    Patterns are NOT persisted by this function — that's the nightly
    sweep's job (so callers can preview / dry-run).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days))
    cutoff_iso = cutoff.isoformat()
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM human_overrides
            WHERE overridden_at >= ?
            ORDER BY overridden_at ASC
            """,
            (cutoff_iso,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    buckets: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for row in rows:
        key = (
            _resolve_decision_class(row),
            row["override_type"],
            _normalize_action_sig(row["original_action"]),
        )
        buckets.setdefault(key, []).append(row)

    patterns: list[OverridePattern] = []
    for (decision_class, override_type, action_sig), members in buckets.items():
        if len(members) < min_cluster:
            continue
        timestamps = [
            datetime.fromisoformat(m["overridden_at"]) for m in members
        ]
        ws, we = min(timestamps), max(timestamps)
        span_seconds = int((we - ws).total_seconds())

        # Polarity: if all `override_action` values are the same, it's a
        # strong "always overrides X with Y" negative-polarity signal
        # (codify Y, not X). Otherwise positive (variation in corrections).
        chosen_actions = {m["override_action"].strip().lower() for m in members}
        polarity = "negative" if len(chosen_actions) == 1 else "positive"

        if polarity == "negative":
            recommended_action = (
                f"Codify Y='{next(iter(chosen_actions))}' as default for "
                f"decision_class='{decision_class}' instead of X='{action_sig}'."
            )
        else:
            recommended_action = (
                f"Operators correct decision_class='{decision_class}' "
                f"action='{action_sig}' with varying Y — investigate; "
                "codification not yet warranted."
            )

        patterns.append(
            OverridePattern(
                pattern_id=str(uuid.uuid4()),
                decision_class=decision_class,
                override_type=override_type,
                original_action_sig=action_sig,
                cluster_size=len(members),
                window_start=ws.isoformat(),
                window_end=we.isoformat(),
                span_seconds=span_seconds,
                polarity=polarity,
                recommended_action=recommended_action,
            )
        )

    patterns.sort(key=lambda p: p.cluster_size, reverse=True)
    return patterns


def persist_patterns(
    patterns: list[OverridePattern],
    db_path: Optional[str] = None,
) -> int:
    """Persist patterns to override_patterns. Returns rows inserted."""
    if not patterns:
        return 0
    conn = storage.get_connection(db_path)
    try:
        for p in patterns:
            conn.execute(
                """
                INSERT INTO override_patterns (
                    pattern_id, decision_class, override_type,
                    original_action_sig, cluster_size, window_start,
                    window_end, span_seconds, polarity,
                    recommended_action, emitted_codification
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.pattern_id, p.decision_class, p.override_type,
                    p.original_action_sig, p.cluster_size, p.window_start,
                    p.window_end, p.span_seconds, p.polarity,
                    p.recommended_action, p.emitted_codification,
                ),
            )
    finally:
        conn.close()
    return len(patterns)


def list_patterns(
    db_path: Optional[str] = None,
    *,
    limit: int = 200,
    polarity: Optional[str] = None,
) -> list[dict]:
    """Read back persisted patterns for the UI / API."""
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if polarity is not None:
            cur = conn.execute(
                """
                SELECT * FROM override_patterns
                WHERE polarity = ?
                ORDER BY detected_at DESC LIMIT ?
                """,
                (polarity, limit),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM override_patterns
                ORDER BY detected_at DESC LIMIT ?
                """,
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
