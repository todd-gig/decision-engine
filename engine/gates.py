"""
8-Gate Autonomous Execution Authorization System

Gate sequence:
    1. Doctrine Check — no non-negotiable violations
    2. Trust Tier Check — tier meets decision class minimum
    3. Value Threshold Check — net value meets class minimum
    4. Reversibility Check — reversibility tag compatible with auto-execution
    5. Risk Containment Check — downside bounded, rollback exists
    6. Approval Routing — required approvals present or not needed
    7. Monitoring Configuration — monitoring hooks and review date exist
    8. Drift Sentinel Check — no open critical drift findings touch this
                              decision's domain (closes the recursive
                              self-governance loop with drift_sentinel)

If all 8 gates pass → AUTO_EXECUTE
If gates 1-3 or 8 fail → BLOCK (structural)
If gates 4-7 fail → ESCALATE with tier routing

3-Tier Escalation:
    Tier 1 (4hr SLA): owner + stakeholder
    Tier 2 (1-day SLA): functional leader + exec
    Tier 3 (3-day SLA): C-level + board
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import (
    DecisionObject, DecisionClass, ReversibilityTag, TrustTier,
    ExecutionVerdict, ExecutionPacket, AlignmentScores,
    CertificateChain
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
# GATE 8: DRIFT SENTINEL CHECK (recursive self-governance)
# ─────────────────────────────────────────────

def _default_drift_db_path() -> Optional[Path]:
    """Locate drift_history.db relative to this engine's repo."""
    here = Path(__file__).resolve().parent.parent  # decision-engine/
    candidate = here / "drift_sentinel" / "drift_history.db"
    return candidate if candidate.exists() else None


_DOMAIN_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into",
    "ensure", "verify", "fix", "add", "update", "remove", "implement",
    "decision", "action", "trigger", "review", "approval", "owner",
    "context", "stakeholders", "constraints", "evidence", "assumptions",
    "monitoring", "rollback", "execution", "approve", "should", "must",
}


def _extract_domain_tokens(decision: DecisionObject) -> set[str]:
    """Extract repo / file / module tokens from decision payload."""
    tokens: set[str] = set()
    # evidence_refs are the strongest signal — paths or file:line
    for ref in decision.evidence_refs:
        for chunk in re.split(r"[/\s:#]", ref):
            chunk = chunk.strip(".:#").lower()
            if len(chunk) > 2 and chunk not in _DOMAIN_STOPWORDS:
                tokens.add(chunk)
    # Action / title / problem text — broader but useful for repo/module names
    for text in (decision.requested_action, decision.title,
                 decision.problem_statement):
        for word in re.findall(r"[\w][\w./-]*", text or ""):
            w = word.lower().strip(".-/")
            if "/" in w or "." in w or "-" in w or len(w) > 4:
                if w not in _DOMAIN_STOPWORDS:
                    tokens.add(w)
    # Stakeholders sometimes name domains/teams
    for s in decision.stakeholders:
        sl = s.lower().strip()
        if sl and sl not in _DOMAIN_STOPWORDS:
            tokens.add(sl)
    return tokens


def _acknowledged_rule_ids(decision: DecisionObject) -> set[str]:
    """A decision that mentions a rule_id (CRIT-XXX, MAJ-XXX, MIN-XXX) is
    treated as acknowledging / remediating that rule — the gate skips its
    findings to avoid the chicken-and-egg of fixing drift via decisions."""
    text = " ".join(filter(None, [
        decision.title, decision.problem_statement,
        decision.requested_action, decision.execution_plan,
        " ".join(decision.assumptions or []),
        " ".join(decision.constraints or []),
    ]))
    return set(m.group(0).upper()
               for m in re.finditer(r"\b(?:CRIT|MAJ|MIN|INFO)-\d{3}\b",
                                    text, re.IGNORECASE))


def _query_critical_drift(
    db_path: Path,
    tokens: set[str],
    acknowledged: set[str],
    lookback_days: int,
) -> list[tuple[str, str]]:
    """Return [(rule_id, artifact)] for unresolved critical violations
    from the most-recent scan whose artifact intersects `tokens` and
    whose rule_id is not in `acknowledged`."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=lookback_days)).isoformat()
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        # Use only the most recent scan to avoid reporting resolved drift
        cur = conn.execute("""
            SELECT scan_id FROM scans
            WHERE timestamp > ?
            ORDER BY timestamp DESC LIMIT 1
        """, (cutoff,))
        latest = cur.fetchone()
        if not latest:
            conn.close()
            return []
        scan_id = latest[0]
        cur = conn.execute("""
            SELECT DISTINCT rule_id, artifact
            FROM violations
            WHERE scan_id = ? AND severity = 'critical'
        """, (scan_id,))
        rows = cur.fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    matches: list[tuple[str, str]] = []
    for rule_id, artifact in rows:
        if rule_id.upper() in acknowledged:
            continue
        artifact_lower = (artifact or "").lower()
        if any(t in artifact_lower for t in tokens):
            matches.append((rule_id, artifact))
    return matches


def gate_8_drift_check(
    decision: DecisionObject,
    drift_db_path: Optional[Path] = None,
    lookback_days: int = 30,
) -> tuple[bool, str]:
    """Gate 8: No open critical drift touches this decision's domain.

    Recursive self-governance — closes the loop between drift_sentinel
    findings and the 7-gate authorization. A decision that targets a
    domain with unresolved critical drift cannot AUTO_EXECUTE.

    Acknowledgment escape hatch: if the decision text references the
    rule_id (e.g., 'CRIT-008', 'MAJ-005'), the gate treats that rule
    as being remediated and skips its findings.
    """
    db_path = drift_db_path or _default_drift_db_path()
    if db_path is None or not Path(db_path).exists():
        return True, "Drift history unavailable — gate skipped (warning)"
    tokens = _extract_domain_tokens(decision)
    if not tokens:
        return True, "Decision has no domain tokens to check"
    acknowledged = _acknowledged_rule_ids(decision)
    matches = _query_critical_drift(
        db_path, tokens, acknowledged, lookback_days)
    if not matches:
        msg = "No open critical drift touches this domain"
        if acknowledged:
            msg += f" (acknowledged: {sorted(acknowledged)})"
        return True, msg
    sample = ", ".join(f"{r}@{a.split('/')[-1]}" for r, a in matches[:3])
    suffix = f" (+{len(matches) - 3} more)" if len(matches) > 3 else ""
    return False, (
        f"{len(matches)} critical drift findings touch this domain: "
        f"{sample}{suffix}. Acknowledge by referencing the rule_id "
        "in problem_statement / requested_action / execution_plan."
    )


# ─────────────────────────────────────────────
# 8-GATE AUTHORIZATION ORCHESTRATOR
# ─────────────────────────────────────────────

def run_7_gate_authorization(
    decision: DecisionObject,
    trust_tier: TrustTier,
    net_value: int,
    alignment: AlignmentScores,
    certificate_chain: CertificateChain,
    drift_db_path: Optional[Path] = None,
) -> ExecutionPacket:
    """
    Run all 8 gates sequentially.
    Returns an ExecutionPacket with verdict, gate results, and escalation routing.

    Note: function name kept as `run_7_gate_authorization` for callsite
    compatibility; gate 8 (drift_check) is added at the end and treated
    as structural (failure → BLOCK).
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
        ("gate_8_drift_check",
         lambda: gate_8_drift_check(decision, drift_db_path)),
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

    # Gates 1-3 + 8 are structural — any failure = BLOCK
    # (Gate 8 is structural because unresolved critical drift in the
    # decision's domain means the doctrine baseline isn't met)
    structural_failures = [g for g in failed_gates if g in (
        "gate_1_doctrine", "gate_2_trust_tier", "gate_3_value_threshold",
        "gate_8_drift_check",
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
