"""
Gate 8 (Drift Sentinel feedback) tests.

Verifies the recursive self-governance loop: a decision-engine pipeline
run blocks AUTO_EXECUTE when the drift_sentinel has open critical findings
in the decision's domain, unless the decision text acknowledges the
relevant rule_id.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gates import gate_8_drift_check
from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _seed_drift_db(
    *,
    artifacts: list[tuple[str, str, str]] = (),
    scan_age_hours: float = 1.0,
) -> Path:
    """Create a temp drift_history.db with given (rule_id, severity, artifact) rows.

    `scan_age_hours` controls how old the scan record is (for lookback tests).
    """
    db_file = Path(tempfile.mkdtemp()) / "drift_history.db"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE scans (
            scan_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            sources TEXT NOT NULL,
            total_artifacts INTEGER NOT NULL,
            critical INTEGER NOT NULL,
            major INTEGER NOT NULL,
            minor INTEGER NOT NULL,
            info INTEGER NOT NULL
        );
        CREATE TABLE violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            artifact TEXT NOT NULL,
            location TEXT,
            excerpt TEXT
        );
    """)
    scan_id = uuid.uuid4().hex[:12]
    ts = (datetime.now(timezone.utc) - timedelta(hours=scan_age_hours)
          ).isoformat()
    crit = sum(1 for _, sev, _ in artifacts if sev == "critical")
    conn.execute(
        "INSERT INTO scans VALUES (?,?,?,?,?,?,?,?)",
        (scan_id, ts, "test", len(artifacts), crit, 0, 0, 0),
    )
    for rule_id, sev, art in artifacts:
        conn.execute(
            "INSERT INTO violations(scan_id, rule_id, severity, artifact) "
            "VALUES (?,?,?,?)",
            (scan_id, rule_id, sev, art),
        )
    conn.commit()
    conn.close()
    return db_file


def _decision(
    *,
    title: str = "Refactor module",
    requested_action: str = "Refactor the affected module",
    evidence_refs: list[str] | None = None,
    problem_statement: str = "Module needs refactor",
) -> DecisionObject:
    return DecisionObject(
        title=title,
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        owner="engineer",
        time_horizon=TimeHorizon.IMMEDIATE,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        problem_statement=problem_statement,
        requested_action=requested_action,
        evidence_refs=evidence_refs or ["docs/spec.md"],
        value_scores=ValueScores(),
        trust_scores=TrustScores(),
        alignment_scores=AlignmentScores(),
    )


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────


def test_gate_8_passes_when_db_missing():
    """No drift history → gate skips with warning, passes."""
    nonexistent = Path("/tmp/definitely-not-a-real-drift-db.db")
    decision = _decision()
    passed, reason = gate_8_drift_check(decision, drift_db_path=nonexistent)
    assert passed
    assert "skipped" in reason.lower()


def test_gate_8_passes_when_no_critical_drift():
    """DB exists but no critical findings → pass."""
    db = _seed_drift_db(artifacts=[
        ("MIN-001", "minor", "carmen-beach/apps/web/foo.ts"),
    ])
    decision = _decision(evidence_refs=["docs/foo.md"])
    passed, reason = gate_8_drift_check(decision, drift_db_path=db)
    assert passed


def test_gate_8_passes_when_drift_not_in_domain():
    """Critical drift exists but doesn't touch this decision's domain → pass."""
    db = _seed_drift_db(artifacts=[
        ("CRIT-008", "critical", "gigaton-engine/pricing_engine/engine.py"),
    ])
    decision = _decision(
        title="Rename onboarding email subject",
        requested_action="Update marketing copy",
        evidence_refs=["marketing/email_test.csv"],
    )
    passed, reason = gate_8_drift_check(decision, drift_db_path=db)
    assert passed


def test_gate_8_blocks_when_drift_touches_domain():
    """Critical drift in same path/module → BLOCK."""
    db = _seed_drift_db(artifacts=[
        ("CRIT-008", "critical",
         "gigaton-engine/pricing_engine/engine.py"),
    ])
    decision = _decision(
        title="Update pricing engine output schema",
        requested_action="Refactor gigaton-engine/pricing_engine/engine.py "
                         "to expose recommended_price more cleanly",
        evidence_refs=["gigaton-engine/pricing_engine/engine.py"],
    )
    passed, reason = gate_8_drift_check(decision, drift_db_path=db)
    assert not passed
    assert "CRIT-008" in reason


def test_gate_8_acknowledgment_lets_remediation_through():
    """Decision that mentions rule_id is treated as remediation → pass."""
    db = _seed_drift_db(artifacts=[
        ("CRIT-008", "critical",
         "gigaton-engine/pricing_engine/engine.py"),
    ])
    decision = _decision(
        title="Fix CRIT-008 in pricing_engine",
        problem_statement="Critical drift CRIT-008 — pricing outputs lack "
                          "assumptions[]. This decision remediates that.",
        requested_action="Refactor "
                         "gigaton-engine/pricing_engine/engine.py to "
                         "populate assumptions[] in PricingRecommendation",
        evidence_refs=["gigaton-engine/pricing_engine/engine.py"],
    )
    passed, reason = gate_8_drift_check(decision, drift_db_path=db)
    assert passed
    # Acknowledged set should appear in the pass message
    assert "CRIT-008" in reason or "acknowledged" in reason.lower()


def test_gate_8_lookback_window_excludes_old_scans():
    """Scans older than lookback_days are excluded."""
    db = _seed_drift_db(
        artifacts=[
            ("CRIT-001", "critical",
             "gigaton-engine/multi_agent/api.py"),
        ],
        scan_age_hours=24 * 60,  # 60 days old
    )
    decision = _decision(
        title="Update gigaton-engine multi_agent API",
        requested_action="Refactor gigaton-engine/multi_agent/api.py",
        evidence_refs=["gigaton-engine/multi_agent/api.py"],
    )
    passed, reason = gate_8_drift_check(
        decision, drift_db_path=db, lookback_days=30,
    )
    assert passed  # Old scan ignored


def test_gate_8_only_uses_most_recent_scan():
    """If the latest scan no longer reports a violation, it's resolved."""
    # Seed with two scans manually
    db_dir = Path(tempfile.mkdtemp())
    db = db_dir / "drift_history.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE scans (
            scan_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            sources TEXT NOT NULL,
            total_artifacts INTEGER NOT NULL,
            critical INTEGER NOT NULL,
            major INTEGER NOT NULL,
            minor INTEGER NOT NULL,
            info INTEGER NOT NULL
        );
        CREATE TABLE violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            artifact TEXT NOT NULL,
            location TEXT,
            excerpt TEXT
        );
    """)
    now = datetime.now(timezone.utc)
    # Older scan flagged the issue
    conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?,?,?)",
                 ("old-scan",
                  (now - timedelta(days=2)).isoformat(),
                  "test", 1, 1, 0, 0, 0))
    conn.execute(
        "INSERT INTO violations(scan_id, rule_id, severity, artifact) "
        "VALUES (?,?,?,?)",
        ("old-scan", "CRIT-008", "critical",
         "gigaton-engine/pricing_engine/engine.py"))
    # Newer scan shows it resolved (no violations)
    conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?,?,?)",
                 ("new-scan", now.isoformat(),
                  "test", 0, 0, 0, 0, 0))
    conn.commit()
    conn.close()
    decision = _decision(
        title="Update pricing_engine",
        evidence_refs=["gigaton-engine/pricing_engine/engine.py"],
    )
    passed, reason = gate_8_drift_check(decision, drift_db_path=db)
    assert passed  # Latest scan is clean


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
