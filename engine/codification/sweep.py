"""Codification sweep — scheduled entrypoint that closes the flywheel.

1. Run the analyzer (audit-log scan, score candidates).
2. Map each analyzer Candidate to a ReadinessCandidate using the
   audit metadata available, score against doctrine thresholds.
3. For candidates that clear the readiness gate, open proposals.
4. Return a structured sweep report.

Schedule pattern: this is the entrypoint Cloud Scheduler hits daily
(via `POST /v1/codification/sweep`) and the entrypoint operators run
via `python cli.py codification-sweep`. Matches the cadence pattern
HME uses for the weekly initiative report.

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Optional

from .analyzer import Candidate, analyze, open_candidates_as_proposals
from .readiness import (
    ReadinessCandidate,
    ReadinessScore,
    ReadinessThresholds,
    compute_readiness,
    load_thresholds,
)


# Sweep-level prompt + schema versions. Bump when the sweep flow itself
# changes (e.g. new readiness component). Carried on every analyzer step
# so audit replay can attribute outcomes to a specific sweep contract.
SWEEP_PROMPT_VERSION = "codification_sweep.v0.5"
SWEEP_SCHEMA_VERSION = "codification_sweep.schema.v0.5"


@dataclass
class SweepReport:
    """Structured result of one sweep run."""
    ran_at: str
    candidates_seen: int
    candidates_ready: int
    proposals_opened: int
    candidate_details: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    prompt_version: str = SWEEP_PROMPT_VERSION
    schema_version: str = SWEEP_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_to_readiness(c: Candidate) -> ReadinessCandidate:
    """Project the analyzer candidate onto the readiness contract.

    - `executions`        ← analyzer `volume`
    - `exception_rate`    ← analyzer `response_variance` (high variance
      stands in for exception frequency until OVS lands)
    - `stability`         ← analyzer `outcome_stability`
    - `value`             ← analyzer `audit_completeness` (proxy for
      operational value coverage; replaced by OVS attribution post-v0.5)
    - `risk`              ← analyzer `response_variance` (variance also
      proxies risk until OVS lands; weight is intentionally tiny)
    """
    return ReadinessCandidate(
        candidate_pv=c.candidate_pv,
        candidate_sv=c.candidate_sv,
        executions=c.volume,
        exception_rate=float(c.response_variance),
        stability=float(c.outcome_stability),
        value=float(c.audit_completeness),
        risk=float(c.response_variance),
    )


def run_sweep(
    *,
    min_volume: int = 50,
    score_threshold: float = 0.7,
    audit_db_path: Optional[str] = None,
    proposals_db_path: Optional[str] = None,
    thresholds: Optional[ReadinessThresholds] = None,
    open_proposals: bool = True,
    why: str = "scheduled codification sweep",
) -> SweepReport:
    """Run analyzer → readiness → optionally open proposals.

    `min_volume` is intentionally the doctrine floor (50). Operators
    can lower for staging environments; production should use ≥50.
    """
    th = thresholds or load_thresholds()
    ran_at = datetime.now(tz=timezone.utc).isoformat()

    raw_candidates = analyze(
        min_volume=min_volume,
        score_threshold=score_threshold,
        audit_db_path=audit_db_path,
    )

    candidate_details: list[dict[str, Any]] = []
    ready_candidates: list[Candidate] = []
    for cand in raw_candidates:
        rc = _candidate_to_readiness(cand)
        rs = compute_readiness(rc, thresholds=th)
        candidate_details.append({
            "candidate": cand.to_dict(),
            "readiness": rs.to_dict(),
        })
        if rs.is_ready:
            ready_candidates.append(cand)

    proposals: list[dict[str, Any]] = []
    if open_proposals and ready_candidates:
        proposals = open_candidates_as_proposals(
            ready_candidates,
            top_n=len(ready_candidates),
            proposals_db_path=proposals_db_path,
            why=f"{why}; readiness gate passed",
        )

    return SweepReport(
        ran_at=ran_at,
        candidates_seen=len(raw_candidates),
        candidates_ready=len(ready_candidates),
        proposals_opened=len(proposals),
        candidate_details=candidate_details,
        proposals=proposals,
    )


__all__ = [
    "SweepReport",
    "SWEEP_PROMPT_VERSION",
    "SWEEP_SCHEMA_VERSION",
    "run_sweep",
]
