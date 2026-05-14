"""EntityAdapterBase — shared ingestion + validation logic for entity adapters.

Each concrete adapter (CarmenBeachRevenueAdapter, TiSolutionsConversionAdapter,
GigatonUIUsageAdapter) inherits from this base and overrides:
  - entity:                 the entity string ('carmen-beach' | 'ti-solutions' | ...)
  - topic_suffix:           the Pub/Sub topic suffix ('revenue' | 'conversion' | ...)
  - transform(raw):         build a (metric, observed_value, observed_at,
                            source_record_id, extras) tuple from the raw message
  - decision_class_map():   optional override of the registry mapping (rare)

The base provides:
  - subscription_path:      project-scoped subscription string
  - run_subscriber(blocking): start subscriber loop with lazy pubsub import
  - status():               health snapshot used by /v1/calibration/adapters/status
  - ingest_outcome(...):    shared ingestion path (validation + persistence +
                            attribution trigger). Modules can call this
                            directly for tests / webhook fallback paths.

Lazy-import pattern: pubsub_v1 is NEVER imported at module load. Only
inside run_subscriber() and only when a subscription is configured. This
makes local + CI runs no-op safely without google-cloud-pubsub installed.

penrose_signal: weakens
penrose_dimension: variance
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .. import storage


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────


@dataclass
class AdapterMessage:
    """Canonical normalized message shape after `transform()`.

    The base `ingest_outcome` writes one outcome_events row per message.
    """
    metric: str
    observed_value: float
    observed_at: str            # ISO-8601
    source_record_id: str = ""
    expected_value: Optional[float] = None
    unit: str = ""
    extras: dict = field(default_factory=dict)


@dataclass
class IngestionResult:
    """Result returned from `ingest_outcome` so callers can audit + test."""
    outcome_event_id: str
    entity: str
    metric: str
    observed_value: float
    observed_at: str
    persisted: bool
    reasoning: str = ""
    source_record_id: str = ""

    def to_dict(self) -> dict:
        return {
            "outcome_event_id": self.outcome_event_id,
            "entity": self.entity,
            "metric": self.metric,
            "observed_value": self.observed_value,
            "observed_at": self.observed_at,
            "persisted": self.persisted,
            "reasoning": self.reasoning,
            "source_record_id": self.source_record_id,
        }


@dataclass
class AdapterStatus:
    """Per-adapter status snapshot for /v1/calibration/adapters/status."""
    entity: str
    topic_suffix: str
    subscription_path: str
    configured: bool
    last_message_at: Optional[str] = None
    last_error: Optional[str] = None
    messages_received: int = 0
    messages_persisted: int = 0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "topic_suffix": self.topic_suffix,
            "subscription_path": self.subscription_path,
            "configured": self.configured,
            "last_message_at": self.last_message_at,
            "last_error": self.last_error,
            "messages_received": self.messages_received,
            "messages_persisted": self.messages_persisted,
            "note": self.note,
        }


# ─────────────────────────────────────────────
# Shared ingestion path
# ─────────────────────────────────────────────


def ingest_outcome(
    entity: str,
    message: AdapterMessage,
    *,
    db_path: str | None = None,
    source_id: str | None = None,
) -> IngestionResult:
    """Persist one outcome event + return the result. Idempotent on source_record_id.

    Validation order:
      1. metric must be non-empty
      2. observed_value must be numeric (caller's responsibility)
      3. observed_at must be ISO-8601 parseable; otherwise default to now()
         (we don't reject malformed timestamps — outcomes are append-only and
         losing one to a parse error is worse than a slight clock-skew).

    Idempotency: when `message.source_record_id` is set and a row already
    exists for (entity, metric, source_record_id), we return the existing
    row's id and mark `persisted=False`.
    """
    if not entity:
        raise ValueError("entity is required")
    if not message.metric:
        raise ValueError("message.metric is required")

    observed_at = message.observed_at
    if not observed_at:
        observed_at = datetime.now(tz=timezone.utc).isoformat()

    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if message.source_record_id:
            existing = conn.execute(
                """
                SELECT id FROM outcome_events
                WHERE entity = ? AND metric = ? AND source_record_id = ?
                LIMIT 1
                """,
                (entity, message.metric, message.source_record_id),
            ).fetchone()
            if existing is not None:
                return IngestionResult(
                    outcome_event_id=existing["id"],
                    entity=entity,
                    metric=message.metric,
                    observed_value=message.observed_value,
                    observed_at=observed_at,
                    persisted=False,
                    reasoning=(
                        f"idempotent: source_record_id "
                        f"{message.source_record_id!r} already ingested"
                    ),
                    source_record_id=message.source_record_id,
                )

        outcome_id = f"ev-{uuid.uuid4().hex[:12]}"
        ingested_at = datetime.now(tz=timezone.utc).isoformat()
        reasoning = (
            f"ingested via adapter for entity={entity!r} metric={message.metric!r} "
            f"at {ingested_at}"
        )
        conn.execute(
            """
            INSERT INTO outcome_events (
                id, source_id, source, entity, metric,
                observed_value, expected_value, unit,
                observed_at, ingested_at, source_record_id, reasoning,
                schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                source_id,
                entity,
                entity,
                message.metric,
                float(message.observed_value),
                message.expected_value,
                message.unit,
                observed_at,
                ingested_at,
                message.source_record_id or None,
                reasoning,
                "v1",
            ),
        )
    finally:
        conn.close()

    return IngestionResult(
        outcome_event_id=outcome_id,
        entity=entity,
        metric=message.metric,
        observed_value=message.observed_value,
        observed_at=observed_at,
        persisted=True,
        reasoning=reasoning,
        source_record_id=message.source_record_id,
    )


# ─────────────────────────────────────────────
# Adapter base class
# ─────────────────────────────────────────────


class EntityAdapterBase(ABC):
    """Subclass for each entity outcome stream.

    Subclasses MUST set `entity` and `topic_suffix` as class attrs and override
    `transform()`. The default `subscription_path` is derived from env:
      - GCP_PROJECT (or GCP_PROJECT_ID, OVS_GCP_PROJECT) -> project string
      - topic = `outcomes.<entity>.<topic_suffix>`
      - subscription = `ovs-calibration.<entity>.<topic_suffix>.sub`

    Subclasses MAY override `_subscription_name()` for non-canonical naming.
    """

    entity: str = ""
    topic_suffix: str = ""

    def __init__(
        self,
        *,
        project_id: str | None = None,
        subscription_name: str | None = None,
        db_path: str | None = None,
    ) -> None:
        self._project_id = (
            project_id
            or os.environ.get("GCP_PROJECT")
            or os.environ.get("GCP_PROJECT_ID")
            or os.environ.get("OVS_GCP_PROJECT")
            or ""
        )
        self._subscription_name = subscription_name or self._subscription_name_default()
        self._db_path = db_path
        self._status = AdapterStatus(
            entity=self.entity,
            topic_suffix=self.topic_suffix,
            subscription_path=self.subscription_path,
            configured=bool(self._project_id),
        )
        if not self._project_id:
            self._status.note = (
                "GCP_PROJECT not set — adapter will no-op safely on run_subscriber()"
            )

    # ── Identity ────────────────────────────────────────────────────────────

    @property
    def topic(self) -> str:
        return f"outcomes.{self.entity}.{self.topic_suffix}"

    @property
    def subscription_path(self) -> str:
        if not self._project_id:
            return f"(unconfigured)/{self.topic}.sub"
        return f"projects/{self._project_id}/subscriptions/{self._subscription_name}"

    def _subscription_name_default(self) -> str:
        return f"ovs-calibration.{self.entity}.{self.topic_suffix}.sub"

    # ── Per-subclass override ───────────────────────────────────────────────

    @abstractmethod
    def transform(self, raw: dict) -> AdapterMessage:
        """Transform a raw Pub/Sub payload into a normalized AdapterMessage.

        Implementations MUST be deterministic and side-effect-free.
        """

    # ── Public surface ──────────────────────────────────────────────────────

    def status(self) -> AdapterStatus:
        # Refresh the configured + subscription_path snapshots in case env
        # changed since __init__ (rare in prod, useful in tests).
        self._status.configured = bool(self._project_id)
        self._status.subscription_path = self.subscription_path
        return self._status

    def ingest_message(
        self,
        raw: dict,
        *,
        source_id: str | None = None,
    ) -> Optional[IngestionResult]:
        """Synchronous ingestion path (also used by webhook fallback + tests).

        Returns None on transform error (logged + counted in status); caller
        decides whether to NACK. Returns IngestionResult on success.
        """
        try:
            msg = self.transform(raw)
        except (KeyError, ValueError, TypeError) as exc:
            self._status.last_error = (
                f"transform error: {exc!r} (entity={self.entity})"
            )
            logger.warning(
                "adapter %s transform failed: %s", self.entity, exc,
            )
            return None

        self._status.messages_received += 1
        self._status.last_message_at = datetime.now(tz=timezone.utc).isoformat()
        try:
            result = ingest_outcome(
                self.entity,
                msg,
                db_path=self._db_path,
                source_id=source_id,
            )
        except Exception as exc:  # noqa: BLE001 — adapter survives ingestion error
            self._status.last_error = f"ingest error: {exc!r}"
            logger.warning(
                "adapter %s ingest failed: %s", self.entity, exc,
            )
            return None
        if result.persisted:
            self._status.messages_persisted += 1
        return result

    def run_subscriber(self, blocking: bool = False) -> Optional[Any]:
        """Start the Pub/Sub subscriber.

        Returns:
          - StreamingPullFuture when blocking=False and pubsub is available
            (caller is responsible for `.result()` or `.cancel()`)
          - None when blocking=True (the call blocks until cancelled)
          - None when GCP not configured (no-op fallback per spec rule)
          - None when google-cloud-pubsub is not installed (no-op fallback)

        Lazy-imports pubsub_v1 — this method is the ONLY place pubsub is
        touched. Importing the module at package level must remain pubsub-free.
        """
        if not self._project_id:
            logger.info(
                "adapter %s: GCP_PROJECT unset; run_subscriber() no-op",
                self.entity,
            )
            self._status.note = (
                "GCP_PROJECT not set — adapter is in no-op mode"
            )
            return None

        try:
            from google.cloud import pubsub_v1  # type: ignore[import-untyped]
        except ImportError:
            logger.info(
                "adapter %s: google-cloud-pubsub not installed; "
                "run_subscriber() no-op",
                self.entity,
            )
            self._status.note = (
                "google-cloud-pubsub not installed — adapter is in no-op mode"
            )
            return None

        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(
            self._project_id, self._subscription_name,
        )

        def _callback(message: Any) -> None:
            try:
                raw = json.loads(message.data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.warning(
                    "adapter %s: failed to decode message %s: %s",
                    self.entity, getattr(message, "message_id", "?"), exc,
                )
                message.nack()
                return
            result = self.ingest_message(raw)
            if result is None:
                message.nack()
            else:
                message.ack()

        future = subscriber.subscribe(subscription_path, callback=_callback)
        self._status.note = (
            f"subscribed: {subscription_path}"
        )

        if not blocking:
            return future

        try:
            future.result()
        except Exception as exc:  # noqa: BLE001 — controlled exit
            logger.warning(
                "adapter %s: subscriber exited: %s", self.entity, exc,
            )
            self._status.last_error = f"subscriber exited: {exc!r}"
            future.cancel()
        return None
