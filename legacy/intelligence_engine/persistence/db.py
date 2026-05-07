"""
persistence/db.py
SQLite persistence layer — replaces flat-file learning_records.jsonl.
Stores decisions, outcomes, patterns, causal graphs, and weight history.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# Engine imports (relative to intelligence-engine root)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import DecisionObject, PipelineResult
from engine.audit import serialize_pipeline_result
from engine.learning_loop import OutcomeRecord, VarianceAnalysis


SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id     TEXT PRIMARY KEY,
    title           TEXT,
    decision_class  TEXT,
    owner           TEXT,
    verdict         TEXT,
    net_value_score REAL,
    trust_tier      TEXT,
    trust_total     REAL,
    alignment_composite REAL,
    priority_score  REAL,
    rtql_stage      TEXT,
    rtql_multiplier REAL,
    pipeline_result_json TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id              TEXT PRIMARY KEY,
    decision_id             TEXT,
    decision_class          TEXT,
    original_verdict        TEXT,
    expected_value          REAL,
    actual_value            REAL,
    expected_timeline_days  INTEGER,
    actual_timeline_days    INTEGER,
    expected_risk_level     TEXT,
    actual_risk_materialized INTEGER,
    composite_variance_score REAL,
    trust_recommendation    TEXT,
    value_direction         TEXT,
    risk_surprise           INTEGER,
    recorded_at             TEXT,
    FOREIGN KEY(decision_id) REFERENCES decisions(decision_id)
);

CREATE TABLE IF NOT EXISTS patterns (
    pattern_id              TEXT PRIMARY KEY,
    pattern_type            TEXT,
    decision_class          TEXT,
    description             TEXT,
    supporting_decision_ids TEXT,
    confidence_score        REAL,
    occurrence_count        INTEGER,
    first_seen              TEXT,
    last_seen               TEXT,
    status                  TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS causal_graphs (
    graph_id             TEXT PRIMARY KEY,
    decision_class       TEXT,
    variable_name        TEXT,
    variable_value_band  TEXT,
    outcome_direction    TEXT,
    correlation_strength REAL,
    sample_count         INTEGER,
    causal_confidence    TEXT,
    created_at           TEXT
);

CREATE TABLE IF NOT EXISTS weight_history (
    revision_id  TEXT PRIMARY KEY,
    yaml_section TEXT,
    key_name     TEXT,
    old_value    REAL,
    new_value    REAL,
    reason       TEXT,
    triggered_by TEXT,
    applied_at   TEXT
);
"""


class DatabaseManager:
    """
    Central SQLite persistence manager.
    Single connection, committed after every write.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ─── DECISIONS ────────────────────────────────────────────────────────────

    def store_decision(self, decision: DecisionObject, result: PipelineResult) -> str:
        """Persist a processed decision + full pipeline result JSON."""
        result_json = json.dumps(serialize_pipeline_result(result), default=str)
        rtql_stage = result.rtql_result.stage.value if result.rtql_result else "unknown"
        rtql_mult = result.rtql_result.trust_multiplier if result.rtql_result else 1.0
        verdict = result.execution_packet.verdict.value if result.execution_packet else "unknown"

        self.conn.execute(
            """INSERT OR REPLACE INTO decisions VALUES
               (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                result.decision_id,
                decision.title,
                decision.decision_class.value,
                decision.owner,
                verdict,
                result.net_value_score,
                result.trust_tier.value if result.trust_tier else "T0",
                result.trust_total,
                result.alignment_composite,
                result.priority_score,
                rtql_stage,
                rtql_mult,
                result_json,
                datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()
        return result.decision_id

    def get_decisions_by_class(self, decision_class: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE decision_class = ?", (decision_class,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_decisions(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM decisions ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def decision_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    # ─── OUTCOMES ─────────────────────────────────────────────────────────────

    def store_outcome(self, outcome: OutcomeRecord, variance: VarianceAnalysis) -> str:
        outcome_id = str(uuid.uuid4())
        value_var = float(variance.value_variance_pct) if variance.value_variance_pct else 0.0
        self.conn.execute(
            """INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                outcome_id,
                outcome.decision_id,
                outcome.decision_class.value if hasattr(outcome.decision_class, "value") else str(outcome.decision_class),
                outcome.original_verdict.value if hasattr(outcome.original_verdict, "value") else str(outcome.original_verdict),
                outcome.expected_value,
                outcome.actual_value,
                outcome.expected_timeline_days,
                outcome.actual_timeline_days,
                outcome.expected_risk_level,
                1 if outcome.actual_risk_materialized else 0,
                value_var,
                variance.trust_recommendation.value if hasattr(variance.trust_recommendation, "value") else str(variance.trust_recommendation),
                variance.value_direction.value if hasattr(variance.value_direction, "value") else str(variance.value_direction),
                1 if (outcome.actual_risk_materialized and outcome.expected_risk_level == "low") else 0,
                datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()
        return outcome_id

    def get_outcomes_by_class(self, decision_class: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM outcomes WHERE decision_class = ?", (decision_class,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_outcomes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM outcomes ORDER BY recorded_at").fetchall()
        return [dict(r) for r in rows]

    def get_decisions_with_outcomes(self) -> list[dict]:
        """JOIN decisions + outcomes for causal analysis."""
        rows = self.conn.execute(
            """SELECT d.*, o.actual_value, o.composite_variance_score,
                      o.value_direction, o.risk_surprise, o.actual_risk_materialized
               FROM decisions d
               INNER JOIN outcomes o ON d.decision_id = o.decision_id"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_variance_summary(self) -> dict:
        """Aggregate variance stats across all outcomes."""
        rows = self.conn.execute("SELECT * FROM outcomes").fetchall()
        if not rows:
            return {"total_outcomes": 0, "mean_variance": 0.0, "risk_surprise_rate": 0.0}
        variances = [r["composite_variance_score"] for r in rows]
        surprises = sum(r["risk_surprise"] for r in rows)
        return {
            "total_outcomes": len(rows),
            "mean_variance": sum(variances) / len(variances),
            "max_variance": max(variances),
            "min_variance": min(variances),
            "risk_surprise_rate": surprises / len(rows),
            "positive_outcomes": sum(1 for v in variances if v > 0),
            "negative_outcomes": sum(1 for v in variances if v < 0),
        }

    # ─── PATTERNS ─────────────────────────────────────────────────────────────

    def store_pattern(self, pattern: dict) -> str:
        pid = pattern.get("pattern_id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO patterns VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                pattern.get("pattern_type", "recurrence"),
                pattern.get("decision_class", ""),
                pattern.get("description", ""),
                json.dumps(pattern.get("supporting_decision_ids", [])),
                pattern.get("confidence_score", 0.0),
                pattern.get("occurrence_count", 0),
                pattern.get("first_seen", now),
                pattern.get("last_seen", now),
                pattern.get("status", "active"),
            ),
        )
        self.conn.commit()
        return pid

    def get_all_patterns(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM patterns WHERE status = 'active' ORDER BY confidence_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── CAUSAL GRAPHS ────────────────────────────────────────────────────────

    def store_causal_edge(self, edge: dict) -> str:
        gid = str(uuid.uuid4())
        self.conn.execute(
            """INSERT OR REPLACE INTO causal_graphs VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                gid,
                edge.get("decision_class", ""),
                edge.get("variable_name", ""),
                edge.get("variable_value_band", ""),
                edge.get("outcome_direction", "neutral"),
                edge.get("correlation_strength", 0.0),
                edge.get("sample_count", 0),
                edge.get("causal_confidence", "low"),
                datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()
        return gid

    def get_causal_graph(self, decision_class: str = None) -> list[dict]:
        if decision_class:
            rows = self.conn.execute(
                "SELECT * FROM causal_graphs WHERE decision_class = ? ORDER BY ABS(correlation_strength) DESC",
                (decision_class,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM causal_graphs ORDER BY ABS(correlation_strength) DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── WEIGHT HISTORY ───────────────────────────────────────────────────────

    def log_weight_change(
        self, section: str, key: str, old: float, new: float,
        reason: str, triggered_by: str
    ):
        self.conn.execute(
            "INSERT INTO weight_history VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), section, key, old, new,
                reason, triggered_by, datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()

    def get_weight_history(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM weight_history ORDER BY applied_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
