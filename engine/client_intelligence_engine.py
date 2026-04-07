"""
Client Intelligence Engine
15-category scoring system that integrates with the RTQL Classifier to produce
trust-adjusted intelligence reports, gap analyses, and prioritised action plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engine.rtql_classifier import (
    InputRecord,
    RTQLClassifier,
    TrustStage,
    TRUST_MULTIPLIERS,
)

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------
CATEGORY_WEIGHTS: Dict[str, float] = {
    "identity_purpose": 0.05,
    "market_reality": 0.08,
    "customer": 0.10,
    "value_creation": 0.10,
    "revenue": 0.10,
    "cost_resources": 0.08,
    "time": 0.07,
    "trust_credibility": 0.08,
    "systems_processes": 0.08,
    "human_capital": 0.07,
    "intelligence_data": 0.06,
    "growth_leverage": 0.06,
    "risk_uncertainty": 0.03,
    "innovation_adaptation": 0.02,
    "governance_control": 0.02,
}

# Human-readable labels for the 15 categories
CATEGORY_LABELS: Dict[str, str] = {
    "identity_purpose": "Identity & Purpose",
    "market_reality": "Market Reality",
    "customer": "Customer",
    "value_creation": "Value Creation",
    "revenue": "Revenue",
    "cost_resources": "Cost & Resources",
    "time": "Time",
    "trust_credibility": "Trust & Credibility",
    "systems_processes": "Systems & Processes",
    "human_capital": "Human Capital",
    "intelligence_data": "Intelligence & Data",
    "growth_leverage": "Growth & Leverage",
    "risk_uncertainty": "Risk & Uncertainty",
    "innovation_adaptation": "Innovation & Adaptation",
    "governance_control": "Governance & Control",
}

# 5 sub-variables per category
CATEGORY_SUB_VARIABLES: Dict[str, List[str]] = {
    "identity_purpose": [
        "mission_clarity", "vision_alignment", "value_proposition",
        "purpose_coherence", "brand_authenticity",
    ],
    "market_reality": [
        "market_size", "competitive_intensity", "market_growth_rate",
        "regulatory_environment", "market_accessibility",
    ],
    "customer": [
        "customer_segmentation", "customer_lifetime_value", "acquisition_cost",
        "retention_rate", "customer_satisfaction",
    ],
    "value_creation": [
        "value_differentiation", "product_market_fit", "delivery_capability",
        "innovation_pipeline", "ip_strength",
    ],
    "revenue": [
        "revenue_growth", "revenue_diversification", "pricing_power",
        "revenue_predictability", "unit_economics",
    ],
    "cost_resources": [
        "cost_structure", "resource_efficiency", "capital_intensity",
        "operational_leverage", "supplier_dependency",
    ],
    "time": [
        "time_to_value", "cycle_time", "runway",
        "time_to_market", "payback_period",
    ],
    "trust_credibility": [
        "reputation_score", "testimonials_evidence", "track_record",
        "compliance_posture", "stakeholder_trust",
    ],
    "systems_processes": [
        "process_maturity", "automation_level", "scalability",
        "integration_capability", "technical_debt",
    ],
    "human_capital": [
        "team_capability", "leadership_quality", "talent_density",
        "culture_strength", "succession_planning",
    ],
    "intelligence_data": [
        "data_quality", "analytics_maturity", "decision_intelligence",
        "feedback_loops", "competitive_intelligence",
    ],
    "growth_leverage": [
        "growth_rate", "leverage_points", "network_effects",
        "expansion_optionality", "compounding_mechanisms",
    ],
    "risk_uncertainty": [
        "risk_identification", "risk_mitigation", "scenario_planning",
        "insurance_coverage", "crisis_readiness",
    ],
    "innovation_adaptation": [
        "innovation_cadence", "adaptability", "experimentation_culture",
        "technology_adoption", "learning_velocity",
    ],
    "governance_control": [
        "governance_structure", "compliance_controls", "audit_readiness",
        "board_oversight", "policy_enforcement",
    ],
}

# Category score formula weights
_VS = 0.35   # Variable Strength
_EQ = 0.20   # Evidence Quality
_EM = 0.20   # Execution Maturity
_CO = 0.15   # Consistency
_SF = 0.10   # Strategic Fit

# Gap severity bands
GAP_SEVERITY_BANDS: List[Tuple[float, str]] = [
    (10.0,  "minor"),
    (25.0,  "moderate"),
    (45.0,  "major"),
    (float("inf"), "critical"),
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class CategoryScore:
    """Scored result for a single intelligence category."""
    category_key: str
    category_label: str
    weight: float

    # Raw component scores (0–100 scale each)
    variable_strength: float = 0.0
    evidence_quality: float = 0.0
    execution_maturity: float = 0.0
    consistency: float = 0.0
    strategic_fit: float = 0.0

    # Computed
    raw_score: float = field(init=False, default=0.0)
    trust_adjusted_score: float = field(init=False, default=0.0)
    trust_multiplier: float = 1.0

    # Sub-variable detail
    sub_variable_scores: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.raw_score = (
            self.variable_strength * _VS
            + self.evidence_quality * _EQ
            + self.execution_maturity * _EM
            + self.consistency * _CO
            + self.strategic_fit * _SF
        )
        self.trust_adjusted_score = self.raw_score * self.trust_multiplier


@dataclass
class GapResult:
    """Represents a gap between a target and actual category score."""
    category_key: str
    category_label: str
    actual: float
    target: float
    strategic_importance: float   # 0–1 weight reflecting business priority
    trust_penalty_modifier: float

    gap_score: float = field(init=False, default=0.0)
    severity: str = field(init=False, default="minor")

    def __post_init__(self) -> None:
        raw_gap = max(0.0, self.target - self.actual)
        self.gap_score = raw_gap * self.strategic_importance * self.trust_penalty_modifier
        self.severity = _classify_severity(self.gap_score)


@dataclass
class ActionItem:
    """A prioritised action item derived from gap analysis."""
    category_key: str
    category_label: str
    description: str
    gap_score: float
    leverage: float     # 0–1 estimated leverage of action
    urgency: float      # 0–1 time sensitivity
    value_impact: float # 0–1 expected value impact

    priority_score: float = field(init=False, default=0.0)
    severity: str = ""

    def __post_init__(self) -> None:
        self.priority_score = (
            self.gap_score * 0.35
            + self.leverage * 0.30
            + self.urgency * 0.20
            + self.value_impact * 0.15
        )


@dataclass
class ClientIntelligenceReport:
    """Full analysis output for a single client / survey run."""
    client_id: Optional[str]
    category_scores: List[CategoryScore]
    gap_results: List[GapResult]
    action_items: List[ActionItem]
    overall_trust_stage: str
    overall_weighted_score: float
    summary: Dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _classify_severity(gap_score: float) -> str:
    for threshold, label in GAP_SEVERITY_BANDS:
        if gap_score <= threshold:
            return label
    return "critical"


def _trust_penalty_modifier(stage: str) -> float:
    """Return gap penalty modifier based on RTQL stage."""
    certified_or_higher = {
        TrustStage.CERTIFIED,
        TrustStage.RESEARCH_GRADE,
        TrustStage.FIRST_PRINCIPLES_CANDIDATE,
        TrustStage.AXIOM_CANDIDATE,
    }
    if stage in certified_or_higher:
        return 1.00
    if stage == TrustStage.CERTIFICATION_GAP:
        return 1.10
    # Below qualified (noise, weak_signal, echo_signal, qualified handled below)
    if stage == TrustStage.QUALIFIED:
        return 1.00
    return 1.25  # noise / weak_signal / echo_signal


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class ClientIntelligenceEngine:
    """
    Scores 15 intelligence categories for a client, integrates RTQL trust
    adjustments, identifies gaps, and produces prioritised action items.
    """

    def __init__(self, rtql_classifier: Optional[RTQLClassifier] = None) -> None:
        self._rtql = rtql_classifier or RTQLClassifier()

    # ------------------------------------------------------------------
    # score_category
    # ------------------------------------------------------------------
    def score_category(
        self,
        category_key: str,
        inputs: Dict[str, float],
        rtql_stages: Optional[Dict[str, str]] = None,
    ) -> CategoryScore:
        """
        Score a single category.

        Parameters
        ----------
        category_key:
            One of the 15 category keys defined in CATEGORY_WEIGHTS.
        inputs:
            Dict with keys: variable_strength, evidence_quality,
            execution_maturity, consistency, strategic_fit (each 0–100).
            Optionally includes sub-variable scores keyed by the sub-variable
            name (also 0–100).
        rtql_stages:
            Optional mapping of sub-variable → trust stage string.
            When provided, individual sub-variable scores are trust-adjusted
            before aggregating into variable_strength.
        """
        if category_key not in CATEGORY_WEIGHTS:
            raise ValueError(f"Unknown category key: '{category_key}'")

        sub_var_keys = CATEGORY_SUB_VARIABLES[category_key]

        # Collect sub-variable scores (default 50 = neutral if not provided)
        sub_scores: Dict[str, float] = {}
        for sv in sub_var_keys:
            raw = float(inputs.get(sv, 50.0))
            if rtql_stages and sv in rtql_stages:
                multiplier = self._rtql.get_trust_multiplier(rtql_stages[sv])
                raw = raw * multiplier
            sub_scores[sv] = raw

        # Derive variable_strength from sub-variables if not explicitly given
        if "variable_strength" not in inputs and sub_scores:
            variable_strength = sum(sub_scores.values()) / len(sub_scores)
        else:
            variable_strength = float(inputs.get("variable_strength", 50.0))

        evidence_quality = float(inputs.get("evidence_quality", 50.0))
        execution_maturity = float(inputs.get("execution_maturity", 50.0))
        consistency = float(inputs.get("consistency", 50.0))
        strategic_fit = float(inputs.get("strategic_fit", 50.0))

        # Determine category-level trust multiplier
        # Use the mean of sub-variable stage multipliers when available
        if rtql_stages:
            stage_multipliers = [
                TRUST_MULTIPLIERS.get(rtql_stages[sv], 1.0)
                for sv in sub_var_keys
                if sv in rtql_stages
            ]
            trust_multiplier = (
                sum(stage_multipliers) / len(stage_multipliers)
                if stage_multipliers
                else 1.0
            )
        else:
            trust_multiplier = 1.0

        cs = CategoryScore(
            category_key=category_key,
            category_label=CATEGORY_LABELS[category_key],
            weight=CATEGORY_WEIGHTS[category_key],
            variable_strength=variable_strength,
            evidence_quality=evidence_quality,
            execution_maturity=execution_maturity,
            consistency=consistency,
            strategic_fit=strategic_fit,
            trust_multiplier=trust_multiplier,
            sub_variable_scores=sub_scores,
        )
        return cs

    # ------------------------------------------------------------------
    # analyze_gaps
    # ------------------------------------------------------------------
    def analyze_gaps(
        self,
        scores: List[CategoryScore],
        targets: Dict[str, float],
        rtql_stage: str = TrustStage.QUALIFIED,
    ) -> List[GapResult]:
        """
        Compute gap results for every scored category.

        Parameters
        ----------
        scores:
            Output from score_category (one per category).
        targets:
            Mapping of category_key → target trust-adjusted score (0–100).
        rtql_stage:
            Overall RTQL stage used to compute the trust penalty modifier.
        """
        penalty = _trust_penalty_modifier(rtql_stage)
        results: List[GapResult] = []

        for cs in scores:
            target = targets.get(cs.category_key, 100.0)
            # Strategic importance derived from category weight (normalised to 0–1)
            strategic_importance = cs.weight / max(CATEGORY_WEIGHTS.values())

            gr = GapResult(
                category_key=cs.category_key,
                category_label=cs.category_label,
                actual=cs.trust_adjusted_score,
                target=target,
                strategic_importance=strategic_importance,
                trust_penalty_modifier=penalty,
            )
            results.append(gr)

        # Sort by gap_score descending
        results.sort(key=lambda r: r.gap_score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # prioritize_actions
    # ------------------------------------------------------------------
    def prioritize_actions(self, gaps: List[GapResult]) -> List[ActionItem]:
        """
        Convert gap results into prioritised action items.

        Leverage, urgency, and value_impact are heuristically derived from
        gap severity and the category's strategic importance.
        """
        severity_leverage = {
            "minor": 0.25,
            "moderate": 0.50,
            "major": 0.75,
            "critical": 0.95,
        }
        severity_urgency = {
            "minor": 0.20,
            "moderate": 0.45,
            "major": 0.70,
            "critical": 0.90,
        }

        action_templates = {
            "minor": "Monitor {label}: gap is within acceptable range but watch for drift.",
            "moderate": "Improve {label}: address identified weaknesses with targeted initiatives.",
            "major": "Prioritise {label}: significant gap requires dedicated resource allocation.",
            "critical": "Critical intervention needed for {label}: immediate action required to prevent value erosion.",
        }

        items: List[ActionItem] = []
        for gap in gaps:
            if gap.gap_score <= 0:
                continue
            leverage = severity_leverage.get(gap.severity, 0.5)
            urgency = severity_urgency.get(gap.severity, 0.5)
            value_impact = min(1.0, gap.strategic_importance * 1.5)

            description = action_templates[gap.severity].format(
                label=gap.category_label
            )

            ai = ActionItem(
                category_key=gap.category_key,
                category_label=gap.category_label,
                description=description,
                gap_score=gap.gap_score,
                leverage=leverage,
                urgency=urgency,
                value_impact=value_impact,
                severity=gap.severity,
            )
            items.append(ai)

        # Sort by priority_score descending
        items.sort(key=lambda a: a.priority_score, reverse=True)
        return items

    # ------------------------------------------------------------------
    # full_analysis
    # ------------------------------------------------------------------
    def full_analysis(self, survey_data: Dict) -> ClientIntelligenceReport:
        """
        Run a complete analysis from raw survey data.

        Expected survey_data schema
        ---------------------------
        {
            "client_id": "optional string",
            "rtql_input": {<InputRecord fields>},          # optional
            "category_inputs": {
                "<category_key>": {
                    "variable_strength": float,  # 0-100
                    "evidence_quality": float,
                    "execution_maturity": float,
                    "consistency": float,
                    "strategic_fit": float,
                    "<sub_variable>": float,     # 0-100, optional
                    ...
                },
                ...
            },
            "targets": {"<category_key>": float, ...},    # optional, defaults to 80
            "rtql_stages": {"<sub_variable>": "<stage>"}  # optional per-subvar overrides
        }
        """
        client_id = survey_data.get("client_id")

        # --- Derive overall RTQL stage ---
        overall_stage = TrustStage.QUALIFIED  # default
        rtql_input_data = survey_data.get("rtql_input")
        if rtql_input_data:
            try:
                rtql_record = InputRecord(**rtql_input_data)
                overall_stage = self._rtql.classify(rtql_record)
            except (TypeError, ValueError):
                overall_stage = TrustStage.WEAK_SIGNAL

        overall_multiplier = self._rtql.get_trust_multiplier(overall_stage)
        rtql_stages = survey_data.get("rtql_stages", {})
        category_inputs: Dict[str, Dict] = survey_data.get("category_inputs", {})
        targets: Dict[str, float] = survey_data.get("targets", {})

        # --- Score all 15 categories ---
        category_scores: List[CategoryScore] = []
        for cat_key in CATEGORY_WEIGHTS:
            inputs = category_inputs.get(cat_key, {})
            cs = self.score_category(
                category_key=cat_key,
                inputs=inputs,
                rtql_stages=rtql_stages if rtql_stages else None,
            )
            # Apply overall trust multiplier if no per-subvar stages given
            if not rtql_stages:
                cs.trust_multiplier = overall_multiplier
                cs.trust_adjusted_score = cs.raw_score * overall_multiplier
            category_scores.append(cs)

        # --- Gap analysis ---
        # Default target = 80 for all categories
        default_targets = {k: targets.get(k, 80.0) for k in CATEGORY_WEIGHTS}
        gap_results = self.analyze_gaps(
            scores=category_scores,
            targets=default_targets,
            rtql_stage=overall_stage,
        )

        # --- Action prioritisation ---
        action_items = self.prioritize_actions(gap_results)

        # --- Overall weighted score ---
        overall_weighted_score = sum(
            cs.trust_adjusted_score * cs.weight for cs in category_scores
        )

        # --- Summary ---
        summary: Dict[str, object] = {
            "overall_trust_stage": overall_stage,
            "overall_trust_multiplier": overall_multiplier,
            "overall_weighted_score": round(overall_weighted_score, 2),
            "critical_gaps": [
                g.category_label for g in gap_results if g.severity == "critical"
            ],
            "major_gaps": [
                g.category_label for g in gap_results if g.severity == "major"
            ],
            "top_actions": [a.description for a in action_items[:3]],
        }

        return ClientIntelligenceReport(
            client_id=client_id,
            category_scores=category_scores,
            gap_results=gap_results,
            action_items=action_items,
            overall_trust_stage=overall_stage,
            overall_weighted_score=overall_weighted_score,
            summary=summary,
        )
