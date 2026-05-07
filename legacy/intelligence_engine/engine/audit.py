"""
Audit Logging & Decision Record Output System

Creates structured, timestamped audit records at each pipeline stage.
Produces serializable output for file-based storage, learning loop input,
and compliance review.
"""

import json
from datetime import datetime
from typing import Optional
from dataclasses import asdict

from .models import (
    DecisionObject, AuditRecord, PipelineResult,
    RTQLResult, CertificateChain, ExecutionPacket,
    TrustTier, AlignmentScores
)


# ─────────────────────────────────────────────
# AUDIT RECORD FACTORY
# ─────────────────────────────────────────────

class AuditLogger:
    """Collects audit records throughout the pipeline."""

    def __init__(self, decision_id: str):
        self.decision_id = decision_id
        self.records: list[AuditRecord] = []

    def log(self, stage: str, action: str,
            inputs: dict = None, outputs: dict = None,
            notes: str = "") -> AuditRecord:
        record = AuditRecord(
            decision_id=self.decision_id,
            pipeline_stage=stage,
            action_taken=action,
            inputs_snapshot=inputs or {},
            outputs_snapshot=outputs or {},
            notes=notes,
        )
        self.records.append(record)
        return record

    def log_validation(self, errors: list[str]) -> AuditRecord:
        return self.log(
            stage="validation",
            action="validate_decision_object",
            outputs={"errors": errors, "valid": len(errors) == 0},
            notes=f"{'Passed' if not errors else 'Failed'} with {len(errors)} errors"
        )

    def log_rtql(self, rtql_result: RTQLResult) -> AuditRecord:
        return self.log(
            stage="rtql_prefilter",
            action="classify_input",
            outputs={
                "stage": rtql_result.stage.value,
                "trust_multiplier": rtql_result.trust_multiplier,
                "write_target": rtql_result.write_target.value,
                "passed": rtql_result.passed,
                "blocking_reasons": rtql_result.blocking_reasons,
                "research_actions": rtql_result.research_actions,
            },
            notes=f"RTQL stage: {rtql_result.stage.value}"
        )

    def log_value_assessment(self, gross: int, penalty: int,
                              net: int, classification: str) -> AuditRecord:
        return self.log(
            stage="value_assessment",
            action="compute_value_scores",
            outputs={
                "gross_value": gross,
                "penalty": penalty,
                "net_value": net,
                "classification": classification,
            },
            notes=f"Net value: {net} ({classification})"
        )

    def log_trust_assessment(self, tier: TrustTier, total: int,
                              demotion_reasons: list[str]) -> AuditRecord:
        return self.log(
            stage="trust_assessment",
            action="calculate_trust_tier",
            outputs={
                "trust_tier": tier.value,
                "trust_total": total,
                "demotion_reasons": demotion_reasons,
            },
            notes=f"Trust tier: {tier.value} (total: {total})"
        )

    def log_alignment(self, alignment: AlignmentScores) -> AuditRecord:
        return self.log(
            stage="alignment_check",
            action="check_alignment",
            outputs={
                "doctrine_alignment": alignment.doctrine_alignment,
                "ethos_alignment": alignment.ethos_alignment,
                "first_principles_alignment": alignment.first_principles_alignment,
                "composite": round(alignment.composite(), 3),
                "anti_pattern_flags": alignment.anti_pattern_flags,
                "has_violations": alignment.has_violations(),
            },
            notes=f"Alignment composite: {alignment.composite():.3f}"
        )

    def log_certificate_chain(self, chain: CertificateChain) -> AuditRecord:
        chain_state = {}
        for name, cert in [("QC", chain.qc), ("VC", chain.vc),
                           ("TC", chain.tc), ("EC", chain.ec)]:
            if cert:
                chain_state[name] = {
                    "id": cert.certificate_id,
                    "status": cert.status.value,
                    "denial_reasons": cert.denial_reasons,
                }
            else:
                chain_state[name] = {"status": "not_attempted"}

        return self.log(
            stage="certification",
            action="build_certificate_chain",
            outputs={
                "chain_state": chain_state,
                "chain_complete": chain.chain_complete(),
                "highest_valid": chain.highest_valid().value if chain.highest_valid() else None,
            },
            notes=f"Chain complete: {chain.chain_complete()}"
        )

    def log_execution(self, packet: ExecutionPacket) -> AuditRecord:
        return self.log(
            stage="execution_authorization",
            action="run_7_gate_authorization",
            outputs={
                "verdict": packet.verdict.value,
                "gate_results": packet.gate_results,
                "blocking_gates": packet.blocking_gates,
                "escalation_tier": packet.escalation_tier,
                "escalation_sla": packet.escalation_sla,
                "escalation_recipients": packet.escalation_recipients,
            },
            notes=f"Verdict: {packet.verdict.value}"
        )

    def log_priority_score(self, score: float) -> AuditRecord:
        return self.log(
            stage="priority_scoring",
            action="calculate_priority_score",
            outputs={"priority_score": score},
            notes=f"Priority score: {score}"
        )


# ─────────────────────────────────────────────
# SERIALIZATION
# ─────────────────────────────────────────────

def serialize_pipeline_result(result: PipelineResult) -> dict:
    """Convert PipelineResult to a JSON-serializable dict."""
    output = {
        "decision_id": result.decision_id,
        "success": result.success,
        "validation_errors": result.validation_errors,
        "value_classification": result.value_classification,
        "net_value_score": result.net_value_score,
        "trust_tier": result.trust_tier.value,
        "trust_total": result.trust_total,
        "alignment_composite": round(result.alignment_composite, 3),
        "alignment_violations": result.alignment_violations,
        "priority_score": result.priority_score,
        "executive_summary": result.executive_summary,
    }

    if result.rtql_result:
        output["rtql"] = {
            "stage": result.rtql_result.stage.value,
            "trust_multiplier": result.rtql_result.trust_multiplier,
            "write_target": result.rtql_result.write_target.value,
            "passed": result.rtql_result.passed,
            "research_actions": result.rtql_result.research_actions,
        }

    if result.certificate_chain:
        chain = result.certificate_chain
        output["certificates"] = {}
        for name, cert in [("QC", chain.qc), ("VC", chain.vc),
                           ("TC", chain.tc), ("EC", chain.ec)]:
            if cert:
                output["certificates"][name] = {
                    "id": cert.certificate_id,
                    "status": cert.status.value,
                    "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
                    "expires_at": cert.expires_at.isoformat() if cert.expires_at else None,
                    "denial_reasons": cert.denial_reasons,
                }

    if result.execution_packet:
        ep = result.execution_packet
        output["execution"] = {
            "verdict": ep.verdict.value,
            "owner": ep.owner,
            "escalation_tier": ep.escalation_tier,
            "escalation_sla": ep.escalation_sla,
            "blocking_gates": ep.blocking_gates,
        }

    output["audit_trail"] = [
        {
            "audit_id": r.audit_id,
            "timestamp": r.timestamp,
            "stage": r.pipeline_stage,
            "action": r.action_taken,
            "notes": r.notes,
        }
        for r in result.audit_trail
    ]

    return output


def result_to_json(result: PipelineResult, indent: int = 2) -> str:
    """Serialize PipelineResult to formatted JSON string."""
    return json.dumps(serialize_pipeline_result(result), indent=indent)


# ─────────────────────────────────────────────
# EXECUTIVE SUMMARY GENERATOR
# ─────────────────────────────────────────────

def generate_executive_summary(result: PipelineResult) -> str:
    """Generate a human-readable executive summary of the pipeline result."""
    lines = []
    lines.append(f"DECISION: {result.decision_id}")
    lines.append(f"STATUS: {'PROCESSED' if result.success else 'FAILED'}")

    if result.validation_errors:
        lines.append(f"VALIDATION ERRORS: {len(result.validation_errors)}")
        for e in result.validation_errors:
            lines.append(f"  - {e}")
        return "\n".join(lines)

    if result.rtql_result:
        lines.append(f"RTQL STAGE: {result.rtql_result.stage.value}")
        if result.rtql_result.research_actions:
            lines.append(f"RTQL RESEARCH REQUIRED: {len(result.rtql_result.research_actions)} actions")

    lines.append(f"VALUE: {result.net_value_score} ({result.value_classification})")
    lines.append(f"TRUST: {result.trust_tier.value} (total: {result.trust_total})")
    lines.append(f"ALIGNMENT: {result.alignment_composite:.3f}")

    if result.alignment_violations:
        lines.append(f"ALIGNMENT VIOLATIONS: {', '.join(result.alignment_violations)}")

    if result.certificate_chain:
        chain = result.certificate_chain
        cert_status = []
        for name, cert in [("QC", chain.qc), ("VC", chain.vc),
                           ("TC", chain.tc), ("EC", chain.ec)]:
            if cert:
                cert_status.append(f"{name}:{cert.status.value}")
            else:
                cert_status.append(f"{name}:none")
        lines.append(f"CERTIFICATES: {' | '.join(cert_status)}")

    if result.execution_packet:
        ep = result.execution_packet
        lines.append(f"VERDICT: {ep.verdict.value}")
        if ep.escalation_tier:
            lines.append(f"ESCALATION: Tier {ep.escalation_tier} ({ep.escalation_sla})")
        if ep.blocking_gates:
            lines.append(f"BLOCKING: {len(ep.blocking_gates)} gates")
            for bg in ep.blocking_gates:
                lines.append(f"  - {bg}")

    lines.append(f"PRIORITY SCORE: {result.priority_score}")

    return "\n".join(lines)
