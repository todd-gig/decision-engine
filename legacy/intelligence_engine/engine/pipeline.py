"""
Decision Processing Pipeline — Core Orchestrator

The central nervous system of the Executive Decision Engine.
Chains all subsystems in the canonical processing sequence:

    Input Validation
    → Missing Data / Ethical Conflict Pre-Check
    → RTQL Pre-Filter
    → Value Assessment (raw + weighted)
    → Trust Assessment
    → Authority Check
    → Alignment Check
    → Certificate Chain (QC → VC → TC → EC)
    → 7-Gate Authorization
    → State Machine Transition
    → Priority Scoring
    → Execution Routing
    → Audit Trail Assembly

Single entry point: process_decision(DecisionObject, config?) → PipelineResult
"""

from typing import Optional

from .models import (
    DecisionObject, PipelineResult, RTQLInput, RTQLResult,
    TrustTier, CertificateChain, ExecutionPacket, ExecutionVerdict,
    RTQLStage
)
from .config import EngineConfig, load_config
from .rtql_filter import classify_rtql, rtql_prefilter_passes
from .scoring import (
    calculate_trust_tier, trust_adjusted_value,
    check_alignment, calculate_priority_score
)
from .weighted_scoring import compute_weighted_value, compute_weighted_trust
from .authority import authority_check
from .state_machine import next_state_for_action, advance_state
from .certificates import build_certificate_chain
from .gates import run_7_gate_authorization
from .audit import (
    AuditLogger, generate_executive_summary, serialize_pipeline_result
)


def process_decision(
    decision: DecisionObject,
    config: Optional[EngineConfig] = None,
) -> PipelineResult:
    """
    Run the full decision processing pipeline.

    Takes a human-populated DecisionObject with all scored dimensions
    and produces a PipelineResult containing:
    - validation status
    - RTQL classification
    - value and trust assessments (raw + weighted)
    - authority check result
    - alignment check
    - certificate chain
    - 7-gate authorization verdict
    - state machine transition
    - priority score
    - executive summary
    - full audit trail
    """
    if config is None:
        config = load_config()

    result = PipelineResult(decision_id=decision.decision_id)
    logger = AuditLogger(decision.decision_id)

    # ──────────────────────────────────────────
    # STAGE 1: INPUT VALIDATION
    # ──────────────────────────────────────────
    validation_errors = decision.validate()
    logger.log_validation(validation_errors)

    if validation_errors:
        result.validation_errors = validation_errors
        result.success = False
        result.audit_trail = logger.records
        result.executive_summary = generate_executive_summary(result)
        return result

    # ──────────────────────────────────────────
    # STAGE 1.5: MISSING DATA / ETHICAL PRE-CHECK
    # ──────────────────────────────────────────
    if decision.has_missing_data:
        logger.log(
            stage="pre_check",
            action="missing_data_detected",
            notes="Decision flagged as having missing data — will route to needs_data"
        )

    if decision.ethical_conflict:
        logger.log(
            stage="pre_check",
            action="ethical_conflict_detected",
            notes="Decision flagged with ethical conflict — will block"
        )

    # ──────────────────────────────────────────
    # STAGE 2: RTQL PRE-FILTER
    # ──────────────────────────────────────────
    rtql_result = RTQLResult()
    if decision.rtql_input:
        rtql_result = classify_rtql(decision.rtql_input)
        logger.log_rtql(rtql_result)
        result.rtql_result = rtql_result

        if not rtql_prefilter_passes(rtql_result):
            logger.log(
                stage="rtql_prefilter",
                action="rtql_block_warning",
                notes=f"RTQL stage {rtql_result.stage.value} — "
                      f"input has low trust, proceeding with degraded multiplier"
            )
    else:
        rtql_result.stage = RTQLStage.QUALIFIED
        rtql_result.trust_multiplier = 1.0
        rtql_result.passed = True
        result.rtql_result = rtql_result
        logger.log(
            stage="rtql_prefilter",
            action="rtql_bypass",
            notes="No RTQL input provided — defaulting to qualified with multiplier 1.0"
        )

    # ──────────────────────────────────────────
    # STAGE 3: VALUE ASSESSMENT (raw + weighted)
    # ──────────────────────────────────────────
    vs = decision.value_scores
    gross = vs.gross_value()
    penalty = vs.penalty()
    net = vs.net_value()
    classification = vs.value_classification()

    # Weighted value from config
    weighted_result = compute_weighted_value(vs, config)

    # RTQL trust-adjusted net
    adjusted_net = trust_adjusted_value(vs, rtql_result.trust_multiplier)

    logger.log_value_assessment(gross, penalty, net, classification)
    logger.log(
        stage="value_assessment",
        action="compute_weighted_value",
        outputs=weighted_result,
        notes=f"Weighted net: {weighted_result['weighted_net']}"
    )

    result.net_value_score = net
    result.value_classification = classification

    # ──────────────────────────────────────────
    # STAGE 4: TRUST ASSESSMENT
    # ──────────────────────────────────────────
    trust_tier, demotion_reasons = calculate_trust_tier(decision.trust_scores)
    trust_total = decision.trust_scores.total()

    # Weighted trust from config
    weighted_trust = compute_weighted_trust(
        decision.trust_scores, trust_tier, config
    )

    logger.log_trust_assessment(trust_tier, trust_total, demotion_reasons)
    logger.log(
        stage="trust_assessment",
        action="compute_weighted_trust",
        outputs=weighted_trust,
        notes=f"Adjusted trust score: {weighted_trust['adjusted_trust_score']}"
    )

    result.trust_tier = trust_tier
    result.trust_total = trust_total

    # ──────────────────────────────────────────
    # STAGE 4.5: AUTHORITY CHECK
    # ──────────────────────────────────────────
    auth_result = authority_check(
        decision_class=decision.decision_class,
        actor_role=decision.actor_role,
        trust_tier=trust_tier,
        config=config,
    )
    logger.log(
        stage="authority_check",
        action="authority_check",
        outputs=auth_result,
        notes=auth_result["reason"]
    )

    # ──────────────────────────────────────────
    # STAGE 5: ALIGNMENT CHECK
    # ──────────────────────────────────────────
    alignment = check_alignment(decision)
    logger.log_alignment(alignment)

    result.alignment_composite = alignment.composite()
    result.alignment_violations = alignment.anti_pattern_flags

    # ──────────────────────────────────────────
    # STAGE 6: CERTIFICATE CHAIN (QC → VC → TC → EC)
    # ──────────────────────────────────────────
    from .certificates import issue_qc, issue_vc, issue_tc, issue_ec

    chain = CertificateChain()
    chain.qc = issue_qc(decision)
    if chain.qc.is_valid():
        chain.vc = issue_vc(decision, chain.qc)
    if chain.vc and chain.vc.is_valid():
        chain.tc = issue_tc(decision, trust_tier, chain.vc)

    # ──────────────────────────────────────────
    # STAGE 7: 7-GATE AUTHORIZATION
    # ──────────────────────────────────────────
    exec_packet = run_7_gate_authorization(
        decision=decision,
        trust_tier=trust_tier,
        net_value=net,
        alignment=alignment,
        certificate_chain=chain,
    )

    # Issue EC based on gate results
    if chain.tc and chain.tc.is_valid():
        chain.ec = issue_ec(decision, trust_tier, chain.tc, exec_packet.gate_results)

    logger.log_certificate_chain(chain)
    result.certificate_chain = chain

    # Re-run authorization with complete chain for final verdict
    exec_packet = run_7_gate_authorization(
        decision=decision,
        trust_tier=trust_tier,
        net_value=net,
        alignment=alignment,
        certificate_chain=chain,
    )

    # ── Override verdict for missing data / ethical conflict ──
    if decision.ethical_conflict:
        exec_packet.verdict = ExecutionVerdict.BLOCK
        exec_packet.blocking_gates.append("Ethical conflict flag is set — mandatory block")

    if decision.has_missing_data and exec_packet.verdict not in (
        ExecutionVerdict.BLOCK,
    ):
        exec_packet.verdict = ExecutionVerdict.NEEDS_DATA
        exec_packet.blocking_gates.append(
            "Missing data flag is set — cannot execute until data gaps resolved"
        )

    # ── Override if authority insufficient ──
    if not auth_result["can_execute"] and exec_packet.verdict == ExecutionVerdict.AUTO_EXECUTE:
        exec_packet.verdict = ExecutionVerdict.ESCALATE_TIER_1
        exec_packet.blocking_gates.append(
            f"Authority insufficient: {auth_result['reason']}"
        )

    logger.log_execution(exec_packet)
    result.execution_packet = exec_packet

    # ──────────────────────────────────────────
    # STAGE 8: STATE MACHINE TRANSITION
    # ──────────────────────────────────────────
    target_state = next_state_for_action(
        decision.current_state, exec_packet.verdict.value
    )
    state_result = advance_state(
        decision.current_state, target_state, config
    )
    logger.log(
        stage="state_machine",
        action="advance_state",
        outputs=state_result,
        notes=f"{decision.current_state} → {state_result['current_state']}"
    )

    # ──────────────────────────────────────────
    # STAGE 9: PRIORITY SCORING
    # ──────────────────────────────────────────
    priority = calculate_priority_score(
        value_scores=vs,
        trust_tier=trust_tier,
        alignment=alignment,
        rtql_multiplier=rtql_result.trust_multiplier,
        probability_of_success=0.7,
    )

    logger.log_priority_score(priority)
    result.priority_score = priority

    # ──────────────────────────────────────────
    # FINALIZE
    # ──────────────────────────────────────────
    result.success = True
    result.audit_trail = logger.records
    result.executive_summary = generate_executive_summary(result)

    return result
