"""
API Schemas — Pydantic models for request/response serialization.

Bridges between the FastAPI HTTP layer and the dataclass-based engine models.
Supports both the full pipeline (rich DecisionObject) and a simplified
evaluation mode (flat dimension dicts) for quick integrations.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional

TrustTierLiteral = Literal["T0", "T1", "T2", "T3", "T4"]
DecisionClassLiteral = Literal["D0", "D1", "D2", "D3", "D4", "D5", "D6"]
ReversibilityLiteral = Literal["R1", "R2", "R3", "R4"]
TimeHorizonLiteral = Literal["immediate", "near_term", "mid_term", "long_term"]


# ── Full Pipeline Request ──


class ValueScoresInput(BaseModel):
    revenue_impact: int = 0
    cost_efficiency: int = 0
    time_leverage: int = 0
    strategic_alignment: int = 0
    customer_human_benefit: int = 0
    knowledge_asset_creation: int = 0
    compounding_potential: int = 0
    reversibility: int = 0
    downside_risk: int = 0
    execution_drag: int = 0
    uncertainty: int = 0
    ethical_misalignment: int = 0


class TrustScoresInput(BaseModel):
    evidence_quality: int = 0
    logic_integrity: int = 0
    outcome_history: int = 0
    context_fit: int = 0
    stakeholder_clarity: int = 0
    risk_containment: int = 0
    auditability: int = 0


class AlignmentScoresInput(BaseModel):
    doctrine_alignment: float = 0.0
    ethos_alignment: float = 0.0
    first_principles_alignment: float = 0.0
    anti_pattern_flags: list[str] = Field(default_factory=list)
    applied_principles: list[str] = Field(default_factory=list)


class RTQLScoresInput(BaseModel):
    source_integrity: int = 0
    exposure_count: int = 0
    independence: int = 0
    explainability: int = 0
    replicability: int = 0
    adversarial_robustness: int = 0
    novelty_yield: int = 0


class CausalChecksInput(BaseModel):
    reveals_causal_mechanism: bool = False
    is_irreducible: bool = False
    survives_authority_removal: bool = False
    survives_context_shift: bool = False


class RTQLInputPayload(BaseModel):
    claim: str = ""
    source: str = ""
    is_identifiable: bool = False
    has_provenance: bool = False
    scores: RTQLScoresInput = Field(default_factory=RTQLScoresInput)
    causal_checks: CausalChecksInput = Field(default_factory=CausalChecksInput)


class FullDecisionRequest(BaseModel):
    """Full pipeline request — maps to DecisionObject."""
    title: str
    decision_class: DecisionClassLiteral = "D1"
    owner: str = ""
    time_horizon: TimeHorizonLiteral = "immediate"
    reversibility: ReversibilityLiteral = "R1"
    problem_statement: str = ""
    requested_action: str = ""
    context_summary: str = ""
    stakeholders: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    value_scores: ValueScoresInput = Field(default_factory=ValueScoresInput)
    trust_scores: TrustScoresInput = Field(default_factory=TrustScoresInput)
    alignment_scores: AlignmentScoresInput = Field(default_factory=AlignmentScoresInput)
    rtql_input: Optional[RTQLInputPayload] = None
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    execution_plan: str = ""
    monitoring_metric: str = ""
    rollback_trigger: str = ""
    review_date: Optional[str] = None
    current_state: str = "draft"
    actor_role: str = "AI_Domain_Agent"
    has_missing_data: bool = False
    ethical_conflict: bool = False


# ── Simplified Evaluation Request (backward compat with execution-engine) ──


class SimpleDecisionInput(BaseModel):
    """Simplified flat evaluation — for quick API integrations."""
    decision_id: str
    title: str
    decision_class: DecisionClassLiteral
    current_state: str = "draft"
    actor_role: str = "AI_Domain_Agent"
    trust_tier: TrustTierLiteral = "T3"
    positive_dimensions: dict[str, float] = Field(default_factory=dict)
    penalty_dimensions: dict[str, float] = Field(default_factory=dict)
    trust_inputs: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    ethical_conflict: bool = False
    has_missing_data: bool = False
    reversibility: ReversibilityLiteral = "R1"


class SimpleEvaluationRequest(BaseModel):
    decision: SimpleDecisionInput


# ── State Transition ──


class TransitionRequest(BaseModel):
    current_state: str
    target_state: str


class TransitionResponse(BaseModel):
    allowed: bool
    current_state: str
    target_state: str
    required_certificates: list[str] = Field(default_factory=list)


# ── Outcome Recording ──


class OutcomeRequest(BaseModel):
    decision_id: str
    decision_class: str
    original_verdict: str
    expected_value: float
    expected_timeline_days: int
    expected_risk_level: str = "low"
    actual_value: float
    actual_timeline_days: int
    actual_risk_materialized: bool = False
    actual_risk_description: str = ""
    outcome_summary: str = ""
    lessons_learned: list[str] = Field(default_factory=list)
    recorded_by: str = ""


# ── Generic Response ──


class AuditEntry(BaseModel):
    stage: str
    detail: dict


class PipelineResponse(BaseModel):
    decision_id: str
    success: bool
    validation_errors: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    reason_code: str = ""
    value_classification: str = ""
    net_value_score: float = 0
    trust_tier: str = ""
    trust_total: int = 0
    alignment_composite: float = 0.0
    alignment_violations: list[str] = Field(default_factory=list)
    priority_score: float = 0.0
    next_state: str = ""
    certificate_status: dict = Field(default_factory=dict)
    executive_summary: str = ""
    audit_log: list[AuditEntry] = Field(default_factory=list)
    full_result: Optional[dict] = None


# ── Human Override + Codification ─────────────────────────────────────────────


class OverrideRecordRequest(BaseModel):
    """POST /v1/overrides — record one human override."""
    decision_id: Optional[str] = None
    decision_certificate_id: Optional[str] = None
    override_type: str = Field(..., min_length=1)
    overridden_by_user_id: str = Field(..., min_length=1)
    overridden_at: str = Field(..., min_length=1)  # ISO-8601
    source_engine: str = Field(..., min_length=1, max_length=64)
    surface: str = Field(..., min_length=1)
    original_action: str = Field(..., min_length=1)
    override_action: str = Field(..., min_length=1)
    user_reasoning: Optional[str] = None
    freeform_metadata: Optional[dict] = None


class ProposalSimSummary(BaseModel):
    n: int
    divergence_p50: float
    divergence_p90: float
    cost_savings_usd: Optional[float] = None
    latency_savings_ms: Optional[int] = None


class ProposalCreateRequest(BaseModel):
    """POST /v1/proposals — open a new codification proposal."""
    candidate_pv: str = Field(..., min_length=1)
    candidate_sv: str = Field(..., min_length=1)
    candidate_score: float = Field(..., ge=0.0, le=1.0)
    analyzer_run_at: str = Field(..., min_length=1)
    proposed_python: str = Field(..., min_length=1)
    proposed_tests: str = Field(..., min_length=1)
    why: str = Field(..., min_length=1)
    sim: ProposalSimSummary


class ProposalApproveRequest(BaseModel):
    """POST /v1/proposals/{id}/approve — record human decision."""
    approver_user_id: str = Field(..., min_length=1)
    approval_why: str = Field(..., min_length=1)
    new_status: str = Field(..., min_length=1)  # validated against enum in handler
    shipped_pr_url: Optional[str] = None


class AnalyzerRunRequest(BaseModel):
    """POST /v1/codification/analyze — trigger an analyzer run."""
    min_volume: int = Field(default=100, ge=1)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    open_top_n_as_proposals: int = Field(default=0, ge=0, le=50)
    audit_db_path: Optional[str] = None
    proposals_db_path: Optional[str] = None
    why: str = Field(default="scheduled analyzer run")
