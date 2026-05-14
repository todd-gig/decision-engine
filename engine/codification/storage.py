"""codification_proposals SQLite schema + connection helpers.

Schema mirrors specs/codification_engine_v0.md §Codification Proposal schema.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "codification_proposals.db"


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
        CREATE TABLE IF NOT EXISTS codification_proposals (
            proposal_id           TEXT PRIMARY KEY,
            candidate_pv          TEXT NOT NULL,
            candidate_sv          TEXT NOT NULL,
            candidate_score       REAL NOT NULL,
            analyzer_run_at       TEXT NOT NULL,
            proposed_python       TEXT NOT NULL,
            proposed_tests        TEXT NOT NULL,
            why                   TEXT NOT NULL,
            sim_n                 INTEGER NOT NULL,
            sim_divergence_p50    REAL NOT NULL,
            sim_divergence_p90    REAL NOT NULL,
            sim_cost_savings_usd  REAL,
            sim_latency_savings_ms INTEGER,
            queue_status          TEXT NOT NULL,
            approver_user_id      TEXT,
            approved_at           TEXT,
            approval_why          TEXT,
            shipped_pr_url        TEXT,
            created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (queue_status IN
                ('open', 'approved_ship', 'approved_fallback', 'rejected', 'deferred'))
        );
        CREATE INDEX IF NOT EXISTS idx_codification_status
            ON codification_proposals(queue_status, created_at);
        CREATE INDEX IF NOT EXISTS idx_codification_pv
            ON codification_proposals(candidate_pv, candidate_sv);
    """)
