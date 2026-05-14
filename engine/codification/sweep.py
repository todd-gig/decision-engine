"""Codification sweep — scheduled entrypoint that closes the flywheel.

1. Run the analyzer (audit-log scan, score candidates).
2. Map each analyzer Candidate to a ReadinessCandidate using the
   audit metadata available, score against doctrine thresholds.
3. For candidates that clear the readiness gate, open proposals.
4. (v0.6 — opt-in) For each opened proposal, ask the LLM proposer to
   draft a deterministic Python module; replay it through the
   simulator; only proposals whose simulation `PASSED` are marked
   `ready_for_signoff`. Gated by `codification.proposer.enabled` so
   existing behavior is unchanged unless flipped on.
5. Return a structured sweep report.

Schedule pattern: this is the entrypoint Cloud Scheduler hits daily
(via `POST /v1/codification/sweep`) and the entrypoint operators run
via `python cli.py codification-sweep`. Matches the cadence pattern
HME uses for the weekly initiative report.

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

import os
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
SWEEP_PROMPT_VERSION = "codification_sweep.v0.6"
SWEEP_SCHEMA_VERSION = "codification_sweep.schema.v0.6"

#: Env flag mirroring `codification.proposer.enabled` config knob. Default
#: OFF — flipping it on is the v0.6 opt-in switch that drives the LLM
#: proposer + simulator inside the scheduled sweep.
PROPOSER_ENABLED_ENV = "CODIFICATION_PROPOSER_ENABLED"


def _proposer_enabled_flag(explicit: Optional[bool]) -> bool:
    """Resolve the proposer-enabled gate.

    Order:
      1. Explicit kwarg to `run_sweep`
      2. `CODIFICATION_PROPOSER_ENABLED` env (truthy values: 1,true,yes,on)
      3. Default False — preserves v0.5 behavior.
    """
    if explicit is not None:
        return bool(explicit)
    raw = os.environ.get(PROPOSER_ENABLED_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SweepReport:
    """Structured result of one sweep run.

    v0.6 additions (all populated only when `proposer_enabled=True`):
      - module_proposals_drafted: count of LLM module proposals drafted
      - module_proposals_passed: count whose simulator status == PASSED
      - module_proposals_rejected: count rejected for divergence > 5%
      - module_proposal_details: per-proposal proposer/sim summary

    Existing fields are unchanged when the flag is off.
    """
    ran_at: str
    candidates_seen: int
    candidates_ready: int
    proposals_opened: int
    candidate_details: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    prompt_version: str = SWEEP_PROMPT_VERSION
    schema_version: str = SWEEP_SCHEMA_VERSION
    proposer_enabled: bool = False
    module_proposals_drafted: int = 0
    module_proposals_passed: int = 0
    module_proposals_rejected: int = 0
    module_proposal_details: list[dict[str, Any]] = field(default_factory=list)

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


def _run_proposer_and_simulator(
    *,
    ready_candidates: list[Candidate],
    proposals: list[dict[str, Any]],
    top_n: int,
    proposals_db_path: Optional[str],
    audit_db_path: Optional[str],
    md_dir: Optional[str] = None,
) -> tuple[int, int, int, list[dict[str, Any]]]:
    """For each opened proposal, draft a module via LLM proposer and simulate.

    Returns (drafted, passed, rejected, details). Failures (LLM
    unavailable, banned import, compile error) are captured per-row and
    do NOT halt the sweep — the report carries the error so operators
    can triage.
    """
    # Local imports — keep sweep importable when proposer flag is off
    # in environments without anthropic/openai SDK creds.
    from .proposer import (
        BannedImportError,
        Candidate as ProposerCandidate,
        propose_python_module,
    )
    from .simulator import SimulatorCompileError, simulate_against_history

    details: list[dict[str, Any]] = []
    drafted = 0
    passed = 0
    rejected = 0

    pairs = list(zip(ready_candidates[:top_n], proposals[:top_n]))
    for cand, opened in pairs:
        proposal_id = opened["proposal_id"]
        evidence_ids = list(cand.sample_audit_ids)
        pc = ProposerCandidate(
            candidate_id=proposal_id,
            candidate_pv=cand.candidate_pv,
            candidate_sv=cand.candidate_sv,
            candidate_score=cand.candidate_score,
            executions=cand.volume,
            evidence_ids=evidence_ids,
            why=opened.get("why", ""),
        )
        row: dict[str, Any] = {
            "proposal_id": proposal_id,
            "candidate_pv": cand.candidate_pv,
            "candidate_sv": cand.candidate_sv,
        }
        try:
            module_proposal = propose_python_module(
                pc, certificate=None, db_path=proposals_db_path,
                md_dir=md_dir,
            )
            drafted += 1
            row["module_proposal"] = module_proposal.to_dict()
        except BannedImportError as e:
            rejected += 1
            row["error"] = f"banned_import: {e}"
            row["simulator_passed"] = False
            row["ready_for_signoff"] = False
            details.append(row)
            continue
        except Exception as e:  # noqa: BLE001 — capture for operator triage
            row["error"] = f"proposer_failure: {type(e).__name__}: {e}"
            row["simulator_passed"] = False
            row["ready_for_signoff"] = False
            details.append(row)
            continue

        try:
            sim = simulate_against_history(
                module_proposal,
                evidence_decision_ids=evidence_ids,
                audit_db_path=audit_db_path,
            )
        except SimulatorCompileError as e:
            rejected += 1
            row["error"] = f"simulator_compile: {e}"
            row["simulator_passed"] = False
            row["ready_for_signoff"] = False
            details.append(row)
            continue

        row["simulation"] = {
            "status": sim.status,
            "divergence_rate": sim.divergence_rate,
            "n": sim.n,
            "module_proposal_id": sim.module_proposal_id,
            "signature_match_hash": sim.signature_match_hash,
            "cases": sim.divergence_cases,
        }
        sim_passed = sim.status == "PASSED"
        row["simulator_passed"] = sim_passed
        # Per spec: only simulator_passed proposals are eligible for sign-off.
        row["ready_for_signoff"] = sim_passed
        if sim_passed:
            passed += 1
        else:
            rejected += 1
        details.append(row)

    return drafted, passed, rejected, details


def run_sweep(
    *,
    min_volume: int = 50,
    score_threshold: float = 0.7,
    audit_db_path: Optional[str] = None,
    proposals_db_path: Optional[str] = None,
    thresholds: Optional[ReadinessThresholds] = None,
    open_proposals: bool = True,
    why: str = "scheduled codification sweep",
    proposer_enabled: Optional[bool] = None,
    proposer_top_n: int = 5,
    proposer_md_dir: Optional[str] = None,
) -> SweepReport:
    """Run analyzer → readiness → optionally open proposals → optionally
    draft + simulate the top-N candidate modules.

    `min_volume` is intentionally the doctrine floor (50). Operators
    can lower for staging environments; production should use ≥50.

    `proposer_enabled` defaults to None → resolved from the
    `CODIFICATION_PROPOSER_ENABLED` env (default off). When True the
    sweep additionally calls the LLM proposer + simulator and reports
    which proposals are `ready_for_signoff`.
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

    proposer_flag = _proposer_enabled_flag(proposer_enabled)
    drafted = passed = rejected = 0
    module_details: list[dict[str, Any]] = []
    if proposer_flag and proposals:
        drafted, passed, rejected, module_details = _run_proposer_and_simulator(
            ready_candidates=ready_candidates,
            proposals=proposals,
            top_n=max(0, int(proposer_top_n)),
            proposals_db_path=proposals_db_path,
            audit_db_path=audit_db_path,
            md_dir=proposer_md_dir,
        )

    return SweepReport(
        ran_at=ran_at,
        candidates_seen=len(raw_candidates),
        candidates_ready=len(ready_candidates),
        proposals_opened=len(proposals),
        candidate_details=candidate_details,
        proposals=proposals,
        proposer_enabled=proposer_flag,
        module_proposals_drafted=drafted,
        module_proposals_passed=passed,
        module_proposals_rejected=rejected,
        module_proposal_details=module_details,
    )


__all__ = [
    "SweepReport",
    "SWEEP_PROMPT_VERSION",
    "SWEEP_SCHEMA_VERSION",
    "PROPOSER_ENABLED_ENV",
    "run_sweep",
]
