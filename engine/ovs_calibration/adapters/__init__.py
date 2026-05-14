"""Per-entity Pub/Sub adapters for OVS-Calibration outcome ingestion.

Each adapter:
  - subscribes to a canonical Pub/Sub topic `outcomes.<entity>.<metric>`
    (spec §Ingestion pipeline line 70)
  - transforms an incoming message into an OutcomeEvent
  - validates against the OutcomeSource schema (if registered)
  - calls `ingest_outcome(...)` to persist + trigger attribution

Lazy-import `google.cloud.pubsub_v1` per the override-engine + ai_router
pattern — the import only happens inside `run_subscriber()`. Importing this
package at startup must NOT pull in pubsub libs.

Each adapter exposes:
  - subscription_path:  canonical subscription path (project/topic-scoped)
  - run_subscriber(blocking: bool = False): start the subscriber loop
  - status(): per-adapter health for the /v1/calibration/adapters/status route

Fallback contract: when GCP_PROJECT / subscription is unconfigured, the
adapter MUST log + return immediately rather than raising. This is what
makes local dev + CI test runs no-op safely.

penrose_signal: weakens
penrose_dimension: variance | cascade
"""
from __future__ import annotations

from .base import (
    EntityAdapterBase,
    AdapterStatus,
    AdapterMessage,
    IngestionResult,
    ingest_outcome,
)
from .carmen_beach_revenue import CarmenBeachRevenueAdapter
from .ti_solutions_conversion import TiSolutionsConversionAdapter
from .gigaton_ui_usage import GigatonUIUsageAdapter


def all_adapters() -> list[EntityAdapterBase]:
    """Return one instance of each registered adapter.

    Instances are cheap (no GCP I/O at construction); the caller can
    cherry-pick + call run_subscriber() on the ones they want active.
    """
    return [
        CarmenBeachRevenueAdapter(),
        TiSolutionsConversionAdapter(),
        GigatonUIUsageAdapter(),
    ]


__all__ = [
    "EntityAdapterBase",
    "AdapterStatus",
    "AdapterMessage",
    "IngestionResult",
    "ingest_outcome",
    "CarmenBeachRevenueAdapter",
    "TiSolutionsConversionAdapter",
    "GigatonUIUsageAdapter",
    "all_adapters",
]
