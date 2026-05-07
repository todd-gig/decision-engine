"""
7-Gate Autonomous Execution Authorization System

Gate sequence:
    1. Doctrine Check — no non-negotiable violations
    2. Trust Tier Check — tier meets decision class minimum
    3. Value Threshold Check — net value meets class minimum
    4. Reversibility Check — reversibility tag compatible with auto-execution
    5. Risk Containment Check — downside bounded, rollback exists
    6. Approval Routing — required approvals present or not needed
    7. Monitoring Configuration — monitoring hooks and review date exist

If all 7 gates pass → AUTO_EXECUTE
If gates 1-5 pass but 6-7 fail → ESCALATE with tier routing
If any gate 1-5 fails → BLOCK or ESCALATE based on severity

3-Tier Escalation:
    Tier 1 (4hr SLA): owner + stakeholder
    Tier 2 (1-day SLA): functional leader + exec
    Tier 3 (3-day SLA): C-level + board
"""

from .models import (
    DecisionObject, DecisionClass, ReversibilityTag, TrustTier,
    ExecutionVerdict, ExecutionPacket, AlignmentScores,
    CertificateChain, CertificateType
)


# ─────────────────────────────────────────────
# TRUST TIER MINIMUMS PER DECISION CLASS
# ─────────────────────────────────────────────

# From execution protocol: D1 auto at T3+, D2 approved recurrence at T3+
# D3-D6 require human approval regardless
TRUST_TIER_MINIMUMS = {
    DecisionClass.D0_INFORMATIONAL: TrustTier.T0_UNQUALIFIED,
    DecisionClass.D1_REVERSIBLE_TACTICAL: TrustTier.T3_CERTIFIED,
    DecisionClass.D2_OPERATIONAL: TrustTier.T2_QUALIFIED,
    DecisionClass.D3_FINANCIAL: TrustTier.T3_CERTIFIED,
    DecisionClass.D4_STRATEGIC: TrustTier.T3_CERTIFIED,
    DecisionClass.D5_LEGAL_ETHICAL: TrustTier.T4_DELEGATED,
    DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST: TrustTier.T4_DELEGATED,
}

# Value thresholds per decision class
VALUE_THRESHOLDS = {
    DecisionClass.D0_INFORMATIONAL: 0,
    DecisionClass.D1_REVERSIBLE_TACTICAL: 8,
    DecisionClass.D2_OPERATIONAL: 12,
    DecisionClass.D3_FINANCIAL: 16,
    DecisionClass.D4_STRATEGIC: 20,
    DecisionClass.D5_LEGAL_ETHICAL: 20,
    DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST: 24,
}

# Reversibility auto-execution limits
# From execution protocol: auto-execute only R1/R2
AUTO_EXECUTE_REVERSIBILITY = {
    ReversibilityTag.R1_EASILY_REVERSIBLE,
    ReversibilityTag.R2_MODERATELY_REVERSIBLE,
}

# Decision classes that ALWAYS require human approval
MANDATORY_HUMAN_CLASSES = {
    DecisionClass.D5_LEGAL_ETHICAL,
    DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST,
}

# Decision classes eligible for autonomous execution
AUTO_ELIGIBLE_CLASSES = {
    DecisionClass.D0_INFORMATIONAL,
    DecisionClass.D1_REVERSIBLE_TACTICAL,
}

# D2 eligible only with approved recurrence pattern
D2_AUTO_ELIGIBLE = DecisionClass.D2_OPERATIONAL

# Trust tier ordering for comparison
TIER_ORDER = {
    TrustTier.T0_UNQUALIFIED: 0,
    TrustTier.T1_OBSERVED: 1,
    TrustTier.T2_QUALIFIED: 2,
    TrustTier.T3_CERTIFIED: 3,
    TrustTier.T4_DELEGATED: 4,
}


def _tier_gte(actual: TrustTier, minimum: TrustTier) -> bool:
    return TIER_ORDER[actual] >= TIER_ORDER[minimum]


# ─────────────────────────────────────────────
# INDIVIDUAL GATE FUNCTIONS
# ─────────────────────────────────────────────

def gate_1_doctrine(decision: DecisionObject,
                     alignment: AlignmentScores) -> tuple[bool, str]:
    """Gate 1: No non-negotiable doctrine violations."""
    if alignment.doctrine_alignment < 0.3:
        return False, f"Doctrine alignment {alignment.doctrine_alignment} below 0.3 minimum"

    # Check for critical anti-patterns
    critical_patterns = {
        "optics_over_substance",
        "automation_without_human_override",
        "ethical_misalignment_above_threshold",
    }
    violations = critical_patterns.intersection(set(alignment.anti_pattern_flags))
    if violations:
        return False, f"Critical anti-pattern violations: {', '.join(violations)}"

    if decision.value_scores.ethical_misalignment > 3:
        return False, f"Ethical misalignment score {decision.value_scores.ethical_misalignment} exceeds threshold 3"

    return True, "Doctrine check passed"


def gate_2_trust_tier(decision: DecisionObject,
                       trust_tier: TrustTier) -> tuple[bool, str]:
    """Gate 2: Trust tier meets decision class minimum."""
    minimum = TRUST_TIER_MINIMUMS[decision.decision_class]
    if _tier_gte(trust_tier, minimum):
        return True, f"Trust tier {trust_tier.value} meets minimum {minimum.value} for {decision.decision_class.value}"
    return False, f"Trust tier {trust_tier.value} below minimum {minimum.value} for {decision.decision_class.value}"


def gate_3_value_threshold(decision: DecisionObject,
                            net_value: int) -> tuple[bool, str]:
    """Gate 3: Net value score meets decision class threshold."""
    threshold = VALUE_THRESHOLDS[decision.decision_class]
    if net_value >= threshold:
        return True, f"Net value {net_value} meets threshold {threshold} for {decision.decision_class.value}"
    return False, f"Net value {net_value} below threshold {threshold} for {decision.decision_class.value}"


def gate_4_reversibility(decision: DecisionObject) -> tuple[bool, str]:
    """Gate 4: Reversibility tag compatible with autonomous execution."""
    if decision.decision_class in MANDATORY_HUMAN_CLASSES:
        return False, f"Decision class {decision.decision_class.value} requires mandatory human approval regardless of reversibility"

    if decision.reversibility in AUTO_EXECUTE_REVERSIBILITY:
        return True, f"Reversibility {decision.reversibility.value} is within auto-execute bounds"

    return False, f"Reversibility {decision.reversibility.value} too high for autonomous execution"


def gate_5_risk_containment(decision: DecisionObject) -> tuple[bool, str]:
    """Gate 5: Downside bounded and rollback mechanism exists."""
    issues = []

    if decision.value_scores.downside_risk > 3:
        issues.append(f"Downside risk {decision.value_scores.downside_risk} exceeds containment threshold 3")

    if decision.value_scores.uncertainty > 3:
        issues.append(f"Uncertainty {decision.value_scores.uncertainty} exceeds containment threshold 3")

    if decision.reversibility.value in ("R3", "R4") and not decision.rollback_trigger:
        issues.append("No rollback trigger defined for high-irreversibility decision")

    if not decision.monitoring_metric:
        issues.append("No monitoring metric defined")

    if issues:
        return False, "; ".join(issues)

    return True, "Risk containment adequate — downside bounded, monitoring in place"


def gate_6_approval_routing(decision: DecisionObject,
                             trust_tier: TrustTier) -> tuple[bool, str]:
    """Gate 6: Required approvals present or decision class doesn't require them."""
    dc = decision.decision_class

    # D0 and D1 with sufficient trust need no approvals
    if dc in AUTO_ELIGIBLE_CLASSES:
        if dc == DecisionClass.D0_INFORMATIONAL:
            return True, "D0 informational — no approval required"
        if _tier_gte(trust_tier, TrustTier.T3_CERTIFIED):
            return True, f"D1 with trust {trust_tier.value} — auto-approved"

    # D2 requires owner approval unless T3+ with approved recurrence
    if dc == D2_AUTO_ELIGIBLE:
        if _tier_gte(trust_tier, TrustTier.T3_CERTIFIED):
            # Check if owner is in approvals (indicates approved recurrence)
            if decision.owner in decision.required_approvals:
                return True, "D2 with T3+ trust and owner approval — auto-approved"
            elif not decision.required_approvals:
                return False, "D2 requires at least owner approval"
        return False, f"D2 with trust {trust_tier.value} requires human approval"

    # D3-D6 always require human approval
    if dc in MANDATORY_HUMAN_CLASSES:
        if decision.required_approvals:
            return True, f"Required approvals listed: {', '.join(decision.required_approvals)}"
        return False, f"{dc.value} requires mandatory human approval — none listed"

    # D3, D4 — executive approval required
    if decision.required_approvals:
        return True, f"Approvals present for {dc.value}: {', '.join(decision.required_approvals)}"
    return False, f"{dc.value} requires human executive approval — none listed"


def gate_7_monitoring(decision: DecisionObject) -> tuple[bool, str]:
    """Gate 7: Monitoring hooks and review date exist."""
    issues = []

    if not decision.monitoring_metric:
        issues.append("No monitoring metric defined")

    if not decision.review_date:
        issues.append("No review date set")

    if not decision.rollback_trigger and decision.decision_class.value not in ("D0",):
        issues.append("No rollback trigger defined")

    if issues:
        return False, "; ".join(issues)

    return True, "Monitoring configuration complete"


# ─────────────────────────────────────────────
# ESCALATION TIER ROUTING
# ─────────────────────────────────────────────

def determine_escalation_tier(decision: DecisionObject,
                               failed_gates: list[str]) -> tuple[int, str, list[str]]:
    """
    Determine escalation tier based on decision class and failure severity.

    Returns (tier, sla, recipients_roles).

    Tier 1: 4hr SLA — owner + stakeholder
    Tier 2: 1-day SLA — functional leader + exec
    Tier 3: 3-day SLA — C-level + board
    """
    dc = decision.decision_class

    # Tier 3: irreversible/high-blast or legal/ethical
    if dc in (DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST, DecisionClass.D5_LEGAL_ETHICAL):
        return 3, "3 business days", ["c_level", "board"]

    # Tier 2: strategic or financial
    if dc in (DecisionClass.D4_STRATEGIC, DecisionClass.D3_FINANCIAL):
        return 2, "1 business day", ["functional_leader", "executive"]

    # Tier 2 if doctrine or trust gates failed (serious structural issues)
    if any(g in failed_gates for g in ["gate_1_doctrine", "gate_2_trust_tier"]):
        return 2, "1 business day", ["functional_leader", "executive"]

    # Tier 1: operational or tactical
    return 1, "4 hours", ["owner", "stakeholder"]


# ─────────────────────────────────────────────
# 7-GATE AUTHORIZATION ORCHESTRATOR
# ─────────────────────────────────────────────

def run_7_gate_authorization(
    decision: DecisionObject,
    trust_tier: TrustTier,
    net_value: int,
    alignment: AlignmentScores,
    certificate_chain: CertificateChain,
) -> ExecutionPacket:
    """
    Run all 7 gates sequentially.
    Returns an ExecutionPacket with verdict, gate results, and escalation routing.
    """
    packet = ExecutionPacket(
        decision_id=decision.decision_id,
        owner=decision.owner,
        action_steps=[decision.requested_action],
        monitoring_metric=decision.monitoring_metric,
        rollback_trigger=decision.rollback_trigger,
        review_date=decision.review_date or "",
    )

    gate_results = {}
    failed_gates = []
    blocking_gates = []

    # Run each gate
    gates = [
        ("gate_1_doctrine", lambda: gate_1_doctrine(decision, alignment)),
        ("gate_2_trust_tier", lambda: gate_2_trust_tier(decision, trust_tier)),
        ("gate_3_value_threshold", lambda: gate_3_value_threshold(decision, net_value)),
        ("gate_4_reversibility", lambda: gate_4_reversibility(decision)),
        ("gate_5_risk_containment", lambda: gate_5_risk_containment(decision)),
        ("gate_6_approval_routing", lambda: gate_6_approval_routing(decision, trust_tier)),
        ("gate_7_monitoring", lambda: gate_7_monitoring(decision)),
    ]

    for gate_name, gate_fn in gates:
        passed, reason = gate_fn()
        gate_results[gate_name] = {"passed": passed, "reason": reason}
        if not passed:
            failed_gates.append(gate_name)
            blocking_gates.append(f"{gate_name}: {reason}")

    packet.gate_results = gate_results
    packet.blocking_gates = blocking_gates

    # ── Determine verdict ──

    # D0 informational — always information only
    if decision.decision_class == DecisionClass.D0_INFORMATIONAL:
        packet.verdict = ExecutionVerdict.INFORMATION_ONLY
        return packet

    # Gates 1-3 are structural — any failure = BLOCK
    structural_failures = [g for g in failed_gates if g in (
        "gate_1_doctrine", "gate_2_trust_tier", "gate_3_value_threshold"
    )]
    if structural_failures:
        packet.verdict = ExecutionVerdict.BLOCK
        return packet

    # Certificate chain must be complete for execution
    if not certificate_chain.chain_complete():
        highest = certificate_chain.highest_valid()
        if highest is None:
            packet.verdict = ExecutionVerdict.BLOCK
            packet.blocking_gates.append("No valid certificates in chain")
        else:
            # Partial chain — escalate
            tier, sla, recipients = determine_escalation_tier(decision, failed_gates)
            packet.verdict = ExecutionVerdict(f"escalate_tier_{tier}")
            packet.escalation_tier = tier
            packet.escalation_sla = sla
            packet.escalation_recipients = recipients
            packet.blocking_gates.append(
                f"Certificate chain incomplete — highest valid: {highest.value}"
            )
        return packet

    # All gates pass → auto-execute (if class allows)
    if not failed_gates:
        # Final check: is this class eligible for autonomous execution?
        if decision.decision_class in AUTO_ELIGIBLE_CLASSES:
            packet.verdict = ExecutionVerdict.AUTO_EXECUTE
        elif (decision.decision_class == D2_AUTO_ELIGIBLE and
              _tier_gte(trust_tier, TrustTier.T3_CERTIFIED)):
            packet.verdict = ExecutionVerdict.AUTO_EXECUTE
        else:
            # Gates passed but class requires human — escalate for approval
            tier, sla, recipients = determine_escalation_tier(decision, [])
            packet.verdict = ExecutionVerdict(f"escalate_tier_{tier}")
            packet.escalation_tier = tier
            packet.escalation_sla = sla
            packet.escalation_recipients = recipients
        return packet

    # Gates 4-7 failed → ESCALATE (structural gates already checked above)
    tier, sla, recipients = determine_escalation_tier(decision, failed_gates)
    packet.verdict = ExecutionVerdict(f"escalate_tier_{tier}")
    packet.escalation_tier = tier
    packet.escalation_sla = sla
    packet.escalation_recipients = recipients
    return packet
