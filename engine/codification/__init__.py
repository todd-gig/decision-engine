"""codification — Claude→Python flywheel as deployable engine.

Per specs/codification_engine_v0.md. v0 sub-package surface:
  - open_proposal(...): create a codification proposal in the queue
  - get_proposal(id): read one
  - list_proposals(status): queue view
  - approve_proposal(...): write approval decision (human-only)
"""
from __future__ import annotations

from .queue import (
    CodificationProposal,
    ProposalStatus,
    SimulationResult,
    approve_proposal,
    get_proposal,
    list_proposals,
    open_proposal,
)

__all__ = [
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
]


def __getattr__(name: str):
    """Lazy-load analyzer to avoid circular import (analyzer needs queue first)."""
    if name in {"analyze", "open_candidates_as_proposals", "Candidate"}:
        from . import analyzer
        return getattr(analyzer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
