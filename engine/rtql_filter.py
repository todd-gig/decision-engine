"""
RTQL Pre-Filter — Recursive Trust Qualification Loop

Classifies raw decision inputs through the 7-checkpoint trust discipline
before they enter the decision processing pipeline.

Stage progression:
    noise → weak_signal → echo_signal → qualified →
    certification_gap → certified → research_grade →
    first_principles_candidate → axiom_candidate

Trust multipliers applied to value scoring:
    noise: 0.00-0.25, weak_signal: 0.25-0.50, qualified: 1.00,
    certified: 1.25, research_grade: 1.50, first_principles_candidate: 2.00
"""

from .models import (
    RTQLInput, RTQLScores, CausalChecks, RTQLResult,
    RTQLStage, WriteTarget
)


# ─────────────────────────────────────────────
# TRUST MULTIPLIER MAP
# ─────────────────────────────────────────────

TRUST_MULTIPLIERS = {
    RTQLStage.NOISE: 0.00,
    RTQLStage.WEAK_SIGNAL: 0.35,
    RTQLStage.ECHO_SIGNAL: 0.50,
    RTQLStage.QUALIFIED: 1.00,
    RTQLStage.CERTIFICATION_GAP: 0.85,
    RTQLStage.CERTIFIED: 1.15,
    RTQLStage.RESEARCH_GRADE: 1.30,
    RTQLStage.FIRST_PRINCIPLES_CANDIDATE: 1.50,
    RTQLStage.AXIOM_CANDIDATE: 1.50,
}

WRITE_TARGET_MAP = {
    RTQLStage.NOISE: WriteTarget.QUARANTINE,
    RTQLStage.WEAK_SIGNAL: WriteTarget.STAGING,
    RTQLStage.ECHO_SIGNAL: WriteTarget.STAGING,
    RTQLStage.QUALIFIED: WriteTarget.CANDIDATE_REGISTRY,
    RTQLStage.CERTIFICATION_GAP: WriteTarget.CANDIDATE_REGISTRY,
    RTQLStage.CERTIFIED: WriteTarget.OPERATIONAL_REGISTRY,
    RTQLStage.RESEARCH_GRADE: WriteTarget.INSIGHT_REGISTRY,
    RTQLStage.FIRST_PRINCIPLES_CANDIDATE: WriteTarget.PRINCIPLES_REGISTRY,
    RTQLStage.AXIOM_CANDIDATE: WriteTarget.AXIOM_REVIEW_QUEUE,
}


# ─────────────────────────────────────────────
# RESEARCH ACTION GENERATORS
# ─────────────────────────────────────────────

def _research_actions_for_failure(stage: RTQLStage, scores: RTQLScores,
                                   causal: CausalChecks) -> list[str]:
    """Generate minimum viable research actions for blocked inputs."""
    actions = []

    if scores.source_integrity < 4:
        actions.append("Locate or establish auditable source trail for this input")
    if scores.exposure_count < 3:
        actions.append("Monitor for repeat appearances across independent contexts")
    if scores.independence < 4:
        actions.append("Seek cross-domain or independent confirmation")
    if scores.explainability < 6:
        actions.append("Decompose claim into causal variables and mechanism")
    if scores.replicability < 6:
        actions.append("Define and execute a replication protocol")
    if scores.adversarial_robustness < 6:
        actions.append("Design adversarial/red-team test for this claim")
    if scores.novelty_yield < 6 and stage in (
        RTQLStage.CERTIFIED, RTQLStage.RESEARCH_GRADE
    ):
        actions.append("Assess whether input produces materially new information")

    if stage == RTQLStage.RESEARCH_GRADE:
        if not causal.reveals_causal_mechanism:
            actions.append("Identify underlying causal mechanism")
        if not causal.is_irreducible:
            actions.append("Test irreducibility — can this be decomposed further?")
        if not causal.survives_authority_removal:
            actions.append("Verify claim holds without authority backing")
        if not causal.survives_context_shift:
            actions.append("Test claim across different operational contexts")

    return actions


# ─────────────────────────────────────────────
# CORE CLASSIFICATION ENGINE
# ─────────────────────────────────────────────

def classify_rtql(inp: RTQLInput) -> RTQLResult:
    """
    Run the full RTQL classification pipeline.

    Implements the canonical decision tree from RTQL spec:
    identifiable? → source_integrity → exposure → independence →
    explainability → replicability → robustness → novelty →
    causal mechanism → irreducible → authority removal → context shift
    """
    result = RTQLResult()
    scores = inp.scores
    causal = inp.causal_checks
    blocking = []

    # ── Gate 0: Identity & Provenance ──
    if not inp.is_identifiable or not inp.has_provenance:
        result.stage = RTQLStage.NOISE
        blocking.append("Input is not identifiable or lacks provenance")
        result.blocking_reasons = blocking
        result.trust_multiplier = TRUST_MULTIPLIERS[result.stage]
        result.write_target = WRITE_TARGET_MAP[result.stage]
        result.research_actions = [
            "Establish identifiable source and provenance trail"
        ]
        return result

    # ── Gate 1: Source Integrity (>= 4) ──
    if scores.source_integrity < 4:
        result.stage = RTQLStage.WEAK_SIGNAL
        blocking.append(
            f"Source integrity {scores.source_integrity} < 4 threshold"
        )

    # ── Gate 2: Exposure Count (>= 3) ──
    if scores.exposure_count < 3:
        if result.stage == RTQLStage.NOISE:
            result.stage = RTQLStage.WEAK_SIGNAL
        elif result.stage != RTQLStage.WEAK_SIGNAL:
            result.stage = RTQLStage.WEAK_SIGNAL
        blocking.append(
            f"Exposure count {scores.exposure_count} < 3 threshold"
        )

    # ── Gate 3: Independence (>= 4) ──
    if scores.independence < 4:
        if not blocking:
            result.stage = RTQLStage.ECHO_SIGNAL
            blocking.append(
                f"Independence {scores.independence} < 4 threshold"
            )
        else:
            blocking.append(
                f"Independence {scores.independence} < 4 threshold"
            )

    # If any qualification gate failed, stop here
    if blocking:
        result.blocking_reasons = blocking
        result.trust_multiplier = TRUST_MULTIPLIERS[result.stage]
        result.write_target = WRITE_TARGET_MAP[result.stage]
        result.research_actions = _research_actions_for_failure(
            result.stage, scores, causal
        )
        return result

    # ── Qualification passed — now test certification gates ──

    cert_gaps = []

    # ── Gate 4: Explainability (>= 6) ──
    if scores.explainability < 6:
        cert_gaps.append(
            f"Explainability {scores.explainability} < 6 threshold"
        )

    # ── Gate 5: Replicability (>= 6) ──
    if scores.replicability < 6:
        cert_gaps.append(
            f"Replicability {scores.replicability} < 6 threshold"
        )

    # ── Gate 6: Adversarial Robustness (>= 6) ──
    if scores.adversarial_robustness < 6:
        cert_gaps.append(
            f"Adversarial robustness {scores.adversarial_robustness} < 6 threshold"
        )

    if cert_gaps:
        result.stage = RTQLStage.CERTIFICATION_GAP
        result.blocking_reasons = cert_gaps
        result.trust_multiplier = TRUST_MULTIPLIERS[result.stage]
        result.write_target = WRITE_TARGET_MAP[result.stage]
        result.research_actions = _research_actions_for_failure(
            result.stage, scores, causal
        )
        result.passed = True  # qualified but not yet certified
        return result

    # ── Certification passed — test for research-grade ──

    if scores.novelty_yield < 6:
        # Certified but not novel enough for research-grade
        result.stage = RTQLStage.CERTIFIED
        result.passed = True
        result.trust_multiplier = TRUST_MULTIPLIERS[result.stage]
        result.write_target = WRITE_TARGET_MAP[result.stage]
        return result

    # ── Research-grade passed — test for first principles ──

    fp_gaps = []
    if not causal.reveals_causal_mechanism:
        fp_gaps.append("Does not reveal causal mechanism")
    if not causal.is_irreducible:
        fp_gaps.append("Not irreducible — can be decomposed further")
    if not causal.survives_authority_removal:
        fp_gaps.append("Does not survive authority removal")
    if not causal.survives_context_shift:
        fp_gaps.append("Does not survive context shift")

    if fp_gaps:
        result.stage = RTQLStage.RESEARCH_GRADE
        result.passed = True
        result.blocking_reasons = fp_gaps
        result.trust_multiplier = TRUST_MULTIPLIERS[result.stage]
        result.write_target = WRITE_TARGET_MAP[result.stage]
        result.research_actions = _research_actions_for_failure(
            result.stage, scores, causal
        )
        return result

    # ── All gates passed — first principles candidate ──
    result.stage = RTQLStage.FIRST_PRINCIPLES_CANDIDATE
    result.passed = True
    result.trust_multiplier = TRUST_MULTIPLIERS[result.stage]
    result.write_target = WRITE_TARGET_MAP[result.stage]
    return result


def rtql_prefilter_passes(result: RTQLResult) -> bool:
    """
    Determine if an RTQL result allows the decision to proceed
    through the main pipeline.

    Noise and weak signals are blocked from influencing decisions.
    Echo signals proceed with a warning.
    Everything qualified and above proceeds.
    """
    return result.stage not in (RTQLStage.NOISE, RTQLStage.WEAK_SIGNAL)
