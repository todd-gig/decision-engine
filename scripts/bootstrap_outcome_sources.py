"""bootstrap_outcome_sources — idempotent registration of canonical OutcomeSources.

WHAT: Registers three canonical outcome sources (PDC STVR revenue,
Ti Solutions HubSpot conversions, Gigaton-UI feature usage) in the
ovs_calibration.outcome_sources table. Each source carries its schema,
decision_class_metric_map, and Pub/Sub ingestion contract.

WHY: The Penrose scoreboard metric #7 (`revenue_per_human_touch`) has a
real human-touch counter shipping today, but the numerator (revenue
ingested through OVS-Calibration) requires real OutcomeSources to be
registered before any adapter event is attributable. Registering these
three sources is the operator action that lights up the metric the
moment a real CSV (or live Pub/Sub event) is provided. Per
penrose_falsification_doctrine.md §Scoreboard item 7 + Non-Negotiable #6
(never synthesize data), the engine refuses to fabricate; this script
makes the data path real, not the data itself.

WHERE: Writes to `<repo>/drift_sentinel/ovs_calibration.db` via
`engine.ovs_calibration.sources.register_source(...)`. Idempotent by
`(name, entity)` — re-running never duplicates.

WHEN: Two entry points:
  1. CLI: `python cli.py bootstrap-sources [--all | --source NAME] [--dry-run]`
  2. Startup: when env `PENROSE_BOOTSTRAP_SOURCES=1` is set, the FastAPI
     app calls `bootstrap_all(idempotent=True)` at startup.
Defaults are off so dev/test runs never auto-write.

HOW: Each canonical source is described in CANONICAL_SOURCES below as a
SourceSpec dataclass; `bootstrap_one(name, ...)` materializes one;
`bootstrap_all(...)` materializes all three. Existence is checked via
`list_sources(entity=...)` matched by name; an existing row is returned
as-is (status=`already_registered`).

CONTEXT: This script is the bridge between the OutcomeSources registry
shipped in v0.5 + the per-entity adapters shipped in v0.6. Without it,
operators had to hit `/v1/calibration/sources` three times manually with
hand-crafted JSON. With it, one CLI invocation seeds the canonical set.

penrose_signal: weakens
penrose_dimension: revenue_per_human_touch
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

from engine.ovs_calibration import (
    OutcomeSource,
    list_sources,
    register_source,
)


# ── Canonical source specs ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceSpec:
    """Frozen specification of one canonical OutcomeSource.

    WHY frozen: these are doctrine-level facts about the ecosystem; the
    canonical set should not be mutated by accident at runtime. Operators
    add new sources via the API, not by editing this list at runtime.
    """
    name: str
    kind: str
    entity: str
    ingestion_contract: str
    owner: str
    decision_class_metric_map: dict
    schema: dict


# PDC STVR revenue stream.
#   topic = outcomes.carmen-beach.revenue (canonical, matches CarmenBeachRevenueAdapter)
#   booking_id is the idempotency key for backfill operations
CARMEN_BEACH_REVENUE = SourceSpec(
    name="carmen-beach-revenue",
    kind="revenue",
    entity="carmen-beach",
    ingestion_contract="pubsub",
    owner="todd@gigaton.ai",
    decision_class_metric_map={
        "pricing.dynamic.carmen-beach": "revenue.daily.unit",
        "pricing.adr.carmen-beach":     "revenue.adr.unit",
    },
    schema={
        "type": "object",
        "required": ["booking_id", "unit_id", "check_in", "check_out", "gross_usd"],
        "properties": {
            "booking_id": {"type": "string", "description": "Idempotency key"},
            "unit_id":    {"type": "string", "description": "STVR property unit identifier"},
            "check_in":   {"type": "string", "format": "date"},
            "check_out":  {"type": "string", "format": "date"},
            "gross_usd":  {"type": "number", "minimum": 0},
            "net_usd":    {"type": "number", "minimum": 0},
            "channel":    {"type": "string", "description": "Airbnb/VRBO/Direct/etc."},
        },
    },
)


# Ti Solutions HubSpot conversion stream.
#   topic = outcomes.ti-solutions.conversion
TI_SOLUTIONS_CONVERSION = SourceSpec(
    name="ti-solutions-conversion",
    kind="conversion",
    entity="ti-solutions",
    ingestion_contract="pubsub",
    owner="todd@gigaton.ai",
    decision_class_metric_map={
        "lead.qualification.ti-solutions": "conversion.qualified",
        "lead.close.ti-solutions":         "conversion.closed_won",
    },
    schema={
        "type": "object",
        "required": ["deal_id", "stage", "transitioned_at"],
        "properties": {
            "deal_id":         {"type": "string", "description": "HubSpot deal id"},
            "contact_id":      {"type": "string"},
            "stage":           {"type": "string", "description": "HubSpot pipeline stage"},
            "value_usd":       {"type": "number", "minimum": 0},
            "transitioned_at": {"type": "string", "format": "date-time"},
        },
    },
)


# Gigaton-UI feature usage stream.
#   topic = outcomes.gigaton-ui.usage
GIGATON_UI_USAGE = SourceSpec(
    name="gigaton-ui-usage",
    kind="operational",
    entity="gigaton-ui",
    ingestion_contract="pubsub",
    owner="todd@gigaton.ai",
    decision_class_metric_map={
        "feature.adoption.gigaton-ui":       "usage.feature_engaged",
        "onboarding.completion.gigaton-ui":  "usage.wizard_completed",
    },
    schema={
        "type": "object",
        "required": ["user_id", "feature", "event", "occurred_at"],
        "properties": {
            "user_id":     {"type": "string"},
            "feature":     {"type": "string"},
            "event":       {"type": "string"},
            "occurred_at": {"type": "string", "format": "date-time"},
        },
    },
)


CANONICAL_SOURCES: dict[str, SourceSpec] = {
    CARMEN_BEACH_REVENUE.name:     CARMEN_BEACH_REVENUE,
    TI_SOLUTIONS_CONVERSION.name:  TI_SOLUTIONS_CONVERSION,
    GIGATON_UI_USAGE.name:         GIGATON_UI_USAGE,
}


# ── Result shape ────────────────────────────────────────────────────────────


@dataclass
class BootstrapResult:
    """Per-source result; aggregated by bootstrap_all().

    status:
      - 'registered'           — new row written to outcome_sources
      - 'already_registered'   — row matched by (name, entity); reused
      - 'dry_run'              — would-be intent; nothing written
      - 'skipped'              — explicitly skipped (e.g., unknown name)
    """
    name: str
    entity: str
    status: str
    source_id: Optional[str] = None
    body: Optional[dict] = None
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "entity": self.entity,
            "status": self.status,
            "source_id": self.source_id,
            "body": self.body,
            "reasoning": self.reasoning,
        }


# ── Idempotency check ───────────────────────────────────────────────────────


def _find_existing(spec: SourceSpec, *, db_path: Optional[str] = None) -> Optional[dict]:
    """Match an existing row by (name, entity).

    WHY (name, entity): `name` alone could collide across entities;
    `(name, entity)` is the natural composite key. The registry table
    doesn't enforce uniqueness, so we lookup + dedupe here.
    """
    existing = list_sources(entity=spec.entity, db_path=db_path)
    for row in existing:
        if row.get("name") == spec.name:
            return row
    return None


# ── bootstrap_one / bootstrap_all ───────────────────────────────────────────


def bootstrap_one(
    name: str,
    *,
    dry_run: bool = False,
    db_path: Optional[str] = None,
) -> BootstrapResult:
    """Register one canonical source by name. Idempotent.

    Returns a BootstrapResult; never raises on a successful idempotent
    re-run. Raises KeyError when `name` is not a canonical source.
    """
    if name not in CANONICAL_SOURCES:
        raise KeyError(
            f"unknown canonical source {name!r}; "
            f"valid: {sorted(CANONICAL_SOURCES)}"
        )
    spec = CANONICAL_SOURCES[name]

    existing = _find_existing(spec, db_path=db_path)
    if existing is not None:
        return BootstrapResult(
            name=spec.name,
            entity=spec.entity,
            status="already_registered",
            source_id=existing.get("id"),
            body=existing,
            reasoning=(
                f"source (name={spec.name!r}, entity={spec.entity!r}) "
                f"already present; idempotent no-op"
            ),
        )

    if dry_run:
        return BootstrapResult(
            name=spec.name,
            entity=spec.entity,
            status="dry_run",
            source_id=None,
            body={
                "name":                       spec.name,
                "kind":                       spec.kind,
                "entity":                     spec.entity,
                "ingestion_contract":         spec.ingestion_contract,
                "owner":                      spec.owner,
                "decision_class_metric_map":  spec.decision_class_metric_map,
                "schema":                     spec.schema,
            },
            reasoning="dry-run: would register canonical source",
        )

    src = OutcomeSource(
        name=spec.name,
        kind=spec.kind,
        entity=spec.entity,
        ingestion_contract=spec.ingestion_contract,
        schema=dict(spec.schema),
        owner=spec.owner,
        health_status="unknown",
        decision_class_metric_map=dict(spec.decision_class_metric_map),
    )
    body = register_source(src, db_path=db_path)
    return BootstrapResult(
        name=spec.name,
        entity=spec.entity,
        status="registered",
        source_id=body.get("id"),
        body=body,
        reasoning=(
            f"registered new canonical source for entity={spec.entity!r} "
            f"kind={spec.kind!r} via {spec.ingestion_contract!r}"
        ),
    )


def bootstrap_all(
    *,
    idempotent: bool = True,
    dry_run: bool = False,
    db_path: Optional[str] = None,
) -> list[BootstrapResult]:
    """Register every canonical source. Idempotent by default.

    `idempotent=True` is the only currently supported mode; the parameter
    is reserved so future callers can opt into stricter behavior (e.g.
    raise on duplicate). Re-running yields `already_registered` rows.
    """
    if not idempotent:
        raise ValueError(
            "non-idempotent bootstrap not supported; the canonical set is "
            "always (name, entity)-deduped"
        )
    results: list[BootstrapResult] = []
    for name in CANONICAL_SOURCES:
        results.append(bootstrap_one(name, dry_run=dry_run, db_path=db_path))
    return results


# ── CLI ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_outcome_sources",
        description=(
            "Idempotently register canonical OutcomeSources "
            "(PDC revenue, Ti Solutions conversions, Gigaton-UI usage)"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all", action="store_true",
        help="Register all canonical sources",
    )
    group.add_argument(
        "--source",
        choices=sorted(CANONICAL_SOURCES.keys()),
        help="Register a single canonical source by name",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print would-be intent; never writes",
    )
    parser.add_argument(
        "--db-path", default=None,
        help="Override path to ovs_calibration.db (default repo location)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.all:
        results = bootstrap_all(idempotent=True, dry_run=args.dry_run, db_path=args.db_path)
    else:
        results = [bootstrap_one(args.source, dry_run=args.dry_run, db_path=args.db_path)]

    print(json.dumps(
        {
            "count": len(results),
            "dry_run": bool(args.dry_run),
            "results": [r.to_dict() for r in results],
        },
        indent=2,
        default=str,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via cli.py + tests
    sys.exit(main())
