"""codification — proposal queue lifecycle."""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.codification import (
    CodificationProposal,
    ProposalStatus,
    SimulationResult,
    approve_proposal,
    get_proposal,
    list_proposals,
    open_proposal,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "codification_proposals.db")


def _new_proposal(**kwargs) -> CodificationProposal:
    defaults = dict(
        candidate_pv="explain_recs.v1.0",
        candidate_sv="coaching_prose.v1",
        candidate_score=0.85,
        analyzer_run_at=datetime.now(tz=timezone.utc).isoformat(),
        proposed_python="def explain(recs):\n    return f'Top: {recs[0]}'",
        proposed_tests="def test_explain():\n    assert explain([{'name':'A'}])",
        why="High volume + low variance; deterministic top-rec pattern",
        sim=SimulationResult(
            n=120,
            divergence_p50=0.05,
            divergence_p90=0.12,
            cost_savings_usd=15.0,
            latency_savings_ms=8000,
        ),
    )
    defaults.update(kwargs)
    return CodificationProposal(**defaults)


def test_open_proposal_writes_row_with_status_open(tmp_db):
    p = _new_proposal()
    body = open_proposal(p, db_path=tmp_db)
    assert body["proposal_id"] == p.proposal_id
    assert body["queue_status"] == "open"

    row = get_proposal(p.proposal_id, db_path=tmp_db)
    assert row is not None
    assert row["queue_status"] == "open"
    assert row["candidate_score"] == 0.85
    assert row["sim_n"] == 120


def test_get_proposal_returns_none_for_missing(tmp_db):
    assert get_proposal("does-not-exist", db_path=tmp_db) is None


def test_list_proposals_filters_by_status(tmp_db):
    p1 = _new_proposal()
    p2 = _new_proposal()
    open_proposal(p1, db_path=tmp_db)
    open_proposal(p2, db_path=tmp_db)
    approve_proposal(
        p1.proposal_id,
        approver_user_id="todd",
        approval_why="ship — divergence acceptable",
        new_status=ProposalStatus.APPROVED_SHIP.value,
        shipped_pr_url="https://github.com/.../pull/1",
        db_path=tmp_db,
    )
    open_only = list_proposals(status="open", db_path=tmp_db)
    assert len(open_only) == 1
    assert open_only[0]["proposal_id"] == p2.proposal_id

    approved = list_proposals(status="approved_ship", db_path=tmp_db)
    assert len(approved) == 1
    assert approved[0]["proposal_id"] == p1.proposal_id


def test_approve_proposal_sets_metadata(tmp_db):
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    row = approve_proposal(
        p.proposal_id,
        approver_user_id="todd",
        approval_why="rules match observed pattern; ship as fallback",
        new_status=ProposalStatus.APPROVED_FALLBACK.value,
        db_path=tmp_db,
    )
    assert row["queue_status"] == "approved_fallback"
    assert row["approver_user_id"] == "todd"
    assert "fallback" in row["approval_why"]
    assert row["approved_at"] is not None


def test_approve_rejects_invalid_status(tmp_db):
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with pytest.raises(ValueError):
        approve_proposal(
            p.proposal_id,
            approver_user_id="x",
            approval_why="y",
            new_status="held",  # not in allowed set
            db_path=tmp_db,
        )


def test_approve_already_decided_raises(tmp_db):
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    approve_proposal(
        p.proposal_id,
        approver_user_id="todd",
        approval_why="first decision",
        new_status=ProposalStatus.APPROVED_SHIP.value,
        db_path=tmp_db,
    )
    with pytest.raises(LookupError):
        approve_proposal(
            p.proposal_id,
            approver_user_id="todd",
            approval_why="second decision should fail",
            new_status=ProposalStatus.REJECTED.value,
            db_path=tmp_db,
        )


def test_approve_unknown_id_raises(tmp_db):
    # No proposal stored; approve_proposal should raise LookupError.
    with pytest.raises(LookupError):
        approve_proposal(
            "nonexistent-id",
            approver_user_id="x",
            approval_why="y",
            new_status=ProposalStatus.REJECTED.value,
            db_path=tmp_db,
        )


def test_schema_check_constraint_enforced(tmp_db):
    """SQLite CHECK on queue_status should reject direct invalid writes."""
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE codification_proposals SET queue_status='bogus' WHERE proposal_id = ?",
                (p.proposal_id,),
            )
