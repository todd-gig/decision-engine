"""Codification Engine bridge — emit stable-decision-class signals.

Per spec line 27 + line 194:
  > When a decision class accumulates >=50 attributed outcomes with variance
  > |v| <= 0.10 over the evidence window, emit a candidate to
  > engine.codification.queue.open_proposal() with source='ovs_calibration'.

This wires the two flywheels:
  - OVS-Calibration grades decisions (this engine)
  - Codification crystallizes the patterns it confirmed (Claude->Python promo)

WHY: without an automatic bridge, "stable pattern" signal stays in OVS where
no one reads it for codification candidacy. Emitting at the threshold makes
the Learning Loop closure observable in the codification queue.

penrose_signal: weakens
penrose_dimension: codification | variance
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional


# Doctrine thresholds (spec line 28 + §Open implementation sub-tasks).
DEFAULT_MIN_OUTCOMES = 50
DEFAULT_MAX_ABS_VARIANCE = 0.10


@dataclass
class VarianceObservation:
    """Minimal observation needed to evaluate the codification bridge."""
    outcome_event_id: str
    variance: float          # signed; we use |variance| against threshold
    observed_at: str = ""    # ISO-8601
    decision_certificate_id: str = ""


@dataclass
class CodificationEmission:
    """Result of an attempt to emit a codification candidate.

    Either `proposal_id` is set (we wrote a proposal) or `skipped_reason`
    explains why we didn't.
    """
    decision_class: str
    eligible: bool
    sample_size: int
    p50_variance: float
    p90_variance: float
    proposal_id: Optional[str] = None
    skipped_reason: Optional[str] = None
    emitted_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "decision_class": self.decision_class,
            "eligible": self.eligible,
            "sample_size": self.sample_size,
            "p50_variance": self.p50_variance,
            "p90_variance": self.p90_variance,
            "proposal_id": self.proposal_id,
            "skipped_reason": self.skipped_reason,
            "emitted_at": self.emitted_at,
        }


def evaluate_stability(
    observations: Iterable[VarianceObservation],
    min_outcomes: int = DEFAULT_MIN_OUTCOMES,
    max_abs_variance: float = DEFAULT_MAX_ABS_VARIANCE,
) -> tuple[bool, int, float, float]:
    """Return (eligible, sample_size, p50_abs, p90_abs).

    `eligible` is True iff:
      * sample_size >= min_outcomes
      * p90 of |variance| <= max_abs_variance
    p50/p90 are robust to single-row outliers; the spec phrases stability
    against the bulk of variance, not the mean.
    """
    abs_variances = [abs(o.variance) for o in observations]
    n = len(abs_variances)
    if n == 0:
        return (False, 0, 0.0, 0.0)
    sorted_abs = sorted(abs_variances)
    # p50 / p90 via nearest-rank to avoid scipy dependency
    p50 = sorted_abs[max(0, int(round(0.50 * (n - 1))))]
    p90 = sorted_abs[max(0, int(round(0.90 * (n - 1))))]
    eligible = (n >= min_outcomes) and (p90 <= max_abs_variance)
    return (eligible, n, round(p50, 4), round(p90, 4))


def emit_candidate(
    decision_class: str,
    observations: Iterable[VarianceObservation],
    *,
    proposed_python: str | None = None,
    proposed_tests: str | None = None,
    why: str = "",
    min_outcomes: int = DEFAULT_MIN_OUTCOMES,
    max_abs_variance: float = DEFAULT_MAX_ABS_VARIANCE,
    proposals_db_path: str | None = None,
) -> CodificationEmission:
    """Evaluate stability and, if eligible, open a codification proposal.

    Args:
        decision_class: the decision class string (e.g.,
            'pricing.dynamic.carmen-beach') used as the source identity for
            the candidate prompt/schema version.
        observations: the (decision, outcome) variance rows scoped to the
            evidence window.
        proposed_python / proposed_tests: codified candidate; v0.5 callers
            may pass placeholder stubs — the analyzer in
            engine.codification.analyzer is the canonical author, this bridge
            just opens the proposal at threshold.
        why: short rationale shown in the codification queue.
        proposals_db_path: override for tests.

    Returns: CodificationEmission with proposal_id set on success, or
    skipped_reason populated when the threshold is not met.
    """
    obs_list = list(observations)
    eligible, n, p50, p90 = evaluate_stability(
        obs_list,
        min_outcomes=min_outcomes,
        max_abs_variance=max_abs_variance,
    )
    if not eligible:
        reason = (
            f"sample_size={n} < min_outcomes={min_outcomes}"
            if n < min_outcomes
            else f"p90_abs_variance={p90} > max_abs_variance={max_abs_variance}"
        )
        return CodificationEmission(
            decision_class=decision_class,
            eligible=False,
            sample_size=n,
            p50_variance=p50,
            p90_variance=p90,
            skipped_reason=reason,
        )

    # Eligible — open a codification proposal.
    from engine.codification import (
        CodificationProposal,
        SimulationResult,
        open_proposal,
    )

    sim = SimulationResult(
        n=n,
        divergence_p50=p50,
        divergence_p90=p90,
        cost_savings_usd=None,
        latency_savings_ms=None,
    )
    proposal = CodificationProposal(
        candidate_pv=f"{decision_class}.v1",
        candidate_sv=f"{decision_class}.schema.v1",
        candidate_score=round(max(0.0, 1.0 - p90), 4),
        analyzer_run_at=datetime.now(tz=timezone.utc).isoformat(),
        proposed_python=proposed_python
        or f"# placeholder — analyzer must populate. decision_class={decision_class}",
        proposed_tests=proposed_tests
        or f"# placeholder — analyzer must populate. decision_class={decision_class}",
        why=why
        or (
            f"ovs_calibration: stable pattern for {decision_class} "
            f"(n={n}, p90_abs_variance={p90} <= {max_abs_variance})"
        ),
        sim=sim,
    )
    body = open_proposal(proposal, db_path=proposals_db_path)
    return CodificationEmission(
        decision_class=decision_class,
        eligible=True,
        sample_size=n,
        p50_variance=p50,
        p90_variance=p90,
        proposal_id=body["proposal_id"],
    )
