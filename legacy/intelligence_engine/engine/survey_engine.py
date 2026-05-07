"""
Client Intelligence Engine - Survey Processing Pipeline

Transforms raw client survey inputs into trust-qualified, decision-grade intelligence:
- dynamic category scores
- RTQL classifications per input
- gap analysis and prioritization
- research backlog identification

Implements the mandatory processing pipeline from Claude Client Intelligence Engine Spec:
Client Survey Input -> Variable Normalization -> Per-Input RTQL Classification ->
Per-Category Dynamic Scoring -> Trust Adjustment -> Gap Analysis -> Priority Weighting ->
Action Generation -> Executive Summary

Master Categories (15 domains with weights):
1. Identity & Purpose (0.05)
2. Market Reality (0.08)
3. Customer (0.10)
4. Value Creation (0.10)
5. Revenue (0.10)
6. Cost & Resources (0.08)
7. Time (0.07)
8. Trust & Credibility (0.08)
9. Systems & Processes (0.08)
10. Human Capital (0.07)
11. Intelligence & Data (0.06)
12. Growth & Leverage (0.06)
13. Risk & Uncertainty (0.03)
14. Innovation & Adaptation (0.02)
15. Governance & Control (0.02)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import defaultdict

from .rtql_filter import classify_rtql, TRUST_MULTIPLIERS
from .gap_analysis import calculate_gap, calculate_priority, gap_severity, analyze_gaps, generate_action_items, ActionItem
from .models import RTQLInput, RTQLScores, CausalChecks, RTQLStage


# ─────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────

class SourceType(Enum):
    """Source type classification for survey inputs."""
    SELF_REPORT = "self_report"
    INTERNAL_DATA = "internal_data"
    EXTERNAL_DATA = "external_data"
    OBSERVED = "observed"
    INFERRED = "inferred"


# ─────────────────────────────────────────────────────────────
# MASTER CATEGORIES DEFINITION
# ─────────────────────────────────────────────────────────────

MASTER_CATEGORIES = {
    "Identity & Purpose": {
        "weight": 0.05,
        "variables": [
            "mission_clarity",
            "objective_clarity",
            "value_proposition_clarity",
            "principle_coherence",
            "vision_alignment",
        ],
    },
    "Market Reality": {
        "weight": 0.08,
        "variables": [
            "market_definition_clarity",
            "demand_signal_strength",
            "competition_awareness",
            "pricing_pressure_awareness",
            "constraint_awareness",
        ],
    },
    "Customer": {
        "weight": 0.10,
        "variables": [
            "segment_clarity",
            "pain_point_specificity",
            "decision_driver_understanding",
            "trust_trigger_understanding",
            "retention_driver_understanding",
        ],
    },
    "Value Creation": {
        "weight": 0.10,
        "variables": [
            "offer_clarity",
            "differentiation_strength",
            "quality_consistency",
            "delivery_effectiveness",
            "experience_design_quality",
        ],
    },
    "Revenue": {
        "weight": 0.10,
        "variables": [
            "pricing_clarity",
            "revenue_stream_quality",
            "conversion_performance",
            "sales_cycle_efficiency",
            "expansion_revenue_capacity",
        ],
    },
    "Cost & Resources": {
        "weight": 0.08,
        "variables": [
            "cost_visibility",
            "cac_control",
            "resource_allocation_quality",
            "operating_efficiency",
            "capital_adequacy",
        ],
    },
    "Time": {
        "weight": 0.07,
        "variables": [
            "speed_to_lead_conversion",
            "speed_to_onboarding",
            "time_to_value",
            "decision_latency",
            "feedback_loop_speed",
        ],
    },
    "Trust & Credibility": {
        "weight": 0.08,
        "variables": [
            "proof_strength",
            "brand_credibility",
            "consistency_of_delivery",
            "data_integrity",
            "trust_signal_quality",
        ],
    },
    "Systems & Processes": {
        "weight": 0.08,
        "variables": [
            "workflow_clarity",
            "automation_maturity",
            "bottleneck_severity",
            "system_dependence_risk",
            "scale_readiness",
        ],
    },
    "Human Capital": {
        "weight": 0.07,
        "variables": [
            "skill_alignment",
            "role_clarity",
            "leadership_coherence",
            "incentive_quality",
            "adaptability",
        ],
    },
    "Intelligence & Data": {
        "weight": 0.06,
        "variables": [
            "data_availability",
            "data_reliability",
            "analytics_maturity",
            "feedback_system_quality",
            "knowledge_retention_quality",
        ],
    },
    "Growth & Leverage": {
        "weight": 0.06,
        "variables": [
            "channel_scalability",
            "automation_leverage",
            "brand_leverage",
            "distribution_strength",
            "compounding_advantage",
        ],
    },
    "Risk & Uncertainty": {
        "weight": 0.03,
        "variables": [
            "risk_visibility",
            "dependency_concentration",
            "execution_risk",
            "market_uncertainty",
            "contingency_readiness",
        ],
    },
    "Innovation & Adaptation": {
        "weight": 0.02,
        "variables": [
            "experimentation_rate",
            "iteration_speed",
            "learning_rate",
            "opportunity_sensing",
            "adaptation_quality",
        ],
    },
    "Governance & Control": {
        "weight": 0.02,
        "variables": [
            "decision_rights_clarity",
            "accountability_clarity",
            "compliance_maturity",
            "auditability",
            "strategic_alignment",
        ],
    },
}


# ─────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────

@dataclass
class SurveyInput:
    """Normalized survey input record for processing."""
    input_id: str
    category: str
    subcategory: str
    question: str
    raw_response: str
    normalized_value: float  # 0-5 scale
    evidence_provided: str
    source_type: SourceType
    # RTQL dimension scores (0-12 scale with allowed values)
    source_integrity: int = 0
    exposure_count: int = 0
    independence: int = 0
    explainability: int = 0
    replicability: int = 0
    adversarial_robustness: int = 0
    novelty_yield: int = 0
    # Computed fields (populated during processing)
    rtql_stage: Optional[RTQLStage] = None
    trust_multiplier: float = 1.0
    variable_strength: float = 0.0
    evidence_quality: float = 0.0
    execution_maturity: float = 0.0
    consistency: float = 0.0
    strategic_fit: float = 0.0
    category_score: float = 0.0
    trust_adjusted_score: float = 0.0

    def to_rtql_input(self) -> RTQLInput:
        """Convert to RTQLInput for classification."""
        return RTQLInput(
            claim=self.question,
            source=self.source_type.value,
            is_identifiable=len(self.input_id) > 0,
            has_provenance=len(self.evidence_provided) > 0,
            scores=RTQLScores(
                source_integrity=self.source_integrity,
                exposure_count=self.exposure_count,
                independence=self.independence,
                explainability=self.explainability,
                replicability=self.replicability,
                adversarial_robustness=self.adversarial_robustness,
                novelty_yield=self.novelty_yield,
            ),
            causal_checks=CausalChecks(),  # Can be extended if causal data provided
        )


@dataclass
class CategoryScore:
    """Score for a single category."""
    category: str
    weight: float
    raw_score: float = 0.0
    trust_adjusted_score: float = 0.0
    target_score: float = 5.0
    gap_score: float = 0.0
    gap_severity: str = "minor"
    input_count: int = 0
    rtql_stages: dict = field(default_factory=lambda: defaultdict(int))  # stage -> count
    lowest_rtql_stage: Optional[RTQLStage] = None


@dataclass
class SurveyResult:
    """Complete result of survey processing pipeline."""
    survey_id: str
    category_scores: dict[str, CategoryScore] = field(default_factory=dict)
    rtql_trust_map: dict[str, list[dict]] = field(default_factory=dict)  # category -> list of variable info
    gap_analysis: list[dict] = field(default_factory=list)
    priority_queue: list[ActionItem] = field(default_factory=list)
    research_backlog: list[dict] = field(default_factory=list)
    executive_summary: dict = field(default_factory=dict)
    inputs_processed: int = 0


# ─────────────────────────────────────────────────────────────
# CATEGORY SCORE CALCULATION
# ─────────────────────────────────────────────────────────────

def compute_category_score(inputs_for_category: list[SurveyInput]) -> tuple[float, dict]:
    """
    Compute raw category score from normalized input variables.

    Category Score = (Variable Strength × 0.35) +
                     (Evidence Quality × 0.20) +
                     (Execution Maturity × 0.20) +
                     (Consistency × 0.15) +
                     (Strategic Fit × 0.10)

    Returns (raw_score, component_dict)
    """
    if not inputs_for_category:
        return 0.0, {}

    # Aggregate components across inputs
    agg_variable_strength = 0.0
    agg_evidence_quality = 0.0
    agg_execution_maturity = 0.0
    agg_consistency = 0.0
    agg_strategic_fit = 0.0
    count = len(inputs_for_category)

    for inp in inputs_for_category:
        # normalized_value (0-5) represents variable strength
        agg_variable_strength += inp.normalized_value

        # evidence_quality: approximate from evidence_provided length (0-5 scale)
        # Longer, more detailed evidence = higher quality
        evidence_length = len(inp.evidence_provided)
        evidence_score = min(5.0, evidence_length / 50.0)  # Normalize ~250 chars to 5
        agg_evidence_quality += evidence_score

        # execution_maturity: approximated from source_type consistency
        # Internal data and observed sources suggest mature execution
        source_maturity = {
            SourceType.SELF_REPORT: 1.0,
            SourceType.INTERNAL_DATA: 4.0,
            SourceType.EXTERNAL_DATA: 3.0,
            SourceType.OBSERVED: 4.5,
            SourceType.INFERRED: 2.0,
        }
        agg_execution_maturity += source_maturity.get(inp.source_type, 2.0)

        # consistency: approximated from independence + exposure_count
        # Higher independence and exposure = more consistent
        consistency_score = (inp.independence + inp.exposure_count) / 4.0
        agg_consistency += consistency_score

        # strategic_fit: approximated from explainability + replicability
        # More explainable and replicable = better strategic fit
        fit_score = (inp.explainability + inp.replicability) / 4.0
        agg_strategic_fit += fit_score

    # Average the components
    avg_variable_strength = agg_variable_strength / count
    avg_evidence_quality = agg_evidence_quality / count
    avg_execution_maturity = agg_execution_maturity / count
    avg_consistency = agg_consistency / count
    avg_strategic_fit = agg_strategic_fit / count

    # Normalize all to 0-5 range
    avg_variable_strength = min(5.0, avg_variable_strength)
    avg_evidence_quality = min(5.0, avg_evidence_quality)
    avg_execution_maturity = min(5.0, avg_execution_maturity)
    avg_consistency = min(5.0, avg_consistency)
    avg_strategic_fit = min(5.0, avg_strategic_fit)

    # Apply weights
    raw_score = (
        (avg_variable_strength * 0.35) +
        (avg_evidence_quality * 0.20) +
        (avg_execution_maturity * 0.20) +
        (avg_consistency * 0.15) +
        (avg_strategic_fit * 0.10)
    )

    components = {
        "variable_strength": round(avg_variable_strength, 2),
        "evidence_quality": round(avg_evidence_quality, 2),
        "execution_maturity": round(avg_execution_maturity, 2),
        "consistency": round(avg_consistency, 2),
        "strategic_fit": round(avg_strategic_fit, 2),
    }

    return round(raw_score, 2), components


# ─────────────────────────────────────────────────────────────
# RTQL TRUST MAP GENERATION
# ─────────────────────────────────────────────────────────────

def build_rtql_trust_map(
    inputs: list[SurveyInput],
    category: str,
) -> list[dict]:
    """
    Build a trust map for a category showing RTQL stage per variable.

    Returns list of dicts with:
    - variable name
    - rtql_stage
    - trust_multiplier
    - evidence gaps (for certification_gap and below)
    """
    trust_map = []
    for inp in inputs:
        entry = {
            "variable": inp.subcategory,
            "question": inp.question,
            "rtql_stage": inp.rtql_stage.value if inp.rtql_stage else "unknown",
            "trust_multiplier": inp.trust_multiplier,
            "source_type": inp.source_type.value,
            "normalized_value": inp.normalized_value,
        }

        # Add evidence gaps for low-trust inputs
        gaps = []
        if inp.source_integrity < 4:
            gaps.append("Low source integrity")
        if inp.exposure_count < 3:
            gaps.append("Limited exposure (< 3)")
        if inp.independence < 4:
            gaps.append("Limited independence")
        if inp.explainability < 6:
            gaps.append("Explainability gap")
        if inp.replicability < 6:
            gaps.append("Replicability gap")
        if inp.adversarial_robustness < 6:
            gaps.append("Adversarial robustness gap")

        if gaps:
            entry["evidence_gaps"] = gaps
            entry["trust_concerns"] = "; ".join(gaps)

        trust_map.append(entry)

    return trust_map


# ─────────────────────────────────────────────────────────────
# RESEARCH BACKLOG GENERATION
# ─────────────────────────────────────────────────────────────

def generate_research_backlog(inputs: list[SurveyInput]) -> list[dict]:
    """
    Identify inputs below certification that require research.

    Returns list of backlog items with:
    - category, variable, rtql_stage
    - specific research needed to upgrade
    """
    backlog = []
    for inp in inputs:
        if inp.rtql_stage in (
            RTQLStage.NOISE,
            RTQLStage.WEAK_SIGNAL,
            RTQLStage.ECHO_SIGNAL,
            RTQLStage.QUALIFIED,
            RTQLStage.CERTIFICATION_GAP,
        ):
            research_needed = []

            if inp.source_integrity < 4:
                research_needed.append("Locate or establish auditable source trail")
            if inp.exposure_count < 3:
                research_needed.append(f"Monitor for repeat appearances ({3 - inp.exposure_count} more needed)")
            if inp.independence < 4:
                research_needed.append(
                    f"Seek independent confirmation ({4 - inp.independence} more independent sources)"
                )
            if inp.explainability < 6:
                research_needed.append(f"Improve explainability ({6 - inp.explainability} points needed)")
            if inp.replicability < 6:
                research_needed.append(f"Define and test replication protocol ({6 - inp.replicability} points)")
            if inp.adversarial_robustness < 6:
                research_needed.append(f"Design adversarial testing ({6 - inp.adversarial_robustness} points)")

            backlog.append({
                "input_id": inp.input_id,
                "category": inp.category,
                "variable": inp.subcategory,
                "question": inp.question,
                "rtql_stage": inp.rtql_stage.value if inp.rtql_stage else "unknown",
                "current_score_lowest_dimension": min(
                    inp.source_integrity,
                    inp.exposure_count,
                    inp.independence,
                    inp.explainability,
                    inp.replicability,
                    inp.adversarial_robustness,
                ),
                "research_needed": research_needed,
            })

    # Sort by importance (lower trust = earlier)
    stage_priority = {
        RTQLStage.NOISE: 0,
        RTQLStage.WEAK_SIGNAL: 1,
        RTQLStage.ECHO_SIGNAL: 2,
        RTQLStage.QUALIFIED: 3,
        RTQLStage.CERTIFICATION_GAP: 4,
    }
    backlog.sort(key=lambda x: stage_priority.get(x.get("rtql_stage"), 5))

    return backlog


# ─────────────────────────────────────────────────────────────
# EXECUTIVE SUMMARY GENERATION
# ─────────────────────────────────────────────────────────────

def generate_executive_summary(
    category_scores: dict[str, CategoryScore],
    priority_queue: list[ActionItem],
    research_backlog: list[dict],
) -> dict:
    """
    Generate executive summary covering:
    - strongest categories
    - weakest categories
    - highest-confidence findings
    - biggest trust deficits
    - highest-ROI priorities
    """
    if not category_scores:
        return {}

    # Rank categories by trust-adjusted score
    ranked_categories = sorted(
        category_scores.values(),
        key=lambda x: x.trust_adjusted_score,
        reverse=True,
    )

    strongest = [c.category for c in ranked_categories[:3]]
    weakest = [c.category for c in ranked_categories[-3:]]

    # Highest-confidence findings (trust_adjusted > 4.0 or equivalent)
    confident = [
        c.category
        for c in ranked_categories
        if c.trust_adjusted_score >= 4.0
    ]

    # Trust deficits (low RTQL or many certification gaps)
    trust_deficits = [
        c.category
        for c in ranked_categories
        if c.lowest_rtql_stage in (
            RTQLStage.NOISE,
            RTQLStage.WEAK_SIGNAL,
            RTQLStage.ECHO_SIGNAL,
        )
    ]

    # High-ROI priorities (top 5 from priority queue)
    top_priorities = [
        {
            "variable": a.variable,
            "category": a.category,
            "priority_score": a.priority_score,
            "gap_severity": a.gap_severity_label,
        }
        for a in priority_queue[:5]
    ]

    return {
        "strongest_categories": strongest,
        "weakest_categories": weakest,
        "highest_confidence_findings": confident,
        "biggest_trust_deficits": trust_deficits,
        "highest_roi_priorities": top_priorities,
        "total_inputs_processed": sum(c.input_count for c in category_scores.values()),
        "categories_with_gaps": sum(1 for c in category_scores.values() if c.gap_score > 0),
        "items_in_research_backlog": len(research_backlog),
    }


# ─────────────────────────────────────────────────────────────
# MAIN PROCESSING PIPELINE
# ─────────────────────────────────────────────────────────────

def process_survey(survey_id: str, inputs: list[SurveyInput]) -> SurveyResult:
    """
    Main entry point: transform survey inputs into decision-grade intelligence.

    Pipeline:
    1. Classify each input through RTQL
    2. Compute per-category dynamic scores
    3. Apply trust adjustment
    4. Run gap analysis
    5. Generate priority queue
    6. Identify research backlog
    7. Create executive summary

    Args:
        survey_id: Unique survey identifier
        inputs: List of normalized SurveyInput records

    Returns:
        SurveyResult with complete analysis
    """
    result = SurveyResult(survey_id=survey_id)

    if not inputs:
        return result

    # ── Step 1: RTQL Classification ──
    for inp in inputs:
        rtql_input = inp.to_rtql_input()
        rtql_result = classify_rtql(rtql_input)
        inp.rtql_stage = rtql_result.stage
        inp.trust_multiplier = rtql_result.trust_multiplier

    # ── Step 2: Group inputs by category & compute category scores ──
    inputs_by_category = defaultdict(list)
    for inp in inputs:
        inputs_by_category[inp.category].append(inp)

    for category_name, category_config in MASTER_CATEGORIES.items():
        category_inputs = inputs_by_category.get(category_name, [])

        if not category_inputs:
            # No inputs for this category — create empty score
            score = CategoryScore(
                category=category_name,
                weight=category_config["weight"],
                raw_score=0.0,
                trust_adjusted_score=0.0,
            )
        else:
            # Compute raw score
            raw_score, components = compute_category_score(category_inputs)

            # Track RTQL stages and find lowest
            rtql_stages = defaultdict(int)
            lowest_stage = RTQLStage.QUALIFIED
            for inp in category_inputs:
                rtql_stages[inp.rtql_stage] += 1
                # Determine lowest stage (noise < weak_signal < ... < first_principles)
                stage_order = {
                    RTQLStage.NOISE: 0,
                    RTQLStage.WEAK_SIGNAL: 1,
                    RTQLStage.ECHO_SIGNAL: 2,
                    RTQLStage.QUALIFIED: 3,
                    RTQLStage.CERTIFICATION_GAP: 4,
                    RTQLStage.CERTIFIED: 5,
                    RTQLStage.RESEARCH_GRADE: 6,
                    RTQLStage.FIRST_PRINCIPLES_CANDIDATE: 7,
                    RTQLStage.AXIOM_CANDIDATE: 8,
                }
                if stage_order.get(inp.rtql_stage, 3) < stage_order.get(lowest_stage, 3):
                    lowest_stage = inp.rtql_stage

            # Apply trust adjustment using average trust multiplier
            avg_trust_multiplier = sum(inp.trust_multiplier for inp in category_inputs) / len(category_inputs)
            trust_adjusted_score = raw_score * avg_trust_multiplier

            # Calculate gap
            gap_score, _, gap_sev = calculate_gap(
                actual=trust_adjusted_score,
                target=5.0,
                strategic_importance=category_config["weight"],
                rtql_stage=lowest_stage,
            )

            score = CategoryScore(
                category=category_name,
                weight=category_config["weight"],
                raw_score=raw_score,
                trust_adjusted_score=round(trust_adjusted_score, 2),
                target_score=5.0,
                gap_score=gap_score,
                gap_severity=gap_sev,
                input_count=len(category_inputs),
                rtql_stages=dict(rtql_stages),
                lowest_rtql_stage=lowest_stage,
            )

        result.category_scores[category_name] = score

    # ── Step 3: Build RTQL trust map ──
    for category_name, category_inputs in inputs_by_category.items():
        result.rtql_trust_map[category_name] = build_rtql_trust_map(
            category_inputs,
            category_name,
        )

    # ── Step 4: Run gap analysis ──
    gap_items = []
    for category_name, score in result.category_scores.items():
        if score.input_count > 0:
            gap_items.append({
                "category": category_name,
                "variable": f"{category_name} (category-level)",
                "actual_score": score.trust_adjusted_score,
                "target_score": score.target_score,
                "strategic_importance": score.weight,
                "rtql_stage": score.lowest_rtql_stage.value if score.lowest_rtql_stage else "qualified",
                "leverage_score": 1.0 * (score.weight * 10),  # Scale weight to 0-5 range
                "urgency_score": 2.0,  # Default medium urgency
                "value_matrix_impact": score.weight * 5,  # Scale to 0-5
            })

    analyzed_gaps = analyze_gaps(gap_items)
    result.gap_analysis = [
        {
            "category": g.category,
            "variable": g.variable,
            "actual_score": g.actual_score,
            "target_score": g.target_score,
            "gap_score": g.gap_score,
            "gap_severity": g.gap_severity_label,
            "priority_score": g.priority_score,
        }
        for g in analyzed_gaps
    ]

    # ── Step 5: Generate priority queue ──
    action_items = generate_action_items(analyzed_gaps, min_severity="moderate")
    result.priority_queue = sorted(action_items, key=lambda x: x.priority_score, reverse=True)

    # ── Step 6: Identify research backlog ──
    result.research_backlog = generate_research_backlog(inputs)

    # ── Step 7: Generate executive summary ──
    result.executive_summary = generate_executive_summary(
        result.category_scores,
        result.priority_queue,
        result.research_backlog,
    )

    result.inputs_processed = len(inputs)

    return result
