"""
Executive Decision Engine — Unified Intelligence Package

Consolidates all decision processing subsystems into a single deployable artifact:

- Core Pipeline: Input validation → RTQL → Value → Trust → Authority → Certificates → 7-Gate → State Machine
- RTQL System: Recursive Trust Qualification Loop (classifier, filter, integration layer)
- Scoring: Raw scoring, weighted scoring, priority scoring, alignment checks
- Certificates: 4-certificate chain (QC → VC → TC → EC) with HMAC-signed trust certificates
- Authorization: 7-gate autonomous execution system with 3-tier escalation
- State Machine: 8-state decision lifecycle with action-based transitions
- Analytics: Gap analysis, value leakage detection, ROI engine, OVS engine, causal mapper
- Learning: Adaptive learning loop, variance tracking, institutional memory
- Exceptions: Structured exception classification, escalation, codification
- Governance: 30/60/90-day gate assessment with quantified thresholds
- Memory: Persistent MD-based memory with YAML frontmatter
- Intelligence: Claude API-powered learning agent for human context ingestion
"""

__version__ = "2.0.0"

# ── Core Pipeline ──
from .pipeline import process_decision
from .models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    TrustTier, RTQLStage, CertificateType, CertificateStatus,
    ExecutionVerdict, WriteTarget,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks, RTQLResult,
    Certificate, CertificateChain,
    ExecutionPacket, AuditRecord, PipelineResult,
)
from .config import EngineConfig, load_config

# ── Scoring ──
from .scoring import (
    calculate_trust_tier, trust_adjusted_value,
    check_alignment, calculate_priority_score,
)
from .weighted_scoring import compute_weighted_value, compute_weighted_trust

# ── Authorization ──
from .gates import run_7_gate_authorization
from .authority import authority_check
from .state_machine import (
    next_state_for_action, advance_state, can_transition,
    get_lifecycle_status,
)

# ── Certificates ──
from .certificates import (
    issue_qc, issue_vc, issue_tc, issue_ec,
    build_certificate_chain,
)

# ── RTQL ──
from .rtql_filter import classify_rtql, rtql_prefilter_passes
from .rtql_classifier import RTQLClassifier, InputRecord
from .rtql_integration_layer import RTQLIntegrationLayer, MutationRequest, MutationDecision

# ── Audit ──
from .audit import (
    AuditLogger, serialize_pipeline_result,
    result_to_json, generate_executive_summary,
)

# ── Analytics ──
from .gap_analysis import analyze_gaps, generate_action_items, calculate_gap
from .value_leakage import ValueLeakageDetector
from .roi_engine import ROIEngine, ROIInput, ImplementationCost
from .ovs_engine import OVSEngine, OVSResult
from .causal_mapper import CausalMapper, CausalLink, CausalChain

# ── Learning ──
from .adaptive_learning import AdaptiveLearningEngine, LearningValueIndex
from .learning_loop import (
    record_outcome, calculate_variance, LearningStore,
    LearningRecord, OutcomeRecord,
)

# ── Exceptions ──
from .exception_engine import ExceptionEngine

# ── Governance ──
from .governance_gates import GovernanceGateEngine, Gate1Inputs, Gate2Inputs, Gate3Inputs

# ── Memory & Trust (from decision-logic-pack) ──
from .memory_manager import MemoryManager, MemoryEntry
from .trust_certificates import (
    TrustCertificate, TrustLevel, CertificateAuthority,
    bootstrap_certificates,
)
from .decision_engine import (
    DecisionEngine, DecisionRecord, DecisionStatus,
    DecisionContext, Option, ActionExecutor,
)
from .learning_agent import LearningAgent, LearningEvent
