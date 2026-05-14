"""ovs_calibration SQLite schema + connection helpers.

Schema mirrors the OVS-Calibration Engine spec (outcome_calibration_engine_spec.md):
  - outcome_sources            — registry of outcome ingestion sources
  - outcome_events             — append-only ingested outcome events
  - attribution_links          — many-to-many between decisions and outcomes
  - calibration_revisions      — HMAC-signed dimension updates

WHY this file exists: every other module in this sub-package shares one SQLite
file so the calibration loop can be read end-to-end in a single query. Splitting
storage per module would make joins (decision -> outcome -> revision) impossible
without a heavier dependency.

penrose_signal: weakens
penrose_dimension: variance | cascade
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "ovs_calibration.db"


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
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS outcome_sources (
            id                          TEXT PRIMARY KEY,
            name                        TEXT NOT NULL,
            kind                        TEXT NOT NULL,
            entity                      TEXT NOT NULL,
            ingestion_contract          TEXT NOT NULL,
            schema_json                 TEXT NOT NULL,
            owner                       TEXT NOT NULL,
            health_status               TEXT NOT NULL DEFAULT 'unknown',
            decision_class_metric_map   TEXT NOT NULL DEFAULT '{}',
            schema_version              TEXT NOT NULL DEFAULT 'v1',
            created_at                  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at                  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (kind IN
                ('revenue','conversion','operational','satisfaction','external')),
            CHECK (ingestion_contract IN ('pubsub','webhook','polling'))
        );

        CREATE TABLE IF NOT EXISTS outcome_events (
            id                  TEXT PRIMARY KEY,
            source_id           TEXT,
            source              TEXT NOT NULL,
            entity              TEXT NOT NULL,
            metric              TEXT NOT NULL,
            observed_value      REAL NOT NULL,
            expected_value      REAL,
            unit                TEXT,
            observed_at         TEXT NOT NULL,
            ingested_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_record_id    TEXT,
            reasoning           TEXT,
            schema_version      TEXT NOT NULL DEFAULT 'v1'
        );
        CREATE INDEX IF NOT EXISTS idx_outcome_events_metric
            ON outcome_events(metric, observed_at);
        CREATE INDEX IF NOT EXISTS idx_outcome_events_entity
            ON outcome_events(entity, observed_at);

        CREATE TABLE IF NOT EXISTS attribution_links (
            id                       TEXT PRIMARY KEY,
            decision_certificate_id  TEXT NOT NULL,
            outcome_event_id         TEXT NOT NULL,
            confidence               REAL NOT NULL,
            attribution_method       TEXT NOT NULL,
            layer_number             INTEGER NOT NULL,
            cascade_multiplier       REAL NOT NULL DEFAULT 1.0,
            attributed_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            attributed_by            TEXT NOT NULL,
            reasoning                TEXT NOT NULL,
            schema_version           TEXT NOT NULL DEFAULT 'v1',
            CHECK (attribution_method IN
                ('direct','temporal','causal-chain','manual')),
            CHECK (layer_number IN (1,2,3,4)),
            CHECK (confidence >= 0.0 AND confidence <= 1.0)
        );
        CREATE INDEX IF NOT EXISTS idx_attribution_decision
            ON attribution_links(decision_certificate_id);
        CREATE INDEX IF NOT EXISTS idx_attribution_outcome
            ON attribution_links(outcome_event_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_attribution_pair
            ON attribution_links(decision_certificate_id, outcome_event_id,
                                  attribution_method);

        CREATE TABLE IF NOT EXISTS calibration_revisions (
            id                          TEXT PRIMARY KEY,
            dimension                   TEXT NOT NULL,
            before_value                REAL NOT NULL,
            after_value                 REAL NOT NULL,
            evidence_window_start       TEXT NOT NULL,
            evidence_window_end         TEXT NOT NULL,
            evidence_outcome_ids        TEXT NOT NULL,  -- JSON array
            computation_version         TEXT NOT NULL,
            signed_by                   TEXT NOT NULL,
            hmac                        TEXT NOT NULL,
            signed_at                   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reasoning                   TEXT NOT NULL,
            md_path                     TEXT,
            schema_version              TEXT NOT NULL DEFAULT 'v1'
        );
        CREATE INDEX IF NOT EXISTS idx_calibration_dimension
            ON calibration_revisions(dimension, signed_at);
    """)
