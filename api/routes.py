"""
API Routes — Unified decision engine endpoints.

Exposes the full pipeline, simplified evaluation, state transitions,
outcome recording, learning analytics, and configuration.
"""

from fastapi import APIRouter
from typing import Optional

from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks,
)
from engine.config import EngineConfig, load_config
from engine.pipeline import process_decision
from engine.audit import serialize_pipeline_result
from engine.state_machine import (
    can_transition as sm_can_transition,
    advance_state, get_lifecycle_status,
    STATE_CERTIFICATE_MAP,
)
from engine.learning_loop import record_outcome as ll_record_outcome, LearningStore

# Simplified evaluation imports (backward compat)
from engine.weighted_scoring import compute_weighted_value as _simple_value
from engine.scoring import calculate_trust_tier

from .schemas import (
    FullDecisionRequest, SimpleEvaluationRequest,
    TransitionRequest, TransitionResponse,
    OutcomeRequest, PipelineResponse, AuditEntry,
)

router = APIRouter()

# Load config once at startup
_config: Optional[EngineConfig] = None


def _get_config() -> EngineConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


# ── Health & Config ──


@router.get("/health")
def health():
    return {"status": "ok", "engine_version": "2.0.0"}


@router.get("/v1/config")
def get_config():
    config = _get_config()
    return {
        "thresholds": {
            "value_execute_min": config.thresholds.value_execute_min,
            "value_escalate_min": config.thresholds.value_escalate_min,
            "trust_execute_min": config.thresholds.trust_execute_min,
            "trust_recommend_min": config.thresholds.trust_recommend_min,
        },
        "trust_multiplier": config.trust_multiplier,
        "valid_transitions": config.valid_transitions,
    }


# ── Full Pipeline ──


def _build_decision_object(req: FullDecisionRequest) -> DecisionObject:
    """Convert API request into engine DecisionObject."""
    vs = req.value_scores
    ts = req.trust_scores
    als = req.alignment_scores

    rtql = None
    if req.rtql_input:
        ri = req.rtql_input
        rtql = RTQLInput(
            claim=ri.claim,
            source=ri.source,
            is_identifiable=ri.is_identifiable,
            has_provenance=ri.has_provenance,
            scores=RTQLScores(
                source_integrity=ri.scores.source_integrity,
                exposure_count=ri.scores.exposure_count,
                independence=ri.scores.independence,
                explainability=ri.scores.explainability,
                replicability=ri.scores.replicability,
                adversarial_robustness=ri.scores.adversarial_robustness,
                novelty_yield=ri.scores.novelty_yield,
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=ri.causal_checks.reveals_causal_mechanism,
                is_irreducible=ri.causal_checks.is_irreducible,
                survives_authority_removal=ri.causal_checks.survives_authority_removal,
                survives_context_shift=ri.causal_checks.survives_context_shift,
            ),
        )

    return DecisionObject(
        title=req.title,
        decision_class=DecisionClass(req.decision_class),
        owner=req.owner,
        time_horizon=TimeHorizon(req.time_horizon),
        reversibility=ReversibilityTag(req.reversibility),
        problem_statement=req.problem_statement,
        requested_action=req.requested_action,
        context_summary=req.context_summary,
        stakeholders=req.stakeholders,
        constraints=req.constraints,
        value_scores=ValueScores(
            revenue_impact=vs.revenue_impact,
            cost_efficiency=vs.cost_efficiency,
            time_leverage=vs.time_leverage,
            strategic_alignment=vs.strategic_alignment,
            customer_human_benefit=vs.customer_human_benefit,
            knowledge_asset_creation=vs.knowledge_asset_creation,
            compounding_potential=vs.compounding_potential,
            reversibility=vs.reversibility,
            downside_risk=vs.downside_risk,
            execution_drag=vs.execution_drag,
            uncertainty=vs.uncertainty,
            ethical_misalignment=vs.ethical_misalignment,
        ),
        trust_scores=TrustScores(
            evidence_quality=ts.evidence_quality,
            logic_integrity=ts.logic_integrity,
            outcome_history=ts.outcome_history,
            context_fit=ts.context_fit,
            stakeholder_clarity=ts.stakeholder_clarity,
            risk_containment=ts.risk_containment,
            auditability=ts.auditability,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=als.doctrine_alignment,
            ethos_alignment=als.ethos_alignment,
            first_principles_alignment=als.first_principles_alignment,
            anti_pattern_flags=als.anti_pattern_flags,
            applied_principles=als.applied_principles,
        ),
        rtql_input=rtql,
        evidence_refs=req.evidence_refs,
        assumptions=req.assumptions,
        unknowns=req.unknowns,
        required_approvals=req.required_approvals,
        execution_plan=req.execution_plan,
        monitoring_metric=req.monitoring_metric,
        rollback_trigger=req.rollback_trigger,
        review_date=req.review_date,
        current_state=req.current_state,
        actor_role=req.actor_role,
        has_missing_data=req.has_missing_data,
        ethical_conflict=req.ethical_conflict,
    )


@router.post("/v1/decisions/process", response_model=PipelineResponse)
def process_decision_endpoint(req: FullDecisionRequest):
    """
    Full pipeline processing — the primary endpoint.

    Accepts a complete DecisionObject and runs the full 9-stage pipeline:
    validation → RTQL → value → trust → authority → certificates →
    7-gate authorization → state machine → priority scoring.

    Returns verdict, certificates, audit trail, and executive summary.
    """
    config = _get_config()
    decision = _build_decision_object(req)
    result = process_decision(decision, config)

    # Build response
    serialized = serialize_pipeline_result(result)
    verdict = ""
    reason = ""
    if result.execution_packet:
        verdict = result.execution_packet.verdict.value
        blocking = result.execution_packet.blocking_gates
        reason = blocking[0] if blocking else "all_gates_passed"

    cert_status = {}
    if result.certificate_chain:
        chain = result.certificate_chain
        for name, cert in [("QC", chain.qc), ("VC", chain.vc),
                           ("TC", chain.tc), ("EC", chain.ec)]:
            cert_status[name] = cert.status.value if cert else "not_attempted"

    next_state = ""
    if "execution" in serialized:
        # Derive from state machine
        from engine.state_machine import next_state_for_action
        next_state = next_state_for_action(req.current_state, verdict)

    audit_log = [
        AuditEntry(stage=r["stage"], detail={"action": r["action"], "notes": r["notes"]})
        for r in serialized.get("audit_trail", [])
    ]

    return PipelineResponse(
        decision_id=result.decision_id,
        success=result.success,
        validation_errors=result.validation_errors,
        recommended_action=verdict,
        reason_code=reason,
        value_classification=result.value_classification,
        net_value_score=result.net_value_score,
        trust_tier=result.trust_tier.value,
        trust_total=result.trust_total,
        alignment_composite=round(result.alignment_composite, 3),
        alignment_violations=result.alignment_violations,
        priority_score=result.priority_score,
        next_state=next_state,
        certificate_status=cert_status,
        executive_summary=result.executive_summary,
        audit_log=audit_log,
        full_result=serialized,
    )


# ── State Transitions ──


@router.post("/v1/decisions/transition", response_model=TransitionResponse)
def transition_decision(payload: TransitionRequest):
    """Check if a state transition is valid and return required certificates."""
    config = _get_config()
    allowed = sm_can_transition(payload.current_state, payload.target_state, config)
    certs = STATE_CERTIFICATE_MAP.get(payload.target_state, [])
    return TransitionResponse(
        allowed=allowed,
        current_state=payload.current_state,
        target_state=payload.target_state,
        required_certificates=certs,
    )


@router.get("/v1/decisions/lifecycle/{state}")
def lifecycle_status(state: str):
    """Get lifecycle position for a decision state."""
    return get_lifecycle_status(state)


# ── Learning Loop ──


@router.post("/v1/outcomes/record")
def record_outcome_endpoint(req: OutcomeRequest):
    """Record a post-execution outcome for the learning loop."""
    record = ll_record_outcome(
        decision_id=req.decision_id,
        decision_class=req.decision_class,
        original_verdict=req.original_verdict,
        expected_value=req.expected_value,
        expected_timeline_days=req.expected_timeline_days,
        expected_risk_level=req.expected_risk_level,
        actual_value=req.actual_value,
        actual_timeline_days=req.actual_timeline_days,
        actual_risk_materialized=req.actual_risk_materialized,
        actual_risk_description=req.actual_risk_description,
        outcome_summary=req.outcome_summary,
        lessons_learned=req.lessons_learned,
        recorded_by=req.recorded_by,
    )
    return {
        "record_id": record.record_id,
        "decision_id": record.decision_id,
        "trust_recommendation": record.variance.trust_recommendation.value,
        "composite_variance": record.variance.composite_variance_score,
        "suggested_actions": record.variance.suggested_actions,
    }


@router.get("/v1/learning/summary")
def learning_summary():
    """Get institutional learning summary."""
    store = LearningStore()
    return {
        "summary": store.generate_learning_summary(),
        "stats": store.compute_class_stats(),
    }


@router.get("/v1/learning/unapplied")
def unapplied_learnings():
    """Get learning records that haven't been applied yet."""
    store = LearningStore()
    records = store.get_unapplied()
    return {
        "count": len(records),
        "records": [
            {
                "decision_id": r.decision_id,
                "decision_class": r.decision_class,
                "trust_recommendation": r.variance.trust_recommendation.value,
                "suggested_actions": r.variance.suggested_actions,
                "suggested_update_targets": r.variance.suggested_update_targets,
            }
            for r in records
        ],
    }
