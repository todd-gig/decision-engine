"""
Decision Engine Data Models

Canonical data structures for:
- Decision objects (22-field normalized contract)
- RTQL input records (7-dimension trust scoring)
- Value assessments (8 positive + 4 penalty dimensions)
- Trust assessments (7 trust inputs → tier)
- Certificates (QC, VC, TC, EC chain)
- Execution packets
- Audit records
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import uuid


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class DecisionClass(Enum):
    D0_INFORMATIONAL = "D0"
    D1_REVERSIBLE_TACTICAL = "D1"
    D2_OPERATIONAL = "D2"
    D3_FINANCIAL = "D3"
    D4_STRATEGIC = "D4"
    D5_LEGAL_ETHICAL = "D5"
    D6_IRREVERSIBLE_HIGH_BLAST = "D6"


class ReversibilityTag(Enum):
    R1_EASILY_REVERSIBLE = "R1"
    R2_MODERATELY_REVERSIBLE = "R2"
    R3_COSTLY_TO_REVERSE = "R3"
    R4_EFFECTIVELY_IRREVERSIBLE = "R4"


class TimeHorizon(Enum):
    IMMEDIATE = "immediate"       # 0-7 days
    NEAR_TERM = "near_term"       # 8-30 days
    MID_TERM = "mid_term"         # 31-180 days
    LONG_TERM = "long_term"       # 181+ days


class TrustTier(Enum):
    T0_UNQUALIFIED = "T0"
    T1_OBSERVED = "T1"
    T2_QUALIFIED = "T2"
    T3_CERTIFIED = "T3"
    T4_DELEGATED = "T4"


class RTQLStage(Enum):
    NOISE = "noise"
    WEAK_SIGNAL = "weak_signal"
    ECHO_SIGNAL = "echo_signal"
    QUALIFIED = "qualified"
    CERTIFICATION_GAP = "certification_gap"
    CERTIFIED = "certified"
    RESEARCH_GRADE = "research_grade"
    FIRST_PRINCIPLES_CANDIDATE = "first_principles_candidate"
    AXIOM_CANDIDATE = "axiom_candidate"


class CertificateType(Enum):
    QC = "qualified_context"
    VC = "value_confirmed"
    TC = "trust_certified"
    EC = "execution_cleared"


class CertificateStatus(Enum):
    ISSUED = "issued"
    DENIED = "denied"
    PENDING = "pending"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ExecutionVerdict(Enum):
    AUTO_EXECUTE = "auto_execute"
    ESCALATE_TIER_1 = "escalate_tier_1"
    ESCALATE_TIER_2 = "escalate_tier_2"
    ESCALATE_TIER_3 = "escalate_tier_3"
    BLOCK = "block"
    NEEDS_DATA = "needs_data"
    INFORMATION_ONLY = "information_only"


class WriteTarget(Enum):
    QUARANTINE = "quarantine"
    STAGING = "staging"
    CANDIDATE_REGISTRY = "candidate_registry"
    OPERATIONAL_REGISTRY = "operational_registry"
    INSIGHT_REGISTRY = "insight_registry"
    PRINCIPLES_REGISTRY = "principles_registry"
    AXIOM_REVIEW_QUEUE = "axiom_review_queue"


# ─────────────────────────────────────────────
# VALUE ASSESSMENT
# ─────────────────────────────────────────────

@dataclass
class ValueScores:
    """8 positive + 4 penalty dimensions, each 0-5."""
    # Positive dimensions
    revenue_impact: int = 0
    cost_efficiency: int = 0
    time_leverage: int = 0
    strategic_alignment: int = 0
    customer_human_benefit: int = 0
    knowledge_asset_creation: int = 0
    compounding_potential: int = 0
    reversibility: int = 0
    # Penalty dimensions
    downside_risk: int = 0
    execution_drag: int = 0
    uncertainty: int = 0
    ethical_misalignment: int = 0

    def gross_value(self) -> int:
        return (
            self.revenue_impact + self.cost_efficiency +
            self.time_leverage + self.strategic_alignment +
            self.customer_human_benefit + self.knowledge_asset_creation +
            self.compounding_potential + self.reversibility
        )

    def penalty(self) -> int:
        return (
            self.downside_risk + self.execution_drag +
            self.uncertainty + self.ethical_misalignment
        )

    def net_value(self) -> int:
        return self.gross_value() - self.penalty()

    def value_classification(self) -> str:
        nv = self.net_value()
        if nv >= 20:
            return "strong_candidate"
        elif nv >= 12:
            return "conditional_candidate"
        elif nv >= 0:
            return "weak_candidate"
        else:
            return "block"

    def validate(self) -> list[str]:
        errors = []
        for fname in [
            'revenue_impact', 'cost_efficiency', 'time_leverage',
            'strategic_alignment', 'customer_human_benefit',
            'knowledge_asset_creation', 'compounding_potential',
            'reversibility', 'downside_risk', 'execution_drag',
            'uncertainty', 'ethical_misalignment'
        ]:
            v = getattr(self, fname)
            if not (0 <= v <= 5):
                errors.append(f"{fname} must be 0-5, got {v}")
        return errors


# ─────────────────────────────────────────────
# TRUST ASSESSMENT
# ─────────────────────────────────────────────

@dataclass
class TrustScores:
    """7 trust inputs, each 0-5."""
    evidence_quality: int = 0
    logic_integrity: int = 0
    outcome_history: int = 0
    context_fit: int = 0
    stakeholder_clarity: int = 0
    risk_containment: int = 0
    auditability: int = 0

    def total(self) -> int:
        return (
            self.evidence_quality + self.logic_integrity +
            self.outcome_history + self.context_fit +
            self.stakeholder_clarity + self.risk_containment +
            self.auditability
        )

    def average(self) -> float:
        return self.total() / 7.0

    def validate(self) -> list[str]:
        errors = []
        for fname in [
            'evidence_quality', 'logic_integrity', 'outcome_history',
            'context_fit', 'stakeholder_clarity', 'risk_containment',
            'auditability'
        ]:
            v = getattr(self, fname)
            if not (0 <= v <= 5):
                errors.append(f"{fname} must be 0-5, got {v}")
        return errors


# ─────────────────────────────────────────────
# RTQL INPUT RECORD
# ─────────────────────────────────────────────

@dataclass
class RTQLScores:
    """7-dimension RTQL scoring. Uses smooth number set: 0,1,2,3,4,5,6,8,10,12."""
    source_integrity: int = 0
    exposure_count: int = 0
    independence: int = 0
    explainability: int = 0
    replicability: int = 0
    adversarial_robustness: int = 0
    novelty_yield: int = 0

    ALLOWED_SCORES = {0, 1, 2, 3, 4, 5, 6, 8, 10, 12}

    def validate(self) -> list[str]:
        errors = []
        for fname in [
            'source_integrity', 'exposure_count', 'independence',
            'explainability', 'replicability', 'adversarial_robustness',
            'novelty_yield'
        ]:
            v = getattr(self, fname)
            if v not in self.ALLOWED_SCORES:
                errors.append(
                    f"{fname} must be in {sorted(self.ALLOWED_SCORES)}, got {v}"
                )
        return errors


@dataclass
class CausalChecks:
    reveals_causal_mechanism: bool = False
    is_irreducible: bool = False
    survives_authority_removal: bool = False
    survives_context_shift: bool = False


@dataclass
class RTQLInput:
    claim: str = ""
    source: str = ""
    is_identifiable: bool = False
    has_provenance: bool = False
    scores: RTQLScores = field(default_factory=RTQLScores)
    causal_checks: CausalChecks = field(default_factory=CausalChecks)


# ─────────────────────────────────────────────
# RTQL CLASSIFICATION RESULT
# ─────────────────────────────────────────────

@dataclass
class RTQLResult:
    stage: RTQLStage = RTQLStage.NOISE
    trust_multiplier: float = 0.0
    write_target: WriteTarget = WriteTarget.QUARANTINE
    research_actions: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    passed: bool = False


# ─────────────────────────────────────────────
# ALIGNMENT CHECK
# ─────────────────────────────────────────────

@dataclass
class AlignmentScores:
    """Doctrine, ethos, and first-principles alignment. Each 0.0-1.0."""
    doctrine_alignment: float = 0.0
    ethos_alignment: float = 0.0
    first_principles_alignment: float = 0.0
    anti_pattern_flags: list[str] = field(default_factory=list)
    applied_principles: list[str] = field(default_factory=list)

    def composite(self) -> float:
        return (
            self.doctrine_alignment * 0.4 +
            self.ethos_alignment * 0.3 +
            self.first_principles_alignment * 0.3
        )

    def has_violations(self) -> bool:
        return len(self.anti_pattern_flags) > 0 or any(
            v < 0.3 for v in [
                self.doctrine_alignment,
                self.ethos_alignment,
                self.first_principles_alignment
            ]
        )


# ─────────────────────────────────────────────
# CERTIFICATE
# ─────────────────────────────────────────────

@dataclass
class Certificate:
    certificate_id: str = ""
    decision_id: str = ""
    cert_type: CertificateType = CertificateType.QC
    status: CertificateStatus = CertificateStatus.PENDING
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    evidence_basis: list[str] = field(default_factory=list)
    denial_reasons: list[str] = field(default_factory=list)
    scores_snapshot: dict = field(default_factory=dict)

    def is_valid(self) -> bool:
        if self.status != CertificateStatus.ISSUED:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True


@dataclass
class CertificateChain:
    """QC → VC → TC → EC. No EC without prior QC, VC, and TC."""
    qc: Optional[Certificate] = None
    vc: Optional[Certificate] = None
    tc: Optional[Certificate] = None
    ec: Optional[Certificate] = None

    def chain_complete(self) -> bool:
        return all(
            c is not None and c.is_valid()
            for c in [self.qc, self.vc, self.tc, self.ec]
        )

    def highest_valid(self) -> Optional[CertificateType]:
        for cert, ct in [
            (self.ec, CertificateType.EC),
            (self.tc, CertificateType.TC),
            (self.vc, CertificateType.VC),
            (self.qc, CertificateType.QC),
        ]:
            if cert and cert.is_valid():
                return ct
        return None


# ─────────────────────────────────────────────
# DECISION OBJECT (22-field normalized contract)
# ─────────────────────────────────────────────

@dataclass
class DecisionObject:
    # Identity
    decision_id: str = field(default_factory=lambda: f"DEC-{uuid.uuid4().hex[:8].upper()}")
    title: str = ""
    decision_class: DecisionClass = DecisionClass.D1_REVERSIBLE_TACTICAL
    owner: str = ""
    time_horizon: TimeHorizon = TimeHorizon.IMMEDIATE
    reversibility: ReversibilityTag = ReversibilityTag.R1_EASILY_REVERSIBLE
    # Intent
    problem_statement: str = ""
    requested_action: str = ""
    context_summary: str = ""
    # Stakeholders & Constraints
    stakeholders: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    # Scoring inputs (human-provided)
    value_scores: ValueScores = field(default_factory=ValueScores)
    trust_scores: TrustScores = field(default_factory=TrustScores)
    alignment_scores: AlignmentScores = field(default_factory=AlignmentScores)
    # RTQL pre-filter
    rtql_input: Optional[RTQLInput] = None
    # Evidence
    evidence_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    # Execution
    required_approvals: list[str] = field(default_factory=list)
    execution_plan: str = ""
    monitoring_metric: str = ""
    rollback_trigger: str = ""
    review_date: Optional[str] = None
    # State machine & authority (from decision_service.py / engine.yaml)
    current_state: str = "draft"
    actor_role: str = "AI_Domain_Agent"
    has_missing_data: bool = False
    ethical_conflict: bool = False
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty = valid."""
        errors = []
        if not self.title:
            errors.append("title is required")
        if not self.owner:
            errors.append("owner is required")
        if not self.problem_statement:
            errors.append("problem_statement is required")
        if not self.requested_action:
            errors.append("requested_action is required")
        if not self.evidence_refs:
            errors.append("at least one evidence_ref is required")
        errors.extend(self.value_scores.validate())
        errors.extend(self.trust_scores.validate())
        return errors


# ─────────────────────────────────────────────
# EXECUTION PACKET
# ─────────────────────────────────────────────

@dataclass
class ExecutionPacket:
    decision_id: str = ""
    verdict: ExecutionVerdict = ExecutionVerdict.BLOCK
    action_steps: list[str] = field(default_factory=list)
    owner: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    dependencies: list[str] = field(default_factory=list)
    monitoring_metric: str = ""
    rollback_trigger: str = ""
    review_date: str = ""
    escalation_tier: Optional[int] = None
    escalation_sla: str = ""
    escalation_recipients: list[str] = field(default_factory=list)
    gate_results: dict = field(default_factory=dict)
    blocking_gates: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# AUDIT RECORD
# ─────────────────────────────────────────────

@dataclass
class AuditRecord:
    audit_id: str = field(default_factory=lambda: f"AUD-{uuid.uuid4().hex[:8].upper()}")
    decision_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    pipeline_stage: str = ""
    action_taken: str = ""
    inputs_snapshot: dict = field(default_factory=dict)
    outputs_snapshot: dict = field(default_factory=dict)
    certificate_chain_state: dict = field(default_factory=dict)
    rtql_stage: str = ""
    value_net_score: int = 0
    trust_tier: str = ""
    execution_verdict: str = ""
    notes: str = ""


# ─────────────────────────────────────────────
# PIPELINE RESULT (final output)
# ─────────────────────────────────────────────

@dataclass
class PipelineResult:
    decision_id: str = ""
    success: bool = False
    validation_errors: list[str] = field(default_factory=list)
    rtql_result: Optional[RTQLResult] = None
    value_classification: str = ""
    net_value_score: int = 0
    trust_tier: TrustTier = TrustTier.T0_UNQUALIFIED
    trust_total: int = 0
    alignment_composite: float = 0.0
    alignment_violations: list[str] = field(default_factory=list)
    certificate_chain: Optional[CertificateChain] = None
    execution_packet: Optional[ExecutionPacket] = None
    audit_trail: list[AuditRecord] = field(default_factory=list)
    priority_score: float = 0.0
    executive_summary: str = ""
