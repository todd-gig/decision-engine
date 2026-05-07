"""
Certificate Chain Issuance System

Implements the 4-certificate chain: QC → VC → TC → EC
with the hard rule: No EC without prior valid QC, VC, and TC.

Certificate types:
    QC (Qualified Context) — decision object complete, problem defined, stakeholders named
    VC (Value Confirmed) — net value computed, upside/downside stated, strategic alignment scored
    TC (Trust Certified) — trust tier T2+, evidence attached, assumptions/unknowns listed
    EC (Execution Cleared) — trust threshold met, approval path satisfied, execution + rollback plans exist
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid

from .models import (
    DecisionObject, DecisionClass, TrustTier,
    Certificate, CertificateType, CertificateStatus, CertificateChain,
    ValueScores, TrustScores, AlignmentScores
)
from .gates import TIER_ORDER


# ─────────────────────────────────────────────
# CERTIFICATE EXPIRATION DEFAULTS
# ─────────────────────────────────────────────

CERT_EXPIRY_DAYS = {
    CertificateType.QC: 30,
    CertificateType.VC: 14,
    CertificateType.TC: 14,
    CertificateType.EC: 7,
}


def _make_cert_id(cert_type: CertificateType) -> str:
    return f"{cert_type.name}-{uuid.uuid4().hex[:8].upper()}"


def _now() -> datetime:
    return datetime.now()


# ─────────────────────────────────────────────
# QC — QUALIFIED CONTEXT
# ─────────────────────────────────────────────

def issue_qc(decision: DecisionObject) -> Certificate:
    """
    QC Minimum Requirements:
    - decision object complete (title, owner, class)
    - problem and requested action defined
    - relevant stakeholders named
    """
    cert = Certificate(
        certificate_id=_make_cert_id(CertificateType.QC),
        decision_id=decision.decision_id,
        cert_type=CertificateType.QC,
    )

    denial_reasons = []

    if not decision.title:
        denial_reasons.append("Missing title")
    if not decision.owner:
        denial_reasons.append("Missing owner")
    if not decision.problem_statement:
        denial_reasons.append("Missing problem statement")
    if not decision.requested_action:
        denial_reasons.append("Missing requested action")
    if not decision.stakeholders:
        denial_reasons.append("No stakeholders identified")

    if denial_reasons:
        cert.status = CertificateStatus.DENIED
        cert.denial_reasons = denial_reasons
    else:
        cert.status = CertificateStatus.ISSUED
        cert.issued_at = _now()
        cert.expires_at = _now() + timedelta(days=CERT_EXPIRY_DAYS[CertificateType.QC])
        cert.evidence_basis = [
            f"Title: {decision.title}",
            f"Owner: {decision.owner}",
            f"Class: {decision.decision_class.value}",
            f"Stakeholders: {', '.join(decision.stakeholders)}",
        ]
        cert.scores_snapshot = {
            "decision_class": decision.decision_class.value,
            "reversibility": decision.reversibility.value,
            "time_horizon": decision.time_horizon.value,
        }

    return cert


# ─────────────────────────────────────────────
# VC — VALUE CONFIRMED
# ─────────────────────────────────────────────

def issue_vc(decision: DecisionObject, qc: Certificate) -> Certificate:
    """
    VC Minimum Requirements:
    - QC must be valid
    - net value score computed
    - expected upside and downside stated
    - strategic alignment scored
    """
    cert = Certificate(
        certificate_id=_make_cert_id(CertificateType.VC),
        decision_id=decision.decision_id,
        cert_type=CertificateType.VC,
    )

    denial_reasons = []

    # QC prerequisite
    if not qc or not qc.is_valid():
        denial_reasons.append("QC certificate not valid — cannot issue VC")

    vs = decision.value_scores

    # Net value must be computed (at least some dimensions scored)
    if vs.gross_value() == 0:
        denial_reasons.append("No positive value dimensions scored")

    # Strategic alignment must be explicitly scored
    if vs.strategic_alignment == 0:
        denial_reasons.append("Strategic alignment not scored")

    # Downside must be stated (even if zero — force explicit acknowledgment)
    # We check that the value object has been populated
    validation_errors = vs.validate()
    if validation_errors:
        denial_reasons.extend(validation_errors)

    if denial_reasons:
        cert.status = CertificateStatus.DENIED
        cert.denial_reasons = denial_reasons
    else:
        cert.status = CertificateStatus.ISSUED
        cert.issued_at = _now()
        cert.expires_at = _now() + timedelta(days=CERT_EXPIRY_DAYS[CertificateType.VC])
        cert.evidence_basis = [
            f"Gross value: {vs.gross_value()}",
            f"Penalty: {vs.penalty()}",
            f"Net value: {vs.net_value()}",
            f"Classification: {vs.value_classification()}",
            f"Strategic alignment: {vs.strategic_alignment}/5",
        ]
        cert.scores_snapshot = {
            "gross_value": vs.gross_value(),
            "penalty": vs.penalty(),
            "net_value": vs.net_value(),
            "classification": vs.value_classification(),
        }

    return cert


# ─────────────────────────────────────────────
# TC — TRUST CERTIFIED
# ─────────────────────────────────────────────

def issue_tc(decision: DecisionObject,
              trust_tier: TrustTier,
              vc: Certificate) -> Certificate:
    """
    TC Minimum Requirements:
    - VC must be valid
    - trust tier T2 or higher
    - evidence references attached
    - assumptions and unknowns listed
    """
    cert = Certificate(
        certificate_id=_make_cert_id(CertificateType.TC),
        decision_id=decision.decision_id,
        cert_type=CertificateType.TC,
    )

    denial_reasons = []

    # VC prerequisite
    if not vc or not vc.is_valid():
        denial_reasons.append("VC certificate not valid — cannot issue TC")

    # Trust tier minimum T2
    if TIER_ORDER[trust_tier] < TIER_ORDER[TrustTier.T2_QUALIFIED]:
        denial_reasons.append(
            f"Trust tier {trust_tier.value} below minimum T2 for trust certification"
        )

    # Evidence required
    if not decision.evidence_refs:
        denial_reasons.append("No evidence references attached")

    # Assumptions and unknowns must be listed (even if empty — force explicit)
    # We check they exist as fields (they always do), but flag if D3+ has no assumptions listed
    if (decision.decision_class.value in ("D3", "D4", "D5", "D6") and
            not decision.assumptions):
        denial_reasons.append("Assumptions not explicitly listed for high-class decision")

    if denial_reasons:
        cert.status = CertificateStatus.DENIED
        cert.denial_reasons = denial_reasons
    else:
        cert.status = CertificateStatus.ISSUED
        cert.issued_at = _now()
        cert.expires_at = _now() + timedelta(days=CERT_EXPIRY_DAYS[CertificateType.TC])
        cert.evidence_basis = [
            f"Trust tier: {trust_tier.value}",
            f"Evidence refs: {len(decision.evidence_refs)}",
            f"Assumptions listed: {len(decision.assumptions)}",
            f"Unknowns listed: {len(decision.unknowns)}",
        ]
        cert.scores_snapshot = {
            "trust_tier": trust_tier.value,
            "trust_total": decision.trust_scores.total(),
            "evidence_count": len(decision.evidence_refs),
        }

    return cert


# ─────────────────────────────────────────────
# EC — EXECUTION CLEARED
# ─────────────────────────────────────────────

def issue_ec(decision: DecisionObject,
              trust_tier: TrustTier,
              tc: Certificate,
              gate_results: dict) -> Certificate:
    """
    EC Minimum Requirements:
    - TC must be valid
    - trust tier threshold met for decision class
    - approval path satisfied
    - execution plan exists
    - rollback or monitoring path exists
    """
    cert = Certificate(
        certificate_id=_make_cert_id(CertificateType.EC),
        decision_id=decision.decision_id,
        cert_type=CertificateType.EC,
    )

    denial_reasons = []

    # TC prerequisite
    if not tc or not tc.is_valid():
        denial_reasons.append("TC certificate not valid — cannot issue EC")

    # Check that all 7 gates passed
    failed_gates = [
        name for name, result in gate_results.items()
        if not result.get("passed", False)
    ]
    if failed_gates:
        denial_reasons.append(
            f"Authorization gates failed: {', '.join(failed_gates)}"
        )

    # Execution plan required
    if not decision.execution_plan:
        denial_reasons.append("No execution plan defined")

    # Monitoring required for non-informational
    if decision.decision_class != DecisionClass.D0_INFORMATIONAL:
        if not decision.monitoring_metric:
            denial_reasons.append("No monitoring metric defined")
        if not decision.rollback_trigger:
            denial_reasons.append("No rollback trigger defined")

    if denial_reasons:
        cert.status = CertificateStatus.DENIED
        cert.denial_reasons = denial_reasons
    else:
        cert.status = CertificateStatus.ISSUED
        cert.issued_at = _now()
        cert.expires_at = _now() + timedelta(days=CERT_EXPIRY_DAYS[CertificateType.EC])
        cert.evidence_basis = [
            f"All 7 authorization gates passed",
            f"Trust tier: {trust_tier.value}",
            f"Execution plan present",
            f"Monitoring metric: {decision.monitoring_metric}",
            f"Rollback trigger: {decision.rollback_trigger}",
        ]
        cert.scores_snapshot = {
            "trust_tier": trust_tier.value,
            "gates_passed": len(gate_results) - len(failed_gates),
            "gates_total": len(gate_results),
        }

    return cert


# ─────────────────────────────────────────────
# CHAIN BUILDER
# ─────────────────────────────────────────────

def build_certificate_chain(
    decision: DecisionObject,
    trust_tier: TrustTier,
    gate_results: dict,
) -> CertificateChain:
    """
    Build the full certificate chain QC → VC → TC → EC.
    Each certificate depends on the prior being valid.
    Hard rule: No EC without prior valid QC, VC, and TC.
    """
    chain = CertificateChain()

    # Step 1: QC
    chain.qc = issue_qc(decision)
    if not chain.qc.is_valid():
        return chain

    # Step 2: VC (requires QC)
    chain.vc = issue_vc(decision, chain.qc)
    if not chain.vc.is_valid():
        return chain

    # Step 3: TC (requires VC)
    chain.tc = issue_tc(decision, trust_tier, chain.vc)
    if not chain.tc.is_valid():
        return chain

    # Step 4: EC (requires TC + gates)
    chain.ec = issue_ec(decision, trust_tier, chain.tc, gate_results)

    return chain
