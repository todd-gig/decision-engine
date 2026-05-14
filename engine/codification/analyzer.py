"""Codification analyzer — reads llm_audit and scores codification candidates.

Per specs/codification_engine_v0.md §Analyzer. v0 ships the analyzer
step 1: read audit rows, group by (prompt_version, schema_version),
compute candidate scores, return ranked candidates.

The proposer + simulator steps come later. v0 of the analyzer is
sufficient to populate the proposal queue if the operator wants a
candidate-only view (open_top_n_as_proposals=N writes minimal proposals).
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import open_proposal, CodificationProposal, SimulationResult
from ..ai_router import storage as audit_storage


@dataclass
class Candidate:
    candidate_pv: str
    candidate_sv: str
    volume: int
    response_variance: float
    audit_completeness: float
    outcome_stability: float
    candidate_score: float
    sample_audit_ids: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _read_audit_rows(db_path: Optional[str]) -> list[dict]:
    """Read all rows from llm_audit. Returns empty list if table doesn't exist
    or the database is unreachable."""
    try:
        conn = audit_storage.get_connection(db_path)
    except sqlite3.Error:
        return []
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM llm_audit")
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _normalize_volume(count: int, ecosystem_mean: float) -> float:
    """Log-scale relative to ecosystem mean; clamp to [0, 1].

    Volume score 0.5 = matches mean exactly. 1.0 = 10× mean. 0.0 = no
    volume."""
    if count <= 0 or ecosystem_mean <= 0:
        return 0.0
    ratio = count / ecosystem_mean
    log_ratio = math.log10(ratio + 1.0)   # +1 so ratio=1 → 0.30
    return max(0.0, min(1.0, log_ratio))


def _response_variance(rows: list[dict]) -> float:
    """Approximation: spread of out_chars / in_chars ratio + provider mix.

    Low variance → outputs are tightly coupled to inputs → codifiable.
    High variance → outputs vary across same-shaped inputs → keep LLM.

    Returns value in [0, 1]; 0 = perfectly deterministic, 1 = wildly varied.
    """
    if len(rows) < 2:
        return 1.0
    ratios = []
    for r in rows:
        in_chars = r.get("in_chars") or 0
        out_chars = r.get("out_chars") or 0
        if in_chars > 0:
            ratios.append(out_chars / in_chars)
    if len(ratios) < 2:
        return 1.0
    mean = statistics.mean(ratios)
    if mean == 0:
        return 0.0
    # Coefficient of variation; clamp to [0, 1]
    stdev = statistics.stdev(ratios)
    cv = stdev / mean
    return min(1.0, cv)


def _audit_completeness(rows: list[dict]) -> float:
    """Fraction of rows with full attribution available for replay.

    A row is "complete" if it has caller_engine, caller_function,
    in_tokens, out_tokens all non-null. Codification simulator needs
    these to replay against the deterministic Python proposal.
    """
    if not rows:
        return 0.0
    complete = 0
    for r in rows:
        if (
            r.get("caller_engine")
            and r.get("caller_function")
            and r.get("in_tokens") is not None
            and r.get("out_tokens") is not None
        ):
            complete += 1
    return complete / len(rows)


def _outcome_stability(rows: list[dict]) -> float:
    """V0 default: 0.5 (neutral) when no OVS signal available.

    Post-OVS shipping, this reads OVS's variance per decision class
    that this (pv, sv) serves. v0 has no OVS data so we score neutrally.
    """
    return 0.5


def _candidate_score(
    *, volume_norm: float, variance: float, completeness: float, stability: float,
) -> float:
    """Composite score per spec §Candidate scoring.

    score = 0.4 * volume_norm + 0.3 * (1 - variance) + 0.2 * stability + 0.1 * completeness
    """
    raw = (
        0.4 * volume_norm
        + 0.3 * (1.0 - variance)
        + 0.2 * stability
        + 0.1 * completeness
    )
    return max(0.0, min(1.0, raw))


def analyze(
    *,
    min_volume: int = 100,
    score_threshold: float = 0.7,
    audit_db_path: Optional[str] = None,
) -> list[Candidate]:
    """Read llm_audit, group by (pv, sv), score, return candidates above threshold."""
    rows = _read_audit_rows(audit_db_path)
    if not rows:
        return []

    # Group by (prompt_version, schema_version)
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r.get("prompt_version", ""), r.get("schema_version", ""))
        groups.setdefault(key, []).append(r)

    # Ecosystem mean = total rows / number of distinct (pv, sv) groups
    ecosystem_mean = len(rows) / max(1, len(groups))

    candidates: list[Candidate] = []
    for (pv, sv), grows in groups.items():
        if len(grows) < min_volume:
            continue
        volume_norm = _normalize_volume(len(grows), ecosystem_mean)
        variance = _response_variance(grows)
        completeness = _audit_completeness(grows)
        stability = _outcome_stability(grows)
        score = _candidate_score(
            volume_norm=volume_norm,
            variance=variance,
            completeness=completeness,
            stability=stability,
        )
        if score < score_threshold:
            continue
        candidates.append(Candidate(
            candidate_pv=pv,
            candidate_sv=sv,
            volume=len(grows),
            response_variance=variance,
            audit_completeness=completeness,
            outcome_stability=stability,
            candidate_score=score,
            sample_audit_ids=[r["audit_id"] for r in grows[:5]],
        ))

    candidates.sort(key=lambda c: -c.candidate_score)
    return candidates


def open_candidates_as_proposals(
    candidates: list[Candidate],
    *,
    top_n: int,
    proposals_db_path: Optional[str] = None,
    why: str = "auto-opened by analyzer",
) -> list[dict]:
    """For the top-N candidates, open a minimal proposal in the queue.

    "Minimal" = proposed_python and proposed_tests are placeholders
    referring back to the analyzer run. Operator review fills them in,
    or the proposer step (later) generates them.
    """
    out = []
    now = datetime.now(tz=timezone.utc).isoformat()
    for cand in candidates[:top_n]:
        prop = CodificationProposal(
            candidate_pv=cand.candidate_pv,
            candidate_sv=cand.candidate_sv,
            candidate_score=cand.candidate_score,
            analyzer_run_at=now,
            proposed_python=(
                f"# TODO: proposer step (v0.5) generates Python for "
                f"({cand.candidate_pv}, {cand.candidate_sv}) "
                f"from sample audit_ids {cand.sample_audit_ids}"
            ),
            proposed_tests=(
                f"# TODO: proposer step (v0.5) generates pytest cases "
                f"from sample audit_ids {cand.sample_audit_ids}"
            ),
            why=(
                f"{why}; analyzer scored {cand.candidate_score:.3f} "
                f"(volume={cand.volume}, variance={cand.response_variance:.3f}, "
                f"completeness={cand.audit_completeness:.3f})"
            ),
            sim=SimulationResult(
                n=cand.volume,
                divergence_p50=cand.response_variance,
                divergence_p90=min(1.0, cand.response_variance * 1.6),
                cost_savings_usd=None,
                latency_savings_ms=None,
            ),
        )
        out.append(open_proposal(prop, db_path=proposals_db_path))
    return out
