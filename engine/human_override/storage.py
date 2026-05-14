"""human_overrides SQLite schema + connection helpers.

Schema mirrors specs/human_override_engine_v0.md §Override storage schema.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "human_overrides.db"


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
    """)
