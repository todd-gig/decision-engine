"""
Weighted Value & Trust Scoring

Unlike the base scoring module (which uses raw 0-5 scores),
this module applies configurable asymmetric weights from engine.yaml.

This produces the weighted scores used by the policy engine and
priority score calculator.

Key difference:
- Base scoring: raw_score sums (0-40 gross, 0-20 penalty)
- Weighted scoring: raw_score × weight per dimension (strategic_alignment
  at 2.0× matters twice as much as reversibility at 1.0×)
"""

from .models import ValueScores, TrustScores, TrustTier
from .config import EngineConfig, ValueWeights, PenaltyWeights


def compute_weighted_value(
    value_scores: ValueScores,
    config: EngineConfig,
) -> dict:
    """
    Compute weighted value scores using engine config weights.

    Returns dict with:
    - weighted_gross: sum of (dimension × weight)
    - weighted_penalty: sum of (penalty × weight)
    - weighted_net: gross - penalty
    - raw_net: unweighted net (for backward compat)
    - dimension_contributions: per-dimension weighted scores
    """
    vw = config.value_weights
    pw = config.penalty_weights

    # Positive dimensions × weights
    positive_contributions = {
        "revenue_impact": value_scores.revenue_impact * vw.revenue_impact,
        "cost_efficiency": value_scores.cost_efficiency * vw.cost_efficiency,
        "time_leverage": value_scores.time_leverage * vw.time_leverage,
        "strategic_alignment": value_scores.strategic_alignment * vw.strategic_alignment,
        "customer_benefit": value_scores.customer_human_benefit * vw.customer_benefit,
        "knowledge_creation": value_scores.knowledge_asset_creation * vw.knowledge_creation,
        "compounding_potential": value_scores.compounding_potential * vw.compounding_potential,
        "reversibility": value_scores.reversibility * vw.reversibility,
    }

    # Penalty dimensions × weights
    penalty_contributions = {
        "downside_risk": value_scores.downside_risk * pw.downside_risk,
        "execution_drag": value_scores.execution_drag * pw.execution_drag,
        "uncertainty": value_scores.uncertainty * pw.uncertainty,
        "ethical_misalignment": value_scores.ethical_misalignment * pw.ethical_misalignment,
    }

    weighted_gross = sum(positive_contributions.values())
    weighted_penalty = sum(penalty_contributions.values())
    weighted_net = weighted_gross - weighted_penalty

    return {
        "weighted_gross": round(weighted_gross, 2),
        "weighted_penalty": round(weighted_penalty, 2),
        "weighted_net": round(weighted_net, 2),
        "raw_net": value_scores.net_value(),
        "raw_gross": value_scores.gross_value(),
        "raw_penalty": value_scores.penalty(),
        "positive_contributions": {k: round(v, 2) for k, v in positive_contributions.items()},
        "penalty_contributions": {k: round(v, 2) for k, v in penalty_contributions.items()},
    }


def compute_weighted_trust(
    trust_scores: TrustScores,
    trust_tier: TrustTier,
    config: EngineConfig,
) -> dict:
    """
    Compute trust score adjusted by tier multiplier from config.

    Returns dict with:
    - trust_total: raw sum of 7 inputs
    - trust_average: raw average
    - tier_multiplier: from config
    - adjusted_trust_score: average × tier_multiplier
    """
    total = trust_scores.total()
    average = trust_scores.average()
    tier_mult = config.trust_multiplier.get(trust_tier.value, 0.2)

    return {
        "trust_total": total,
        "trust_average": round(average, 3),
        "trust_tier": trust_tier.value,
        "tier_multiplier": tier_mult,
        "adjusted_trust_score": round(average * tier_mult, 3),
    }
