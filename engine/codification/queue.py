"""Proposal queue — write proposals + read/approve them.

v0 surface — the analyzer/proposer/simulator come later. This module
ships the proposal store and the human-approval workflow that
Founder/Owner UI consumes.

v0.5: `approve_and_certify` mints a CodificationCertificate when an
approver crosses the proposal into `approved_ship` / `approved_fallback`.
Certificate generation is HMAC-signed + persisted with a matching .md
file (see `engine/codification/certificate.py`).
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


# ── v0.5: approval that mints a CodificationCertificate ──────────────────


def approve_and_certify(
    proposal_id: str,
    *,
    approver_user_id: str,
    approval_why: str,
    new_status: str,
    decision_class: str,
    evidence_decision_ids: list[str],
    proposed_spec: str,
    prompt_version: str,
    schema_version: str,
    additional_signers: list[str] | None = None,
    shipped_pr_url: str | None = None,
    db_path: str | None = None,
    secret_key: str | None = None,
) -> dict:
    """Approve a proposal AND mint the governing CodificationCertificate.

    Authorization is enforced via `signoff.is_authorized` — if the approver
    isn't in the canonical signer set for `decision_class`, this raises
    `PermissionError`. Caller should map that to HTTP 403.

    `additional_signers` lets the caller add co-signers (used for
    `doctrine-touching` proposals where both founder + owner must sign).
    """
    # Local imports avoid circular surface at module import time.
    from .signoff import is_authorized, required_signers, has_quorum
    from .certificate import CodificationCertificate, persist_certificate

    if new_status not in {
        ProposalStatus.APPROVED_SHIP.value,
        ProposalStatus.APPROVED_FALLBACK.value,
    }:
        raise ValueError(
            "approve_and_certify is only for APPROVED_SHIP / APPROVED_FALLBACK; "
            f"got {new_status!r}. Use approve_proposal() for rejections."
        )

    if not is_authorized(approver_user_id, decision_class):
        raise PermissionError(
            f"{approver_user_id!r} is not in the required signer set "
            f"for decision_class={decision_class!r}; "
            f"required={required_signers(decision_class)}"
        )

    signers = sorted({approver_user_id, *(additional_signers or [])})
    if not has_quorum(signers, decision_class):
        raise PermissionError(
            f"signer set {signers!r} does not meet quorum for "
            f"decision_class={decision_class!r}; "
            f"required={required_signers(decision_class)}"
        )

    # Build + sign + persist certificate FIRST so the proposal flip
    # never lacks a backing cert.
    cert = CodificationCertificate(
        candidate_id=proposal_id,
        signers=signers,
        decision_class=decision_class,
        reasoning=approval_why,
        evidence_decision_ids=list(evidence_decision_ids),
        proposed_spec=proposed_spec,
        prompt_version=prompt_version,
        schema_version=schema_version,
    )
    cert.sign(secret_key)
    persist_certificate(cert, db_path=db_path)

    # Now flip the proposal. If this fails (e.g. already-decided), the
    # certificate row is orphan but harmless — operators can re-approve
    # against a fresh certificate. The DB cert table is append-only.
    row = approve_proposal(
        proposal_id,
        approver_user_id=approver_user_id,
        approval_why=approval_why,
        new_status=new_status,
        shipped_pr_url=shipped_pr_url,
        db_path=db_path,
    )
    row["certificate"] = cert.to_dict()
    return row
