"""per_entity_revenue — per-entity breakdown of Revenue per Human-Touch.

WHAT: Reads `outcome_events` (filtered by entity + kind=revenue family)
to sum revenue per entity, and `human_overrides.source_engine` +
`codification_certificates` signers to count human touches associated
with each entity. Returns one row per entity with the resulting ratio.

WHY: The aggregate `revenue_per_human_touch` metric tells us the
ecosystem trend, but the operator UI needs to see which entity is
producing the revenue (and which entity is absorbing the human
touches). Per-entity breakdown is what makes the metric actionable for
each business unit — without it, "is PDC contributing to the
trend?" can't be answered without ad-hoc SQL.

WHERE: Reads
  - drift_sentinel/ovs_calibration.db (outcome_events.entity + metric)
  - drift_sentinel/human_overrides.db (source_engine -> entity heuristic)
  - drift_sentinel/codification_proposals.db (codification touches are
    NOT entity-attributable yet; we count them in the aggregate only,
    not per-entity, and report `codification_touches_pooled` for honesty)

WHEN: Read on each hit of `/v1/penrose/revenue/touch-rate`. No cache.

HOW:
  - Window filter: `observed_at >= window_start` for revenue,
    `overridden_at >= window_start` for touches.
  - Entity resolution for touches: `source_engine` is mapped via
    SOURCE_ENGINE_TO_ENTITY (carmen-beach engines start with "carmen-",
    ti-solutions engines start with "ti-", gigaton-ui engines start
    with "gigaton-ui" / "client.platform"). Unknown engines bucket as
    `unknown`.
  - Revenue family filter: outcomes with `kind` registered as revenue
    OR metric starts with `revenue.` (defensive when source row absent).

CONTEXT: Never synthesizes. When neither side is populated, the entity
row reports `revenue_usd=0, touches=0, value=None` so dashboards can
detect the half-instrumented state.

penrose_signal: weakens
penrose_dimension: revenue_per_human_touch
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# ── Mapping ────────────────────────────────────────────────────────────────


# Maps the free-form `source_engine` text recorded on each override to
# the canonical entity. Prefix-match semantics: an override with
# source_engine='carmen-beach-pricing-engine' maps to 'carmen-beach'.
# WHY a prefix map: `source_engine` is not constrained at write time —
# the engines that emit overrides use varying names. Until we add a
# `decision_entity` column on overrides, this prefix table is the
# pragmatic bridge.
SOURCE_ENGINE_TO_ENTITY: dict[str, str] = {
    "carmen-beach":      "carmen-beach",
    "carmen_beach":      "carmen-beach",
    "stvr":              "carmen-beach",
    "ti-solutions":      "ti-solutions",
    "ti_solutions":      "ti-solutions",
    "hubspot":           "ti-solutions",
    "gigaton-ui":        "gigaton-ui",
    "gigaton_ui":        "gigaton-ui",
    "client.platform":   "gigaton-ui",
}


# Canonical entities tracked in the per-entity panel. Any others get
# bucketed as `other`. Keep this explicit so the UI never surprises with
# new rows from a typo in source_engine.
KNOWN_ENTITIES: tuple[str, ...] = ("carmen-beach", "ti-solutions", "gigaton-ui")


@dataclass
class EntityRevenueTouch:
    """One row of the per-entity panel."""
    entity: str
    window_days: int
    revenue_usd: float = 0.0
    revenue_event_count: int = 0
    override_touches: int = 0
    codification_touches: int = 0    # per-entity attribution NOT yet wired
    total_touches: int = 0
    value: Optional[float] = None    # revenue_usd / total_touches; null if 0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "window_days": self.window_days,
            "revenue_usd": round(self.revenue_usd, 4),
            "revenue_event_count": self.revenue_event_count,
            "override_touches": self.override_touches,
            "codification_touches": self.codification_touches,
            "total_touches": self.total_touches,
            "value": self.value,
            "note": self.note,
        }


# ── helpers ────────────────────────────────────────────────────────────────


def _resolve_entity(source_engine: Optional[str]) -> str:
    """Map source_engine -> canonical entity (or 'unknown')."""
    if not source_engine:
        return "unknown"
    s = source_engine.strip().lower()
    # Try exact match first, then prefix match. WHY both: exact match
    # short-circuits for the common "carmen-beach" case; prefix match
    # catches "carmen-beach-pricing-engine".
    if s in SOURCE_ENGINE_TO_ENTITY:
        return SOURCE_ENGINE_TO_ENTITY[s]
    for key, ent in SOURCE_ENGINE_TO_ENTITY.items():
        if s.startswith(key):
            return ent
    return "unknown"


def _safe_open_readonly(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        return None


def _window_start(window_days: int) -> str:
    return (
        datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    ).isoformat()


# ── revenue side ───────────────────────────────────────────────────────────


def _sum_revenue_per_entity(
    ovs_db_path: Path,
    window_days: int,
) -> dict[str, tuple[float, int]]:
    """Return {entity: (sum_observed_value, event_count)} for revenue events.

    Filter:
      - observed_at >= window_start
      - metric starts with 'revenue.' OR source's registered kind == 'revenue'
        (we evaluate the metric prefix here since that's a simple,
        defensive check; pulling kind requires a JOIN that the lightweight
        outcome_events query intentionally avoids).
    """
    conn = _safe_open_readonly(ovs_db_path)
    if conn is None:
        return {}
    start = _window_start(window_days)
    try:
        try:
            rows = conn.execute(
                """
                SELECT entity, observed_value
                FROM outcome_events
                WHERE observed_at >= ?
                  AND metric LIKE 'revenue.%'
                """,
                (start,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    finally:
        conn.close()

    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        ent = r["entity"] or "unknown"
        total, count = out.get(ent, (0.0, 0))
        try:
            v = float(r["observed_value"])
        except (TypeError, ValueError):
            continue
        out[ent] = (total + v, count + 1)
    return out


# ── touch side ─────────────────────────────────────────────────────────────


def _count_override_touches_per_entity(
    overrides_db_path: Path,
    window_days: int,
) -> dict[str, int]:
    """Count overrides per entity in the window. source_engine -> entity."""
    conn = _safe_open_readonly(overrides_db_path)
    if conn is None:
        return {}
    start = _window_start(window_days)
    try:
        try:
            rows = conn.execute(
                """
                SELECT source_engine FROM human_overrides
                WHERE overridden_at >= ?
                """,
                (start,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    finally:
        conn.close()

    out: dict[str, int] = {}
    for r in rows:
        ent = _resolve_entity(r["source_engine"])
        out[ent] = out.get(ent, 0) + 1
    return out


def _count_codification_touches_pooled(
    codification_db_path: Path,
    window_days: int,
) -> int:
    """Count codification certificate signings in the window (pooled, not per-entity).

    WHY pooled: codification certificates don't carry an entity field yet;
    they live at the ecosystem layer. We return a single pooled number
    so dashboards can show "the ratio per entity is `revenue / overrides`
    + a single ecosystem-wide `codification_touches_pooled` ≥ 0 noted
    on every row".
    """
    conn = _safe_open_readonly(codification_db_path)
    if conn is None:
        return 0
    start = _window_start(window_days)
    try:
        try:
            rows = conn.execute(
                """
                SELECT signers FROM codification_certificates
                WHERE signed_at >= ?
                """,
                (start,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    finally:
        conn.close()
    count = 0
    for r in rows:
        try:
            signers = json.loads(r["signers"]) if r["signers"] else []
        except (TypeError, ValueError):
            signers = []
        if signers:
            count += 1
    return count


# ── public ─────────────────────────────────────────────────────────────────


def revenue_per_touch_by_entity(
    window_days: int = 90,
    *,
    ovs_db_path: Optional[str | Path] = None,
    overrides_db_path: Optional[str | Path] = None,
    codification_db_path: Optional[str | Path] = None,
    extra_entities: Optional[list[str]] = None,
) -> dict:
    """Return per-entity Revenue per Human-Touch.

    Shape:
      {
        "window_days": int,
        "by_entity": [ EntityRevenueTouch.to_dict(), ... ],
        "codification_touches_pooled": int,  # ecosystem-wide, not per-entity
        "computed_at": iso,
        "note": "...",
      }
    """
    window_days = max(1, int(window_days))
    repo_root = Path(__file__).resolve().parent.parent.parent
    ovs_path = Path(ovs_db_path) if ovs_db_path else (
        repo_root / "drift_sentinel" / "ovs_calibration.db"
    )
    ov_path = Path(overrides_db_path) if overrides_db_path else (
        repo_root / "drift_sentinel" / "human_overrides.db"
    )
    cod_path = Path(codification_db_path) if codification_db_path else (
        repo_root / "drift_sentinel" / "codification_proposals.db"
    )

    revenue_map = _sum_revenue_per_entity(ovs_path, window_days)
    override_map = _count_override_touches_per_entity(ov_path, window_days)
    codification_pooled = _count_codification_touches_pooled(cod_path, window_days)

    # Combined entity set: canonical + any extra entities observed in the data.
    seen = set(KNOWN_ENTITIES) | set(revenue_map.keys()) | set(override_map.keys())
    if extra_entities:
        seen |= {e for e in extra_entities if e}
    # Drop the 'unknown' bucket from the panel when it's empty; keep when
    # populated so the operator sees there's untaxonomized traffic.
    if "unknown" in seen and override_map.get("unknown", 0) == 0:
        seen.discard("unknown")

    panel: list[EntityRevenueTouch] = []
    for ent in sorted(seen):
        rev_sum, rev_count = revenue_map.get(ent, (0.0, 0))
        overrides_n = override_map.get(ent, 0)
        # codification touches are pooled, not per-entity (see _count_pooled
        # docstring). We surface the pooled count separately on the response.
        total_touches = overrides_n
        value: Optional[float] = None
        if total_touches > 0 and rev_sum > 0:
            value = round(rev_sum / total_touches, 4)
        note = ""
        if rev_sum == 0 and overrides_n == 0:
            note = "no revenue events + no overrides in window"
        elif rev_sum == 0:
            note = "overrides recorded but no revenue events for this entity"
        elif overrides_n == 0:
            note = "revenue recorded but no overrides for this entity"
        panel.append(EntityRevenueTouch(
            entity=ent,
            window_days=window_days,
            revenue_usd=rev_sum,
            revenue_event_count=rev_count,
            override_touches=overrides_n,
            codification_touches=0,
            total_touches=total_touches,
            value=value,
            note=note,
        ))

    return {
        "window_days": window_days,
        "by_entity": [row.to_dict() for row in panel],
        "codification_touches_pooled": codification_pooled,
        "computed_at": datetime.now(tz=timezone.utc).isoformat(),
        "note": (
            "Revenue side reads outcome_events; touches side reads "
            "human_overrides (source_engine -> entity) + pooled "
            "codification certs. codification_touches_pooled is ecosystem-"
            "wide and not yet entity-attributable."
        ),
    }
