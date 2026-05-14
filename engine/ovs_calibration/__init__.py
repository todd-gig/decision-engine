"""ovs_calibration — Outcome Variance & Calibration Engine v0.5.

Closes the Learning Loop (Framework 5.7) across entities. Outcomes flow IN
from every entity surface, get attributed to originating decisions, variance
is computed against the decision certificate's projection, and HMAC-signed
calibration revisions write back to Trust/Value/Authority weights.

This sub-package is INTENTIONALLY separate from `engine/ovs_engine.py` (the
unrelated OVS health-scoring engine). They share a name fragment for
historical reasons but have no runtime coupling.

v0.5 surface:
  - sources           — OutcomeSource registry CRUD
  - variance          — compute_variance(decision, outcome) -> VarianceResult
  - attribution       — three-stage attribution (direct + temporal+entity;
                        causal-chain stub returns [])
  - revisions         — HMAC-signed CalibrationRevision with DB + MD twin
  - authority         — outcome_weight() + check_calibration_authority()
  - codification_bridge — emit stable-pattern candidates to codification queue

Penrose-falsification instrument:
  This engine produces the per-quarter "OVS Variance" metric and the
  "Cascade Multiplier (observed)" metric from
  penrose_falsification_doctrine.md §Scoreboard items 4 + 5. Without closed-
  loop calibration, the "system gets smarter with use" doctrine is
  aspirational — every revision here is evidence that the loop is closing.

penrose_signal: weakens
penrose_dimension: variance | cascade
"""
from __future__ import annotations

from .sources import (
    OutcomeSource,
    register_source,
    get_source,
    list_sources,
    update_health,
)
from .variance import (
    DecisionCertificateLike,
    DecisionProjection,
    OutcomeEventLike,
    VarianceResult,
    MetricKind,
    compute_variance,
)
from .attribution import (
    AttributionLink,
    assign_layer,
    cascade_multiplier_for_layer,
    cascade_multiplier_for_systems,
    attribute_direct,
    attribute_temporal_entity,
    attribute_causal_chain,
    attribute,
    persist_link,
    list_links_for_decision,
    list_links_for_outcome,
)
from .revisions import (
    CalibrationRevision,
    write_revision,
    get_revision,
    list_revisions,
    verify_revision,
)
from .authority import (
    OutcomeEventForWeight,
    RequiresSignoff,
    outcome_weight,
    check_calibration_authority,
    OVERRIDE_WEIGHT,
    DEFAULT_WEIGHT,
    REQUIRED_DUAL_SIGNERS,
)
from .codification_bridge import (
    VarianceObservation,
    CodificationEmission,
    evaluate_stability,
    emit_candidate,
)

__all__ = [
    # sources
    "OutcomeSource",
    "register_source",
    "get_source",
    "list_sources",
    "update_health",
    # variance
    "DecisionCertificateLike",
    "DecisionProjection",
    "OutcomeEventLike",
    "VarianceResult",
    "MetricKind",
    "compute_variance",
    # attribution
    "AttributionLink",
    "assign_layer",
    "cascade_multiplier_for_layer",
    "cascade_multiplier_for_systems",
    "attribute_direct",
    "attribute_temporal_entity",
    "attribute_causal_chain",
    "attribute",
    "persist_link",
    "list_links_for_decision",
    "list_links_for_outcome",
    # revisions
    "CalibrationRevision",
    "write_revision",
    "get_revision",
    "list_revisions",
    "verify_revision",
    # authority
    "OutcomeEventForWeight",
    "RequiresSignoff",
    "outcome_weight",
    "check_calibration_authority",
    "OVERRIDE_WEIGHT",
    "DEFAULT_WEIGHT",
    "REQUIRED_DUAL_SIGNERS",
    # codification bridge
    "VarianceObservation",
    "CodificationEmission",
    "evaluate_stability",
    "emit_candidate",
]
