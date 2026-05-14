"""codification — Claude→Python flywheel as deployable engine.

Per specs/codification_engine_v0.md. v0.5 surface adds the readiness
scorer, governance certificates, sign-off routing, and a scheduled
sweep entrypoint that closes the flywheel.

v0   surface (still exported):
  - open_proposal(...) / get_proposal(id) / list_proposals(status)
  - approve_proposal(...) — flip queue status without minting a cert
  - analyze(...) / open_candidates_as_proposals(...)

v0.5 surface (NEW):
  - compute_readiness(candidate) → ReadinessScore
  - CodificationCertificate (HMAC-SHA256 + matching .md file)
  - persist_certificate / get_certificate / list_certificates_for_candidate
  - required_signers(decision_class) / is_authorized / has_quorum
  - approve_and_certify(...) — auth-gated approval that mints a cert
  - run_sweep(...) — analyzer + readiness + auto-open proposals

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

from .queue import (
    CodificationProposal,
    ProposalStatus,
    SimulationResult,
    approve_and_certify,
    approve_proposal,
    get_proposal,
    list_proposals,
    open_proposal,
)
from .readiness import (
    DOCTRINE_DEFAULTS,
    ReadinessCandidate,
    ReadinessScore,
    ReadinessThresholds,
    compute_readiness,
    load_thresholds,
)
from .certificate import (
    CodificationCertificate,
    MIN_REASONING_CHARS,
    get_certificate,
    list_certificates_for_candidate,
    persist_certificate,
)
from .signoff import (
    DECISION_CLASS_SIGNERS,
    FOUNDER_SIGNER,
    OWNER_SIGNER,
    has_quorum,
    is_authorized,
    required_signers,
)
from .sweep import (
    PROPOSER_ENABLED_ENV,
    SWEEP_PROMPT_VERSION,
    SWEEP_SCHEMA_VERSION,
    SweepReport,
    run_sweep,
)
from .proposer import (
    BannedImportError,
    ModuleProposal,
    PROPOSER_PROMPT_VERSION,
    PROPOSER_SCHEMA_VERSION,
    get_module_proposal,
    list_module_proposals_for_candidate,
    propose_python_module,
)
from .simulator import (
    CODIFIED_ENTRY_POINT,
    DOCTRINE_DIVERGENCE_CEILING,
    SimulatorCompileError,
    simulate_against_history,
)

__all__ = [
    # v0
    "CodificationProposal",
    "ProposalStatus",
    "SimulationResult",
    "open_proposal",
    "get_proposal",
    "list_proposals",
    "approve_proposal",
    "analyze",
    "open_candidates_as_proposals",
    "Candidate",
    # v0.5 readiness
    "ReadinessCandidate",
    "ReadinessScore",
    "ReadinessThresholds",
    "DOCTRINE_DEFAULTS",
    "compute_readiness",
    "load_thresholds",
    # v0.5 certificates
    "CodificationCertificate",
    "MIN_REASONING_CHARS",
    "persist_certificate",
    "get_certificate",
    "list_certificates_for_candidate",
    # v0.5 sign-off
    "FOUNDER_SIGNER",
    "OWNER_SIGNER",
    "DECISION_CLASS_SIGNERS",
    "required_signers",
    "is_authorized",
    "has_quorum",
    # v0.5 sweep
    "SweepReport",
    "SWEEP_PROMPT_VERSION",
    "SWEEP_SCHEMA_VERSION",
    "run_sweep",
    # v0.5 approval flow
    "approve_and_certify",
    # v0.6 proposer
    "BannedImportError",
    "ModuleProposal",
    "PROPOSER_PROMPT_VERSION",
    "PROPOSER_SCHEMA_VERSION",
    "PROPOSER_ENABLED_ENV",
    "propose_python_module",
    "get_module_proposal",
    "list_module_proposals_for_candidate",
    # v0.6 simulator
    "CODIFIED_ENTRY_POINT",
    "DOCTRINE_DIVERGENCE_CEILING",
    "SimulatorCompileError",
    "simulate_against_history",
]


def __getattr__(name: str):
    """Lazy-load analyzer to avoid circular import (analyzer needs queue first)."""
    if name in {"analyze", "open_candidates_as_proposals", "Candidate"}:
        from . import analyzer
        return getattr(analyzer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
