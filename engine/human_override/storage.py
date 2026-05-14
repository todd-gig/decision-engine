"""human_overrides SQLite schema + connection helpers.

Schema mirrors specs/human_override_engine_v0.md §Override storage schema.

v0.5 additions:
  - `signature` column on human_overrides (HMAC-SHA256 hex digest)
  - `override_patterns` table — clustered repeat-override signals
  - `override_drift_signals` table — codified-module override-rate alerts
  - `delete_override` raises `NotSupported` (append-only enforcement)

penrose_signal: weakens
penrose_dimension: override_rate
why: Append-only storage is the substrate the override-rate metric runs
on. A mutable log can't be trusted to show whether human intervention
is decreasing. Append-only + HMAC + nightly clustering convert scattered
events into the Penrose-falsification instrument for Override Rate.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "human_overrides.db"


class NotSupported(Exception):
    """Raised when a caller attempts a forbidden mutation on the append-only log.

    why: Non-Negotiable #1 + spec decision #2 ("Append-only HMAC-signed
    storage — overrides cannot be deleted"). Deleting an override loses
    its signal AND lets an adversary rewrite the rate trend. We raise a
    distinct exception (not e.g. RuntimeError) so callers can pattern-match.
    """


def _default_db_path() -> Path:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    candidate = repo_root / "drift_sentinel" / DEFAULT_DB_FILENAME
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS human_overrides (
            override_id              TEXT PRIMARY KEY,
            decision_id              TEXT,
            decision_certificate_id  TEXT,
            override_type            TEXT NOT NULL,
            overridden_by_user_id    TEXT NOT NULL,
            overridden_at            TEXT NOT NULL,
            source_engine            TEXT NOT NULL,
            surface                  TEXT NOT NULL,
            original_action          TEXT NOT NULL,
            override_action          TEXT NOT NULL,
            user_reasoning           TEXT,
            freeform_metadata        TEXT,    -- JSON
            classification           TEXT NOT NULL,  -- JSON
            signature                TEXT,           -- HMAC-SHA256 hex (v0.5+)
            sent_to_ovs_at           TEXT,
            sent_to_codification_at  TEXT,
            created_at               TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_overrides_decision
            ON human_overrides(decision_id);
        CREATE INDEX IF NOT EXISTS idx_overrides_user
            ON human_overrides(overridden_by_user_id, overridden_at);
        CREATE INDEX IF NOT EXISTS idx_overrides_engine
            ON human_overrides(source_engine, overridden_at);

        CREATE TABLE IF NOT EXISTS override_patterns (
            pattern_id              TEXT PRIMARY KEY,
            decision_class          TEXT NOT NULL,
            override_type           TEXT NOT NULL,
            original_action_sig     TEXT NOT NULL,
            cluster_size            INTEGER NOT NULL,
            window_start            TEXT NOT NULL,
            window_end              TEXT NOT NULL,
            span_seconds            INTEGER NOT NULL,
            polarity                TEXT NOT NULL,  -- 'negative'|'positive'
            recommended_action      TEXT NOT NULL,
            emitted_codification    TEXT,           -- proposal_id if emitted
            detected_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_patterns_class
            ON override_patterns(decision_class, detected_at);

        CREATE TABLE IF NOT EXISTS override_drift_signals (
            signal_id               TEXT PRIMARY KEY,
            rule_id                 TEXT NOT NULL,
            severity                TEXT NOT NULL,
            artifact                TEXT NOT NULL,
            decision_class          TEXT NOT NULL,
            override_rate_14d       REAL NOT NULL,
            sample_size             INTEGER NOT NULL,
            detected_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes                   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_drift_signals_artifact
            ON override_drift_signals(artifact, detected_at);
    """)
    # v0.5 migration — add signature column to pre-existing rows.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(human_overrides)")}
    if "signature" not in cols:
        conn.execute("ALTER TABLE human_overrides ADD COLUMN signature TEXT")


# ── Append-only enforcement ─────────────────────────────────────────────────


def delete_override(override_id: str, db_path: str | Path | None = None) -> None:
    """Forbidden — overrides are append-only.

    Always raises NotSupported. Exposed as a named function so callers
    that *try* to delete get a clear, traceable refusal instead of a
    silent no-op or a generic SQL error. Why: per spec decision #2
    ("Append-only HMAC-signed storage").
    """
    raise NotSupported(
        f"delete_override({override_id!r}) is forbidden — "
        "human_overrides is append-only per Non-Negotiable #1"
    )
