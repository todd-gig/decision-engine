"""
Gap Analysis Engine

From Claude Client Intelligence Engine Spec.

Detects performance gaps across decision dimensions and organizational
categories, applies trust-penalty modifiers, and generates prioritized
action recommendations.

Gap Detection Rules — a gap exists when:
    - actual score < target
    - RTQL trust < required threshold
    - evidence is weak
    - execution maturity is low relative to strategic importance
    - variable has strong leverage but low performance

Gap Formula:
    Gap Score = (Target - Actual) × Strategic Importance × Trust Penalty Modifier

Trust Penalty Modifier:
    1.25 if RTQL < qualified
    1.10 if RTQL = certification_gap
    1.00 if RTQL >= certified

Priority Formula:
    Priority Score = (Gap Score × 0.35) + (Leverage × 0.30) + (Urgency × 0.20) + (Value Impact × 0.15)
"""

from dataclasses import dataclass, field
from .models import RTQLStage


# ─────────────────────────────────────────────
# GAP SEVERITY BANDS
# ─────────────────────────────────────────────

def gap_severity(gap_score: float) -> str:
    if gap_score >= 46:
        return "critical"
    elif gap_score >= 26:
        return "major"
    elif gap_score >= 11:
        return "moderate"
    else:
        return "minor"


# ─────────────────────────────────────────────
# TRUST PENALTY MODIFIER
# ─────────────────────────────────────────────

def trust_penalty_modifier(rtql_stage: RTQLStage) -> float:
    """
    Higher modifier = worse penalty for low-trust inputs.
    This amplifies gaps when evidence quality is poor.
    """
    low_trust = {
        RTQLStage.NOISE, RTQLStage.WEAK_SIGNAL,
        RTQLStage.ECHO_SIGNAL, RTQLStage.QUALIFIED,
    }
    if rtql_stage in low_trust:
        return 1.25
    elif rtql_stage == RTQLStage.CERTIFICATION_GAP:
        return 1.10
    else:
        return 1.00


# ─────────────────────────────────────────────
# GAP ANALYSIS DATA STRUCTURES
# ─────────────────────────────────────────────

@dataclass
class GapItem:
    category: str = ""
    variable: str = ""
    actual_score: float = 0.0
    target_score: float = 5.0
    strategic_importance: float = 1.0
    rtql_stage: RTQLStage = RTQLStage.QUALIFIED
    leverage_score: float = 0.0
    urgency_score: float = 0.0
    value_matrix_impact: float = 0.0
    gap_score: float = 0.0
    gap_severity_label: str = "minor"
    priority_score: float = 0.0
    trust_penalty: float = 1.0


@dataclass
class ActionItem:
    category: str = ""
    variable: str = ""
    current_score: float = 0.0
    target_score: float = 0.0
    rtql_stage: str = ""
    gap_severity_label: str = ""
    leverage_score: float = 0.0
    urgency_score: float = 0.0
    priority_score: float = 0.0
    root_cause_hypothesis: str = ""
    required_research: list[str] = field(default_factory=list)
    recommended_action: list[str] = field(default_factory=list)
    expected_impact: dict = field(default_factory=lambda: {
        "revenue": "low", "trust": "low", "speed": "low", "risk_reduction": "low"
    })
    timeline: str = ""
    owner_type: str = ""


# ─────────────────────────────────────────────
# GAP CALCULATION
# ─────────────────────────────────────────────

def calculate_gap(
    actual: float,
    target: float,
    strategic_importance: float,
    rtql_stage: RTQLStage,
) -> tuple[float, float, str]:
    """
    Calculate gap score with trust penalty.
    Returns (gap_score, trust_penalty, severity).
    """
    raw_gap = max(target - actual, 0)
    penalty = trust_penalty_modifier(rtql_stage)
    score = raw_gap * strategic_importance * penalty
    severity = gap_severity(score)
    return round(score, 2), penalty, severity


def calculate_priority(
    gap_score: float,
    leverage_score: float,
    urgency_score: float,
    value_matrix_impact: float,
) -> float:
    """
    Priority Score = (Gap × 0.35) + (Leverage × 0.30) + (Urgency × 0.20) + (Value Impact × 0.15)
    """
    return round(
        (gap_score * 0.35) +
        (leverage_score * 0.30) +
        (urgency_score * 0.20) +
        (value_matrix_impact * 0.15),
        2
    )


# ─────────────────────────────────────────────
# BATCH GAP ANALYSIS
# ─────────────────────────────────────────────

def analyze_gaps(items: list[dict]) -> list[GapItem]:
    """
    Process a batch of gap analysis inputs.

    Each item dict should contain:
        category, variable, actual_score, target_score,
        strategic_importance, rtql_stage (str),
        leverage_score, urgency_score, value_matrix_impact

    Returns list of GapItem sorted by priority_score descending.
    """
    results = []

    for item in items:
        stage_str = item.get("rtql_stage", "qualified")
        try:
            rtql_stage = RTQLStage(stage_str)
        except ValueError:
            rtql_stage = RTQLStage.QUALIFIED

        gap_score, penalty, severity = calculate_gap(
            actual=item.get("actual_score", 0),
            target=item.get("target_score", 5),
            strategic_importance=item.get("strategic_importance", 1.0),
            rtql_stage=rtql_stage,
        )

        priority = calculate_priority(
            gap_score=gap_score,
            leverage_score=item.get("leverage_score", 0),
            urgency_score=item.get("urgency_score", 0),
            value_matrix_impact=item.get("value_matrix_impact", 0),
        )

        results.append(GapItem(
            category=item.get("category", ""),
            variable=item.get("variable", ""),
            actual_score=item.get("actual_score", 0),
            target_score=item.get("target_score", 5),
            strategic_importance=item.get("strategic_importance", 1.0),
            rtql_stage=rtql_stage,
            leverage_score=item.get("leverage_score", 0),
            urgency_score=item.get("urgency_score", 0),
            value_matrix_impact=item.get("value_matrix_impact", 0),
            gap_score=gap_score,
            gap_severity_label=severity,
            priority_score=priority,
            trust_penalty=penalty,
        ))

    # Sort by priority descending
    results.sort(key=lambda x: x.priority_score, reverse=True)
    return results


def generate_action_items(gaps: list[GapItem],
                           min_severity: str = "moderate") -> list[ActionItem]:
    """
    Generate action items for gaps at or above minimum severity.
    Severity order: minor < moderate < major < critical
    """
    severity_order = {"minor": 0, "moderate": 1, "major": 2, "critical": 3}
    min_level = severity_order.get(min_severity, 1)

    actions = []
    for gap in gaps:
        if severity_order.get(gap.gap_severity_label, 0) >= min_level:
            research = []
            if gap.rtql_stage in (RTQLStage.NOISE, RTQLStage.WEAK_SIGNAL):
                research.append("Establish auditable source trail")
                research.append("Seek independent confirmation")
            elif gap.rtql_stage == RTQLStage.ECHO_SIGNAL:
                research.append("Find cross-domain independent validation")
            elif gap.rtql_stage == RTQLStage.CERTIFICATION_GAP:
                research.append("Improve mechanistic explainability")
                research.append("Define replication protocol")

            actions.append(ActionItem(
                category=gap.category,
                variable=gap.variable,
                current_score=gap.actual_score,
                target_score=gap.target_score,
                rtql_stage=gap.rtql_stage.value,
                gap_severity_label=gap.gap_severity_label,
                leverage_score=gap.leverage_score,
                urgency_score=gap.urgency_score,
                priority_score=gap.priority_score,
                required_research=research,
            ))

    return actions
