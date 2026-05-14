"""network_value_emitter — STUB inbox for PPEME-emitted BFT state observations.

WHAT: Defines the contract for "Super-Additive Network Value" (Penrose
Scoreboard signal 6) without computing it. PPEME owns the 9-variable BFT
state vector today (Framework 5.19); this module is the receiving table
for when PPEME starts emitting per-participant state snapshots.

WHY: Per memory penrose_falsification_doctrine.md §Scoreboard item 6, the
network-value-per-added-participant claim cannot be tested unless we have
participant-level state observations across time. Faking the number would
violate the always-record-WHY + no-synthesis rules. So the table exists,
the endpoint accepts writes, the scoreboard returns a stub with the
formula + next_milestone keys. When PPEME wires up, this inbox fills and
the scoreboard graduates the metric.

WHERE: SQLite table `network_value_observations` in
`drift_sentinel/penrose_scoreboard.db` (shared with velocity).

WHEN: PPEME BFT emitter wires here in penrose-v0.7. Until then table is
empty by design and scoreboard returns
`{"status": "awaiting_ppeme_wiring", "value": None, ...}`.

HOW: 9-variable canonical state vector (CRIT-010 enforced: any caller
posting a non-canonical state shape gets a `ValueError`).

CONTEXT: This file is the bridge. Per memory entry "Doctrine-claim ≠
committed code" — we don't claim Network Value is measured until rows
exist; we DO claim the contract is committed.

# TODO(penrose-v0.7): wire PPEME BFT emitter — see ppeme/api/state_emitter.py
when it lands; subscribe via Pub/Sub or direct HTTP and call
`record_participant_bft_state(...)` on every emit.

penrose_signal: weakens
penrose_dimension: network_value
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import velocity as _velocity_module  # reuse shared DB connection

NETWORK_VALUE_TABLE = "network_value_observations"

# Canonical 9-variable BFT state vector — CRIT-010 enforced.
# Order matters for canonical hashing; sets are compared order-insensitive
# when validating incoming payloads.
NETWORK_VALUE_STATE_DIMENSIONS: tuple[str, ...] = (
    "trust",
    "attention",
    "clarity",
    "desire",
    "urgency",
    "value",
    "friction",
    "social_proof",
    "context_fit",
)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {NETWORK_VALUE_TABLE} (
            id              TEXT PRIMARY KEY,
            participant_id  TEXT NOT NULL,
            state_vector    TEXT NOT NULL,   -- canonical 9-var JSON object
            timestamp       TEXT NOT NULL,
            ingested_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source          TEXT NOT NULL DEFAULT 'ppeme'
        );
        CREATE INDEX IF NOT EXISTS idx_network_value_participant
            ON {NETWORK_VALUE_TABLE}(participant_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_network_value_timestamp
            ON {NETWORK_VALUE_TABLE}(timestamp);
        """
    )


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open shared DB; ensures both velocity + network-value schemas exist."""
    conn = _velocity_module.get_connection(db_path)
    _ensure_schema(conn)
    return conn


def _validate_state_vector(state_vector_9d: dict) -> None:
    if not isinstance(state_vector_9d, dict):
        raise ValueError(
            "state_vector_9d must be a dict mapping each of the canonical "
            f"9 variables to a numeric value; got {type(state_vector_9d).__name__}"
        )
    keys = set(state_vector_9d.keys())
    canonical = set(NETWORK_VALUE_STATE_DIMENSIONS)
    if keys != canonical:
        missing = canonical - keys
        extra = keys - canonical
        raise ValueError(
            "state_vector_9d must contain EXACTLY the canonical 9 variables "
            f"(CRIT-010, §5.19); missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for k, v in state_vector_9d.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(
                f"state_vector_9d[{k!r}] must be numeric; got {type(v).__name__}"
            )


def record_participant_bft_state(
    participant_id: str,
    state_vector_9d: dict,
    timestamp: Optional[str] = None,
    *,
    source: str = "ppeme",
    db_path: str | Path | None = None,
) -> dict:
    """Write one (participant, state, timestamp) observation to the inbox.

    Per WWWWH: WHAT = persist observation; WHY = data substrate for future
    network-value computation; HOW = canonical-9 enforced. Until PPEME
    emits, this is unused — table empty by design.

    Raises:
        ValueError: when state_vector_9d does not match canonical 9.
    """
    if not participant_id or not isinstance(participant_id, str):
        raise ValueError("participant_id must be a non-empty string")
    _validate_state_vector(state_vector_9d)

    ts = timestamp or datetime.now(tz=timezone.utc).isoformat()
    obs_id = f"NVO-{uuid.uuid4().hex[:12].upper()}"

    conn = get_connection(db_path)
    try:
        conn.execute(
            f"""
            INSERT INTO {NETWORK_VALUE_TABLE}
                (id, participant_id, state_vector, timestamp, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                obs_id,
                participant_id,
                json.dumps(state_vector_9d, sort_keys=True),
                ts,
                source,
            ),
        )
        return {
            "id": obs_id,
            "participant_id": participant_id,
            "state_vector": state_vector_9d,
            "timestamp": ts,
            "source": source,
        }
    finally:
        conn.close()


def list_observations(
    participant_id: Optional[str] = None,
    limit: int = 200,
    *,
    db_path: str | Path | None = None,
) -> list[dict]:
    """List observations, optionally filtered by participant.

    Returns [] when table empty (the v0.6 expected state).
    """
    limit = max(1, min(int(limit), 1000))
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if participant_id:
            rows = conn.execute(
                f"""
                SELECT * FROM {NETWORK_VALUE_TABLE}
                WHERE participant_id = ? ORDER BY timestamp DESC LIMIT ?
                """,
                (participant_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT * FROM {NETWORK_VALUE_TABLE}
                ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            try:
                d["state_vector"] = json.loads(d["state_vector"])
            except (TypeError, ValueError):
                pass
            out.append(d)
        return out
    finally:
        conn.close()


def count_observations(*, db_path: str | Path | None = None) -> int:
    """Cheap count for the scoreboard stub. 0 until PPEME wires."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {NETWORK_VALUE_TABLE}"
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()
