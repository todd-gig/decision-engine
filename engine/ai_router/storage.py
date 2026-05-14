"""llm_audit SQLite schema + connection helpers.

The audit table records one row per LLM invocation. Full prompts +
responses are NOT stored — only SHA-256 hashes for tamper-evidence.
Each row is HMAC-SHA256 signed across canonical fields so audit replay
can detect tampering.

Schema mirrors specs/ai_routing_engine_v0.md §Audit table schema with
Postgres-specific types replaced by SQLite-compatible equivalents.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "llm_audit.db"


def _default_db_path() -> Path:
    """Default location: alongside drift_history.db in drift_sentinel/."""
    here = Path(__file__).resolve().parent
    # engine/ai_router/storage.py -> repo root = engine/ai_router/../..
    repo_root = here.parent.parent
    candidate = repo_root / "drift_sentinel" / DEFAULT_DB_FILENAME
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the llm_audit SQLite database."""
    path = Path(db_path) if db_path else _default_db_path()
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create llm_audit table + indexes if not present.

    Idempotent — safe to call on every connection open. Pattern matches
    decision-engine's other SQLite-backed surfaces (drift_history.db,
    intelligence_silo memory).
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS llm_audit (
            audit_id             TEXT PRIMARY KEY,
            invoked_at           TEXT NOT NULL,
            caller_engine        TEXT NOT NULL,
            caller_function      TEXT NOT NULL,
            provider_requested   TEXT NOT NULL,
            provider_used        TEXT NOT NULL,
            model_requested      TEXT NOT NULL,
            model_used           TEXT NOT NULL,
            prompt_version       TEXT NOT NULL,
            schema_version       TEXT NOT NULL,
            in_chars             INTEGER NOT NULL,
            out_chars            INTEGER NOT NULL,
            in_tokens            INTEGER,
            out_tokens           INTEGER,
            cost_usd             REAL,
            latency_ms           INTEGER NOT NULL,
            fallback_chain_taken TEXT NOT NULL,   -- JSON array
            audit_metadata       TEXT,            -- JSON object
            error                TEXT,
            prompt_hash          TEXT NOT NULL,
            response_hash        TEXT NOT NULL,
            audit_signature      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_llm_audit_caller
            ON llm_audit(caller_engine, caller_function, invoked_at);
        CREATE INDEX IF NOT EXISTS idx_llm_audit_pv
            ON llm_audit(prompt_version, schema_version);
        CREATE INDEX IF NOT EXISTS idx_llm_audit_cost
            ON llm_audit(invoked_at) WHERE cost_usd IS NOT NULL;
    """)


def insert_audit(conn: sqlite3.Connection, row: dict) -> None:
    """Insert one audit row. Row is dict with all required fields."""
    conn.execute(
        """
        INSERT INTO llm_audit (
            audit_id, invoked_at, caller_engine, caller_function,
            provider_requested, provider_used, model_requested, model_used,
            prompt_version, schema_version, in_chars, out_chars,
            in_tokens, out_tokens, cost_usd, latency_ms,
            fallback_chain_taken, audit_metadata, error,
            prompt_hash, response_hash, audit_signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["audit_id"], row["invoked_at"], row["caller_engine"],
            row["caller_function"], row["provider_requested"], row["provider_used"],
            row["model_requested"], row["model_used"], row["prompt_version"],
            row["schema_version"], row["in_chars"], row["out_chars"],
            row["in_tokens"], row["out_tokens"], row["cost_usd"], row["latency_ms"],
            json.dumps(row["fallback_chain_taken"]),
            json.dumps(row["audit_metadata"]) if row["audit_metadata"] is not None else None,
            row["error"], row["prompt_hash"], row["response_hash"],
            row["audit_signature"],
        ),
    )
