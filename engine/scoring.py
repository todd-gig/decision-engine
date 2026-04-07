"""
Scoring Engines — Value, Trust, Alignment, and Priority

Implements:
- Trust tier calculation from 7 trust inputs
- Value-adjusted scoring with RTQL trust multiplier
- Alignment composite scoring with anti-pattern detection
- Decision Priority Score formula from CLAUDE.md
"""

from .models import (
    DecisionObject, TrustTier, TrustScores, ValueScores,
    AlignmentScores
)


# ─────────────────────────────────────────────
# TRUST TIER CALCULATION
# ─────────────────────────────────────────────

# Tier thresholds based on trust matrix spec:
# T0: total < 10 (avg < 1.4)
# T1: 10 <= total < 17 (avg ~1.4-2.4)
# T2: 17 <= total < 24 (avg ~2.4-3.4)
# T3: 24 <= total < 30 (avg ~3.4-4.3)
# T4: total >= 30 (avg >= 4.3)

TIER_THRESHOLDS = [
    (30, TrustTier.T4_DELEGATED),
    (24, TrustTier.T3_CERTIFIED),
    (17, TrustTier.T2_QUALIFIED),
    (10, TrustTier.T1_OBSERVED),
    (0,  TrustTier.T0_UNQUALIFIED),
]

# Minimum per-dimension scores for promotion guard
PROMOTION_GUARDS = {
    TrustTier.T2_QUALIFIED: {
        'evidence_quality': 2,
        'auditability': 2,
    },
    TrustTier.T3_CERTIFIED: {
        'evidence_quality': 3,
        'logic_integrity': 3,
        'risk_containment': 3,
        'auditability': 3,
    },
    TrustTier.T4_DELEGATED: {
        'evidence_quality': 4,
        'logic_integrity': 4,
        'outcome_history': 4,
        'risk_containment': 4,
        'auditability': 4,
    },
}


def calculate_trust_tier(scores: TrustScores) -> tuple[TrustTier, list[str]]:
    """
    Calculate trust tier from 7 trust inputs.
    Returns (tier, demotion_reasons).

    Applies promotion guards: even if total is high enough,
    individual dimension minimums must be met.
    """
    total = scores.total()
    demotion_reasons = []

    # Find base tier from total
    base_tier = TrustTier.T0_UNQUALIFIED
    for threshold, tier in TIER_THRESHOLDS:
        if total >= threshold:
            base_tier = tier
            break

    # Apply promotion guards — demote if minimums not met
    effective_tier = base_tier
    if base_tier in PROMOTION_GUARDS:
        guards = PROMOTION_GUARDS[base_tier]
        for dim, minimum in guards.items():
            actual = getattr(scores, dim, 0)
            if actual < minimum:
                demotion_reasons.append(
                    f"{dim}={actual} below minimum {minimum} for {base_tier.value}"
                )

    # If any guard fails, drop one tier
    if demotion_reasons:
        tier_order = [
            TrustTier.T0_UNQUALIFIED,
            TrustTier.T1_OBSERVED,
            TrustTier.T2_QUALIFIED,
            TrustTier.T3_CERTIFIED,
            TrustTier.T4_DELEGATED,
        ]
        idx = tier_order.index(base_tier)
        effective_tier = tier_order[max(0, idx - 1)]

    return effective_tier, demotion_reasons


# ─────────────────────────────────────────────
# TRUST-ADJUSTED VALUE SCORING
# ─────────────────────────────────────────────

def trust_adjusted_value(value_scores: ValueScores,
                          rtql_multiplier: float) -> float:
    """
    Apply RTQL trust multiplier to net value score.
    Adjusted Value = Net Value × Trust Multiplier
    """
    return value_scores.net_value() * rtql_multiplier


# ─────────────────────────────────────────────
# ALIGNMENT SCORING
# ─────────────────────────────────────────────

# The 7 anti-patterns from org ethos doc
ANTI_PATTERNS = [
    "optics_over_substance",
    "complexity_without_leverage",
    "short_term_extraction_harms_trust",
    "undefined_ownership",
    "decisions_without_auditability",
    "action_without_qualification",
    "automation_without_human_override",
]


def check_alignment(decision: DecisionObject) -> AlignmentScores:
    """
    Evaluate alignment against doctrine, ethos, and first principles.

    This is a structural check — it validates that the human-provided
    alignment scores are internally consistent and flags anti-patterns
    detectable from the decision object itself.
    """
    alignment = decision.alignment_scores
    flags = list(alignment.anti_pattern_flags)  # preserve human-provided flags

    # Auto-detect structural anti-patterns
    if not decision.owner:
        flags.append("undefined_ownership")

    if not decision.evidence_refs:
        flags.append("decisions_without_auditability")

    if decision.value_scores.ethical_misalignment > 3:
        flags.append("ethical_misalignment_above_threshold")

    if (decision.decision_class.value in ("D3", "D4", "D5", "D6") and
            not decision.required_approvals):
        flags.append("action_without_qualification")

    if decision.value_scores.execution_drag > 3 and decision.value_scores.compounding_potential < 2:
        flags.append("complexity_without_leverage")

    if not decision.rollback_trigger and decision.reversibility.value in ("R3", "R4"):
        flags.append("automation_without_human_override")

    # Deduplicate
    alignment.anti_pattern_flags = list(set(flags))

    return alignment


# ─────────────────────────────────────────────
# DECISION PRIORITY SCORE
# ─────────────────────────────────────────────

# From CLAUDE.md:
# Decision Priority Score =
#   ((Expected Value - Total Cost - Risk Penalty)
#    × Probability of Success × Time Leverage)
#   × Strategic Alignment
#   × Ethos Alignment
#   × Trust Multiplier

def calculate_priority_score(
    value_scores: ValueScores,
    trust_tier: TrustTier,
    alignment: AlignmentScores,
    rtql_multiplier: float = 1.0,
    probability_of_success: float = 0.7,
) -> float:
    """
    Calculate the Decision Priority Score per the formula in CLAUDE.md.

    Maps model dimensions to formula components:
    - Expected Value = gross_value
    - Total Cost = execution_drag (proxy for coordination/resource cost)
    - Risk Penalty = downside_risk + uncertainty
    - Time Leverage = time_leverage dimension (normalized to 0-1)
    - Strategic Alignment = strategic_alignment (normalized to 0-1)
    - Ethos Alignment = alignment.ethos_alignment
    - Trust Multiplier = tier-based multiplier × RTQL multiplier
    """
    expected_value = value_scores.gross_value()
    total_cost = value_scores.execution_drag
    risk_penalty = value_scores.downside_risk + value_scores.uncertainty
    time_leverage = value_scores.time_leverage / 5.0  # normalize to 0-1

    # Trust multiplier from tier
    tier_multipliers = {
        TrustTier.T0_UNQUALIFIED: 0.2,
        TrustTier.T1_OBSERVED: 0.5,
        TrustTier.T2_QUALIFIED: 0.8,
        TrustTier.T3_CERTIFIED: 1.0,
        TrustTier.T4_DELEGATED: 1.2,
    }
    trust_mult = tier_multipliers.get(trust_tier, 0.2)

    # Strategic alignment from value scores (normalized 0-1)
    strategic_align = value_scores.strategic_alignment / 5.0

    # Ethos alignment from alignment scores (already 0-1)
    ethos_align = alignment.ethos_alignment

    # Core formula
    base = (expected_value - total_cost - risk_penalty)
    if base <= 0:
        base = max(base, -10)  # floor the negative to prevent extreme inversions

    score = (
        base
        * probability_of_success
        * max(time_leverage, 0.1)  # floor to prevent zero-out
        * max(strategic_align, 0.1)
        * max(ethos_align, 0.1)
        * trust_mult
        * rtql_multiplier
    )

    return round(score, 3)
