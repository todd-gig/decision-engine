"""Nightly sweep — converts the last 24h of overrides into actionable signals.

Per spec decision #5 (pattern detection runs nightly) + decision #8
(negative-polarity codification candidates) + decision #9 (drift signal
on de-codification candidate).

Stable patterns (cluster_size ≥5 AND span_seconds ≥48h) are emitted as
negative-polarity codification candidates via `engine.codification.queue
.open_proposal`. "Stable" means the pattern has persisted long enough to
rule out a single-operator burst — anchoring the codification proposal
on genuine recurring behavior, not noise.

penrose_signal: weakens
penrose_dimension: override_rate
why: A pattern detected in a single hour is a burst; a pattern that
spans 48h+ with 5+ events is a structural correction the engine is
consistently making wrong. That is the right substrate for codification
— it's not "what one operator did" but "what the system needs to learn
permanently."
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from . import patterns as patterns_mod
from . import storage


logger = logging.getLogger(__name__)


STABLE_CLUSTER_SIZE = 5  # spec — codification candidate threshold
STABLE_SPAN_SECONDS = 48 * 3600  # 48 hours


def _build_proposal_for_pattern(pattern: patterns_mod.OverridePattern) -> dict:
    """Translate an OverridePattern into a CodificationProposal payload.

    Returns the proposal-creation kwargs. The actual queue insertion
    happens via `engine.codification.queue.open_proposal` so the
    proposal lands in the standard queue the founder UI consumes.
    """
    proposed_python = (
        "# AUTO-GENERATED CODIFICATION CANDIDATE FROM HUMAN OVERRIDES\n"
        "# Decision class: {cls}\n"
        "# Cluster size: {size} overrides\n"
        "# Window: {ws} → {we} ({span}s)\n"
        "# Polarity: {polarity}\n"
        "# Recommended: {action}\n"
    ).format(
        cls=pattern.decision_class,
        size=pattern.cluster_size,
        ws=pattern.window_start,
        we=pattern.window_end,
        span=pattern.span_seconds,
        polarity=pattern.polarity,
        action=pattern.recommended_action,
    )
    proposed_tests = (
        "# TODO(reviewer): write a test that asserts the new default action.\n"
        f"# When decision_class={pattern.decision_class!r} the engine\n"
        f"# previously chose '{pattern.original_action_sig}' but operators\n"
        "# consistently overrode it. A passing test asserts the corrected\n"
        "# action is now the engine default.\n"
    )

    why = (
        f"Negative-polarity codification candidate from human-override "
        f"engine. Cluster of {pattern.cluster_size} overrides on "
        f"decision_class={pattern.decision_class!r} type={pattern.override_type!r} "
        f"spanning {pattern.span_seconds}s. Operators consistently "
        f"chose Y over X. Codify Y as the default."
    )
    # Candidate score ∝ cluster size, capped at 1.0; floor 0.5 so stable
    # patterns enter the queue with non-trivial score.
    score = min(1.0, 0.5 + pattern.cluster_size / 50.0)

    return {
        "candidate_pv": f"override_pattern:{pattern.pattern_id[:8]}",
        "candidate_sv": "v0.5",
        "candidate_score": score,
        "analyzer_run_at": datetime.now(tz=timezone.utc).isoformat(),
        "proposed_python": proposed_python,
        "proposed_tests": proposed_tests,
        "why": why,
    }


def _mark_pattern_emitted(
    pattern_id: str,
    proposal_id: str,
    db_path: Optional[str] = None,
) -> None:
    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            "UPDATE override_patterns SET emitted_codification = ? "
            "WHERE pattern_id = ?",
            (proposal_id, pattern_id),
        )
    finally:
        conn.close()


def run_nightly_sweep(
    *,
    window_days: int = 1,
    db_path: Optional[str] = None,
    codification_db_path: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Run the nightly sweep.

    1. Detect patterns over the last `window_days` (default 24h).
    2. Persist them to override_patterns.
    3. For each *stable* pattern (cluster_size ≥5 AND span ≥48h),
       open a negative-polarity codification proposal and link it back
       to the pattern row.

    Returns a summary dict for CLI / API consumers:
      {patterns_detected, patterns_persisted, codification_proposals,
       proposal_ids, ran_at, window_days, dry_run}
    """
    patterns_list = patterns_mod.detect_patterns(
        window_days=window_days, db_path=db_path,
    )
    detected = len(patterns_list)
    persisted = 0
    proposal_ids: list[str] = []

    if patterns_list and not dry_run:
        persisted = patterns_mod.persist_patterns(patterns_list, db_path=db_path)

    if not dry_run:
        # Lazy import — keeps human_override importable when codification
        # is missing (e.g., in narrowly-scoped test environments).
        from engine.codification import CodificationProposal, SimulationResult, open_proposal

        for pattern in patterns_list:
            if pattern.polarity != "negative":
                continue
            if pattern.cluster_size < STABLE_CLUSTER_SIZE:
                continue
            if pattern.span_seconds < STABLE_SPAN_SECONDS:
                continue
            kwargs = _build_proposal_for_pattern(pattern)
            sim = SimulationResult(
                n=pattern.cluster_size,
                divergence_p50=0.0,  # human-anchored — placeholder until OVS sim wires up
                divergence_p90=0.0,
                cost_savings_usd=None,
                latency_savings_ms=None,
            )
            proposal = CodificationProposal(
                candidate_pv=kwargs["candidate_pv"],
                candidate_sv=kwargs["candidate_sv"],
                candidate_score=kwargs["candidate_score"],
                analyzer_run_at=kwargs["analyzer_run_at"],
                proposed_python=kwargs["proposed_python"],
                proposed_tests=kwargs["proposed_tests"],
                why=kwargs["why"],
                sim=sim,
            )
            try:
                row = open_proposal(proposal, db_path=codification_db_path)
                proposal_id = row["proposal_id"]
                proposal_ids.append(proposal_id)
                _mark_pattern_emitted(
                    pattern.pattern_id, proposal_id, db_path=db_path,
                )
            except Exception as exc:  # pragma: no cover — log + continue
                logger.warning(
                    "failed to open codification proposal for pattern %s: %s",
                    pattern.pattern_id, exc,
                )

    return {
        "patterns_detected": detected,
        "patterns_persisted": persisted,
        "codification_proposals_opened": len(proposal_ids),
        "proposal_ids": proposal_ids,
        "ran_at": datetime.now(tz=timezone.utc).isoformat(),
        "window_days": window_days,
        "dry_run": dry_run,
    }
