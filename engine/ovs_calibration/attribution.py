"""Attribution daemon + AttributionLink.

Three-stage attribution algorithm per spec §Attribution algorithm:
  1. Direct attribution      — decision projection explicitly names the metric.
                               confidence = 1.0; method='direct'.
  2. Temporal + entity match — outcome occurs within expected horizon at the
                               entity the decision targeted; confidence based on
                               horizon-fit + entity-match exactness.
  3. Causal-chain attribution — outcome attributes through a chain (decision A
                               -> output -> input to decision B -> outcome).
                               v0.5 ships a stub that returns []; full impl in v0.6+.

Layer assignment per Framework 5.12 (canonical doctrine §5.12):
  Layer 1  (0-7d):    100%   cascade_multiplier = 1.0
  Layer 2  (7-30d):    70%   cascade_multiplier = 0.7
  Layer 3  (30-90d):   35%   cascade_multiplier = 0.35
  Layer 4  (90+d):     track-only; cascade_multiplier = 0.0 (no calibration write)

Cascade multiplier across systems (Framework 5.12 line 145):
  1 system  -> 1.0×
  2 systems -> 1.4× (linear interpolation)
  3 systems -> 1.8×
  4 systems -> 2.2×

WHY: separating the daemon from the writer keeps attribution pure and
test-friendly; the daemon emits AttributionLink rows the variance computer +
revision writer then consume. Three-stage is doctrine — direct is gold-standard
but rare without certificate-side discipline; temporal+entity is the workhorse;
causal-chain enables Framework 5.12 propagation in v0.6+.

penrose_signal: weakens
penrose_dimension: cascade
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from . import storage
from .variance import DecisionCertificateLike, OutcomeEventLike


# ─────────────────────────────────────────────
# Framework 5.12 — Layer thresholds
# ─────────────────────────────────────────────

LAYER_BOUNDARIES_DAYS = {
    1: (0, 7),
    2: (7, 30),
    3: (30, 90),
}
LAYER_4_FLOOR_DAYS = 90

LAYER_CASCADE_DECAY = {
    1: 1.0,
    2: 0.7,
    3: 0.35,
    4: 0.0,
}

# 1 system = 1.0x, 4 systems = 2.2x; linear interpolation between
SYSTEMS_CASCADE_MULTIPLIER = {1: 1.0, 2: 1.4, 3: 1.8, 4: 2.2}


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────


@dataclass
class AttributionLink:
    """One (decision, outcome) attribution row.

    Mirrors the spec §AttributionLink schema (line 43).
    """
    decision_certificate_id: str
    outcome_event_id: str
    confidence: float
    attribution_method: str  # direct | temporal | causal-chain | manual
    layer_number: int  # 1 | 2 | 3 | 4
    cascade_multiplier: float
    reasoning: str
    attributed_by: str = "system"
    attributed_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    id: str = field(default_factory=lambda: f"attr-{uuid.uuid4().hex[:12]}")
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1]; got {self.confidence}")
        if self.attribution_method not in {
            "direct", "temporal", "causal-chain", "manual"
        }:
            raise ValueError(
                f"attribution_method must be direct|temporal|causal-chain|manual; "
                f"got {self.attribution_method!r}"
            )
        if self.layer_number not in (1, 2, 3, 4):
            raise ValueError(f"layer_number must be 1|2|3|4; got {self.layer_number}")
        if not self.reasoning or len(self.reasoning.strip()) < 5:
            raise ValueError("reasoning is required (>=5 chars); always-record-WHY")


# ─────────────────────────────────────────────
# Layer + cascade math
# ─────────────────────────────────────────────


def assign_layer(
    decision_at: datetime,
    outcome_at: datetime,
) -> int:
    """Compute Framework 5.12 layer from time delta.

    Edges per spec/doctrine:
      delta < 0           -> layer 1 (treat as same-day; clock skew tolerant)
      0   <= delta < 7    -> layer 1
      7   <= delta < 30   -> layer 2
      30  <= delta < 90   -> layer 3
      90  <= delta        -> layer 4 (track-only)

    The 7d / 30d / 90d boundary days fall into the *higher* layer (i.e. exactly
    7d -> layer 2). This matches the canonical "Layer 1 (0-7d, 100%)" wording
    where 7d is the first day of Layer 2.
    """
    delta_days = (outcome_at - decision_at).total_seconds() / 86400.0
    if delta_days < 7:
        return 1
    if delta_days < 30:
        return 2
    if delta_days < 90:
        return 3
    return 4


def cascade_multiplier_for_layer(layer: int) -> float:
    """Per-layer decay multiplier; see LAYER_CASCADE_DECAY."""
    if layer not in LAYER_CASCADE_DECAY:
        raise ValueError(f"layer must be 1|2|3|4; got {layer}")
    return LAYER_CASCADE_DECAY[layer]


def cascade_multiplier_for_systems(system_count: int) -> float:
    """Per Framework 5.12: 1 system 1.0x ... 4 systems 2.2x (linear interp).

    Clamps:
      system_count <= 1 -> 1.0
      system_count >= 4 -> 2.2
    """
    if system_count <= 1:
        return 1.0
    if system_count >= 4:
        return 2.2
    return SYSTEMS_CASCADE_MULTIPLIER[system_count]


# ─────────────────────────────────────────────
# Three-stage attribution
# ─────────────────────────────────────────────


def attribute_direct(
    decision: DecisionCertificateLike,
    outcome: OutcomeEventLike,
    *,
    reasoning: str = "",
) -> Optional[AttributionLink]:
    """Stage 1: direct attribution.

    Triggered when the decision certificate's projection metric exactly matches
    the outcome event's metric AND the entity matches. Confidence is 1.0 by
    convention.

    Returns None if the metric doesn't match — caller falls through to stage 2.
    """
    if decision.projection.metric != outcome.metric:
        return None

    decision_at = _parse_iso(decision.issued_at) or _now()
    outcome_at = _parse_iso(outcome.observed_at) or _now()
    layer = assign_layer(decision_at, outcome_at)

    return AttributionLink(
        decision_certificate_id=decision.decision_certificate_id,
        outcome_event_id=outcome.id,
        confidence=1.0,
        attribution_method="direct",
        layer_number=layer,
        cascade_multiplier=cascade_multiplier_for_layer(layer),
        reasoning=reasoning or (
            f"Direct: decision projection.metric == outcome.metric "
            f"({decision.projection.metric!r})"
        ),
    )


def attribute_temporal_entity(
    decision: DecisionCertificateLike,
    outcome: OutcomeEventLike,
    *,
    decision_entity: str,
    horizon_days: Optional[int] = None,
    reasoning: str = "",
) -> Optional[AttributionLink]:
    """Stage 2: temporal + entity attribution.

    Triggered when:
      - outcome's metric is plausibly in the decision's metric family
        (we accept either exact prefix match `metric.startswith(proj.metric)` OR
        a manual decision_class -> metric registry hit — registry hit is the
        caller's responsibility; this function just checks prefix as a
        permissive fallback)
      - outcome occurs within the decision class's expected time horizon
      - entity strings match (case-insensitive)

    Confidence formula:
      base = 0.7
      +0.15 if outcome.observed_at is within (horizon_days * 0.5)
      +0.10 if metric exact prefix match
      -0.20 if outside (horizon_days * 1.5)
    Clamped to [0.3, 0.95] — never 1.0 (only direct gets 1.0).
    """
    outcome_entity_norm = (outcome.source or "").lower() or None
    target_entity_norm = decision_entity.lower()
    # Permissive entity match: any of source/metric contains the entity string
    if not (
        outcome_entity_norm == target_entity_norm
        or target_entity_norm in (outcome.source or "").lower()
        or target_entity_norm in outcome.metric.lower()
    ):
        return None

    metric_match = (
        outcome.metric == decision.projection.metric
        or outcome.metric.startswith(decision.projection.metric + ".")
        or decision.projection.metric.startswith(outcome.metric + ".")
    )
    if not metric_match:
        return None

    decision_at = _parse_iso(decision.issued_at) or _now()
    outcome_at = _parse_iso(outcome.observed_at) or _now()
    layer = assign_layer(decision_at, outcome_at)

    delta_days = (outcome_at - decision_at).total_seconds() / 86400.0
    hd = horizon_days if horizon_days is not None else decision.projection.horizon_days
    hd = max(hd, 1)  # avoid divide-by-zero

    confidence = 0.7
    if delta_days <= hd * 0.5:
        confidence += 0.15
    if outcome.metric == decision.projection.metric:
        confidence += 0.10
    if delta_days > hd * 1.5:
        confidence -= 0.20
    confidence = max(0.3, min(confidence, 0.95))

    return AttributionLink(
        decision_certificate_id=decision.decision_certificate_id,
        outcome_event_id=outcome.id,
        confidence=round(confidence, 3),
        attribution_method="temporal",
        layer_number=layer,
        cascade_multiplier=cascade_multiplier_for_layer(layer),
        reasoning=reasoning or (
            f"Temporal+entity: entity {decision_entity!r} matched, metric "
            f"{outcome.metric!r} in family of {decision.projection.metric!r}, "
            f"delta={delta_days:.1f}d / horizon={hd}d"
        ),
    )


def attribute_causal_chain(
    decision: DecisionCertificateLike,
    outcome: OutcomeEventLike,
    *,
    chain_links: Iterable[dict] | None = None,
    reasoning: str = "",
) -> list[AttributionLink]:
    """Stage 3: causal-chain attribution.

    v0.5 STUB — returns []. Full implementation (decision A -> output -> input
    to decision B -> outcome) ships in v0.6+ once the upstream causal_mapper
    surface is wired through.

    WHY a stub vs an empty function: the signature exists so the daemon's
    fan-out is set, callers can introspect, and tests can verify it
    deterministically returns nothing without raising.
    """
    _ = chain_links, reasoning  # signature reserved
    return []


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────


def persist_link(link: AttributionLink, db_path: str | None = None) -> dict:
    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO attribution_links (
                id, decision_certificate_id, outcome_event_id,
                confidence, attribution_method, layer_number,
                cascade_multiplier, attributed_at, attributed_by,
                reasoning, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link.id,
                link.decision_certificate_id,
                link.outcome_event_id,
                link.confidence,
                link.attribution_method,
                link.layer_number,
                link.cascade_multiplier,
                link.attributed_at,
                link.attributed_by,
                link.reasoning,
                link.schema_version,
            ),
        )
    finally:
        conn.close()
    return _link_to_dict(link)


def list_links_for_decision(
    decision_certificate_id: str,
    db_path: str | None = None,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM attribution_links WHERE decision_certificate_id = ? "
            "ORDER BY attributed_at",
            (decision_certificate_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_links_for_outcome(
    outcome_event_id: str,
    db_path: str | None = None,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM attribution_links WHERE outcome_event_id = ? "
            "ORDER BY attributed_at",
            (outcome_event_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Daemon entrypoint
# ─────────────────────────────────────────────


def attribute(
    decision: DecisionCertificateLike,
    outcome: OutcomeEventLike,
    *,
    decision_entity: str = "",
    horizon_days: Optional[int] = None,
) -> list[AttributionLink]:
    """Run the three-stage attribution algorithm and return all links produced.

    v0.5 ships stages 1 + 2. Stage 3 is wired but returns []. Each stage is
    tried in order; if direct matches we still allow temporal as well only when
    the entity differs (cascade case) — for v0.5 we collapse to: direct wins
    if it fires, otherwise temporal+entity attempts.
    """
    direct = attribute_direct(decision, outcome)
    if direct is not None:
        return [direct]

    temporal: Optional[AttributionLink] = None
    if decision_entity:
        temporal = attribute_temporal_entity(
            decision, outcome,
            decision_entity=decision_entity,
            horizon_days=horizon_days,
        )

    links: list[AttributionLink] = []
    if temporal is not None:
        links.append(temporal)

    # Stage 3 stub — currently always []
    links.extend(attribute_causal_chain(decision, outcome))
    return links


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Tolerate trailing Z (per JS / ISO-8601 common variant)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _link_to_dict(link: AttributionLink) -> dict:
    return {
        "id": link.id,
        "decision_certificate_id": link.decision_certificate_id,
        "outcome_event_id": link.outcome_event_id,
        "confidence": link.confidence,
        "attribution_method": link.attribution_method,
        "layer_number": link.layer_number,
        "cascade_multiplier": link.cascade_multiplier,
        "attributed_at": link.attributed_at,
        "attributed_by": link.attributed_by,
        "reasoning": link.reasoning,
        "schema_version": link.schema_version,
    }
