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


# ── AI Router HTTP wrapper (POST /v1/ai/invoke) ─────────────────────────────


class AIInvokeRequest(BaseModel):
    """POST /v1/ai/invoke — HTTP surface over engine.ai_router.invoke.

    Lets non-Python engines (or engines that can't import decision-engine
    directly — e.g. sales-os, HME) route LLM calls through the canonical
    chokepoint. CRIT-003 + CRIT-007 enforcement happens server-side.
    """
    prompt: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1, max_length=32)
    model: str = Field(..., min_length=1, max_length=128)
    prompt_version: str = Field(..., min_length=1, max_length=128)
    schema_version: str = Field(..., min_length=1, max_length=128)
    caller_engine: str = Field(..., min_length=1, max_length=64)
    caller_function: str = Field(..., min_length=1, max_length=128)
    max_tokens: int = Field(default=1024, ge=1, le=200000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    fallback_chain: Optional[list[str]] = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    audit_metadata: Optional[dict] = None


# ── Codification sweep + approval ───────────────────────────────────────────


class SweepRunRequest(BaseModel):
    """POST /v1/codification/sweep — run analyzer + readiness + open proposals."""
    min_volume: int = Field(default=50, ge=1)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    audit_db_path: Optional[str] = None
    proposals_db_path: Optional[str] = None
    open_proposals: bool = True
    why: str = Field(default="scheduled codification sweep")
    # v0.6 — opt-in LLM proposer + simulator. Defaults None → resolved
    # from CODIFICATION_PROPOSER_ENABLED env (default off).
    proposer_enabled: Optional[bool] = None
    proposer_top_n: int = Field(default=5, ge=0, le=50)


class ModuleProposeRequest(BaseModel):
    """POST /v1/codification/propose/{proposal_id} — draft a Python module."""
    provider: str = Field(default="anthropic", min_length=1, max_length=32)
    model: str = Field(default="claude-3-5-sonnet", min_length=1, max_length=128)
    evidence_ids: Optional[list[str]] = None       # override stored evidence
    certificate_id: Optional[str] = None           # bind a signed cert
    decision_class: str = Field(default="new-module", min_length=1)


class ModuleSimulateRequest(BaseModel):
    """POST /v1/codification/simulate/{proposal_id} — replay a module proposal."""
    module_proposal_id: str = Field(..., min_length=1)
    evidence_decision_ids: list[str] = Field(default_factory=list)
    audit_db_path: Optional[str] = None
    divergence_ceiling: float = Field(default=0.05, ge=0.0, le=1.0)


class ProposalApproveAndCertifyRequest(BaseModel):
    """POST /v1/proposals/{id}/approve-and-certify — auth-gated approval +
    HMAC-signed CodificationCertificate."""
    approver_user_id: str = Field(..., min_length=1)
    approval_why: str = Field(..., min_length=20)   # always-record-WHY
    new_status: str = Field(..., min_length=1)      # approved_ship | approved_fallback
    decision_class: str = Field(..., min_length=1)  # new-module | tuning | doctrine-touching
    evidence_decision_ids: list[str] = Field(default_factory=list)
    proposed_spec: str = Field(..., min_length=1)
    prompt_version: str = Field(..., min_length=1)
    schema_version: str = Field(..., min_length=1)
    additional_signers: list[str] = Field(default_factory=list)
    shipped_pr_url: Optional[str] = None


# ── OVS-Calibration ─────────────────────────────────────────────────────────


class OutcomeSourceCreateRequest(BaseModel):
    """POST /v1/calibration/sources — register a new outcome source.

    Note: the `schema_def` field carries the source's payload schema; we
    avoid `schema` to dodge Pydantic's BaseModel.schema() name collision.
    """
    name: str = Field(..., min_length=1)
    kind: Literal["revenue", "conversion", "operational", "satisfaction", "external"]
    entity: str = Field(..., min_length=1)
    ingestion_contract: Literal["pubsub", "webhook", "polling"]
    schema_def: dict = Field(default_factory=dict, alias="schema")
    owner: str = Field(..., min_length=1)
    health_status: Literal["healthy", "degraded", "offline", "unknown"] = "unknown"
    decision_class_metric_map: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class DecisionProjectionPayload(BaseModel):
    metric: str = Field(..., min_length=1)
    expected_value: float
    horizon_days: int = 0
    confidence: float = 0.0


class DecisionCertificatePayload(BaseModel):
    decision_certificate_id: str = Field(..., min_length=1)
    decision_class: str = Field(..., min_length=1)
    projection: DecisionProjectionPayload
    issued_at: str = ""


class OutcomeEventPayload(BaseModel):
    id: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    observed_value: float
    observed_at: str = ""
    source: str = ""
    expected_value: Optional[float] = None


class ComputeVarianceRequest(BaseModel):
    """POST /v1/calibration/compute-variance — compute variance for one pair."""
    decision_certificate: DecisionCertificatePayload
    outcome_event: OutcomeEventPayload
    metric_kind_override: Optional[Literal["proportional", "absolute"]] = None
    neutral_band_pct: float = Field(default=0.10, ge=0.0, le=1.0)


class AttributeRequest(BaseModel):
    """POST /v1/calibration/attribute — attribute one (decision, outcome)."""
    decision_certificate: DecisionCertificatePayload
    outcome_event: OutcomeEventPayload
    decision_entity: str = ""
    horizon_days: Optional[int] = None
    persist: bool = True


class CalibrationRevisionCreateRequest(BaseModel):
    """POST /v1/calibration/revisions — sign + persist a calibration revision."""
    dimension: str = Field(..., min_length=1)
    before_value: float
    after_value: float
    evidence_window_start: str = Field(..., min_length=1)
    evidence_window_end: str = Field(..., min_length=1)
    evidence_outcome_ids: list[str] = Field(default_factory=list)
    computation_version: str = Field(..., min_length=1)
    signed_by: str = Field(..., min_length=1)
    reasoning: str = Field(..., min_length=20)
    # Authority-gate inputs
    previous_computation_version: Optional[str] = None
    is_new_dimension: bool = False
    is_removal: bool = False
    additional_signers: list[str] = Field(default_factory=list)
    bypass_authority: bool = False  # for explicit dual-signed admin paths


# ── Penrose Falsification Scoreboard v0.6 ───────────────────────────────────


class NetworkValueRecordRequest(BaseModel):
    """POST /v1/penrose/network-value/record — PPEME inbox for BFT state.

    Body validation enforced; CRIT-010 canonical-9 check happens in the
    emitter and surfaces as HTTP 422 when the state vector keys differ.

    penrose_signal: weakens
    penrose_dimension: network_value
    """
    participant_id: str = Field(..., min_length=1, max_length=128)
    state_vector: dict = Field(..., description="Canonical 9-var BFT state")
    timestamp: Optional[str] = None  # ISO-8601; defaults to now() if omitted
    source: str = Field(default="ppeme", min_length=1, max_length=64)


# ── OVS-Calibration v0.6 — causal-chain + counterfactual + adapters ─────────


class CausalChainHopPayload(BaseModel):
    """One hop in a pre-walked causal chain (terminal not included)."""
    decision_certificate_id: str = Field(..., min_length=1)
    system: str = ""
    issued_at: str = ""
    projection_metric: str = ""


class CausalChainWalkRequest(BaseModel):
    """POST /v1/calibration/causal-chain/walk — walk + return chain links.

    Either `chain_links` (pre-walked by caller) OR `resolver_decisions`
    (caller-supplied lookup table keyed by decision_id) must be set.
    `resolver_decisions` values follow the `decision_resolver` contract
    documented on `attribute_causal_chain` — each entry carries
    `parent_certificate_id`, `evidence_certificate_ids`, `system`, etc.
    """
    decision_certificate: DecisionCertificatePayload
    outcome_event: OutcomeEventPayload
    chain_links: Optional[list[CausalChainHopPayload]] = None
    resolver_decisions: Optional[dict[str, dict]] = None
    persist: bool = False


class CounterfactualScoreRequest(BaseModel):
    """POST /v1/calibration/counterfactual/score — score one counterfactual.

    Returns the score (None when not observable) and optionally persists.
    """
    rejected_decision_id: str = Field(..., min_length=1)
    observed_alternative_outcome_ids: list[str] = Field(..., min_length=1)
    kind: Literal["direct", "comparative", "temporal"]
    rejected_projection_value: Optional[float] = None
    observed_alternative_value: Optional[float] = None
    alternative_chosen_id: Optional[str] = None
    evidence_metadata: dict = Field(default_factory=dict)
    reasoning: str = Field(default="")
    persist: bool = False
    scored_by: str = Field(default="system")
