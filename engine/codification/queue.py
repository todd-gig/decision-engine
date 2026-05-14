"""Proposal queue — write proposals + read/approve them.

v0 surface — the analyzer/proposer/simulator come later. This module
ships the proposal store and the human-approval workflow that
Founder/Owner UI consumes.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from . import storage


class ProposalStatus(str, Enum):
    OPEN = "open"
    APPROVED_SHIP = "approved_ship"
    APPROVED_FALLBACK = "approved_fallback"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class SimulationResult:
    n: int
    divergence_p50: float
    divergence_p90: float
    cost_savings_usd: Optional[float] = None
    latency_savings_ms: Optional[int] = None


@dataclass
class CodificationProposal:
    candidate_pv: str           # source prompt_version
    candidate_sv: str           # source schema_version
    candidate_score: float
    analyzer_run_at: str        # ISO-8601
    proposed_python: str
    proposed_tests: str
    why: str
    sim: SimulationResult
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    queue_status: str = ProposalStatus.OPEN.value


def open_proposal(
    proposal: CodificationProposal,
    db_path: str | None = None,
) -> dict:
    """Insert a new proposal into the queue with status='open'."""
    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO codification_proposals (
                proposal_id, candidate_pv, candidate_sv, candidate_score,
                analyzer_run_at, proposed_python, proposed_tests, why,
                sim_n, sim_divergence_p50, sim_divergence_p90,
                sim_cost_savings_usd, sim_latency_savings_ms,
                queue_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.proposal_id,
                proposal.candidate_pv,
                proposal.candidate_sv,
                proposal.candidate_score,
                proposal.analyzer_run_at,
                proposal.proposed_python,
                proposal.proposed_tests,
                proposal.why,
                proposal.sim.n,
                proposal.sim.divergence_p50,
                proposal.sim.divergence_p90,
                proposal.sim.cost_savings_usd,
                proposal.sim.latency_savings_ms,
                ProposalStatus.OPEN.value,
            ),
        )
    finally:
        conn.close()
    return _to_dict_with_status(proposal, ProposalStatus.OPEN.value)


def get_proposal(proposal_id: str, db_path: str | None = None) -> Optional[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = __import__("sqlite3").Row
        row = conn.execute(
            "SELECT * FROM codification_proposals WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_proposals(
    status: str | None = None,
    db_path: str | None = None,
    limit: int = 200,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = __import__("sqlite3").Row
        if status is None:
            cur = conn.execute(
                "SELECT * FROM codification_proposals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM codification_proposals
                WHERE queue_status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def approve_proposal(
    proposal_id: str,
    *,
    approver_user_id: str,
    approval_why: str,
    new_status: str,
    shipped_pr_url: str | None = None,
    db_path: str | None = None,
) -> dict:
    """Move a proposal out of 'open'. Requires explicit reasoning per always-record-WHY."""
    if new_status not in {
        ProposalStatus.APPROVED_SHIP.value,
        ProposalStatus.APPROVED_FALLBACK.value,
        ProposalStatus.REJECTED.value,
        ProposalStatus.DEFERRED.value,
    }:
        raise ValueError(
            f"new_status must be approved_ship | approved_fallback | rejected | deferred; "
            f"got {new_status!r}"
        )
    now = datetime.now(tz=timezone.utc).isoformat()
    conn = storage.get_connection(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE codification_proposals
            SET queue_status = ?,
                approver_user_id = ?,
                approved_at = ?,
                approval_why = ?,
                shipped_pr_url = ?
            WHERE proposal_id = ? AND queue_status = ?
            """,
            (
                new_status, approver_user_id, now, approval_why,
                shipped_pr_url, proposal_id, ProposalStatus.OPEN.value,
            ),
        )
        if cur.rowcount == 0:
            raise LookupError(
                f"proposal {proposal_id!r} not found or already decided"
            )
    finally:
        conn.close()
    return get_proposal(proposal_id, db_path=db_path)  # type: ignore[return-value]


def _to_dict_with_status(proposal: CodificationProposal, status: str) -> dict:
    body = asdict(proposal)
    body["queue_status"] = status
    return body
