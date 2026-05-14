"""Pub/Sub emitter — production transport for override calibration events.

v0.6 deliverable: graduate `calibration_emit.py` from local JSONL to GCP
Pub/Sub so OVS-Calibration can consume override-derived outcomes across
process boundaries. JSONL only works for single-process readers on the
same filesystem; Pub/Sub gives us decoupled fanout to any subscriber.

Behavior:
  - If `topic_path` is set AND `google.cloud.pubsub_v1` imports AND no
    `PUBSUB_EMULATOR_HOST` is in env → real Pub/Sub publish.
  - Otherwise → fall back to the JSONL append-only log used by v0.5.
    This keeps CI green when GCP creds are unavailable AND keeps local
    dev / emulator runs working without code changes.

Topic env var: `OVERRIDE_CALIBRATION_TOPIC` (full projects/X/topics/Y form).

penrose_signal: weakens
penrose_dimension: override_rate
why: Without a real transport, override calibration is a local-fs side
effect that only the same process can read. Pub/Sub makes the override
weight propagate across process boundaries so the OVS variance trend
(Penrose-Falsification signal #4) responds to human corrections within
seconds, not whenever the next shared-filesystem reader scans.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)


# Env vars consulted at runtime, never cached at import time. Tests and
# production both flip these and expect a fresh resolution per call.
TOPIC_ENV_VAR = "OVERRIDE_CALIBRATION_TOPIC"
EMULATOR_ENV_VAR = "PUBSUB_EMULATOR_HOST"


class PubSubEmitter:
    """Publish override calibration events to Pub/Sub (with JSONL fallback).

    Construction is cheap and side-effect-free. The actual `PublisherClient`
    is lazy-loaded on first `.publish()` call so importing this module
    doesn't require GCP creds (critical for CI + offline dev).
    """

    def __init__(
        self,
        topic_path: Optional[str] = None,
        *,
        fallback_log_path: Optional[Path] = None,
    ) -> None:
        # Resolve topic at construction: explicit arg wins, then env var,
        # then None (which triggers fallback mode).
        self.topic_path = topic_path or os.environ.get(TOPIC_ENV_VAR) or None
        self.fallback_log_path = fallback_log_path
        self._publisher = None  # type: ignore[assignment]

        # One-line warning at init so operators see the transport choice.
        # We don't repeat per-publish to keep logs quiet.
        if self.topic_path and not os.environ.get(EMULATOR_ENV_VAR):
            logger.info(
                "[human_override.pubsub_emitter] mode=pubsub topic=%s",
                self._redacted_topic(),
            )
        else:
            reason = (
                "PUBSUB_EMULATOR_HOST set" if os.environ.get(EMULATOR_ENV_VAR)
                else f"{TOPIC_ENV_VAR} unset"
            )
            logger.warning(
                "[human_override.pubsub_emitter] mode=jsonl_fallback "
                "(reason=%s) — calibration events will append to JSONL log",
                reason,
            )

    # ── public surface ──────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """True when this emitter would attempt a real Pub/Sub publish."""
        return bool(self.topic_path) and not os.environ.get(EMULATOR_ENV_VAR)

    def publish(
        self,
        message: dict | Any,
        ordering_key: Optional[str] = None,
    ) -> str:
        """Publish `message` to Pub/Sub (or JSONL fallback).

        Returns the publisher-assigned message_id when Pub/Sub mode is
        active. In fallback mode returns the literal string "jsonl:<path>"
        so the caller can confirm the transport without raising.
        """
        payload = self._to_dict(message)
        if not self.is_configured():
            return self._fallback_publish(payload)

        try:
            publisher = self._get_publisher()
        except Exception as exc:  # pragma: no cover — exercised in mock-mode tests
            logger.warning(
                "[human_override.pubsub_emitter] publisher init failed "
                "(%s) — falling back to JSONL for this event", exc,
            )
            return self._fallback_publish(payload)

        data = json.dumps(payload).encode("utf-8")
        try:
            future = (
                publisher.publish(self.topic_path, data, ordering_key=ordering_key)
                if ordering_key
                else publisher.publish(self.topic_path, data)
            )
            # .result() blocks until publish resolves; we accept that —
            # override flows are user-driven, not high-throughput hot paths.
            message_id = future.result(timeout=10)
            return str(message_id)
        except Exception as exc:
            # Never break the override path. Log + fallback so the row
            # at least lands locally for later replay.
            logger.warning(
                "[human_override.pubsub_emitter] publish failed (%s) — "
                "falling back to JSONL for this event", exc,
            )
            return self._fallback_publish(payload)

    # ── internal helpers ────────────────────────────────────────────────

    def _get_publisher(self):
        """Lazy-load google.cloud.pubsub_v1 + create a PublisherClient.

        Imported inside the function so the module imports without GCP
        creds — critical for CI + offline dev. `google-cloud-pubsub` is
        a soft dependency (pinned in requirements.txt but tolerated if
        absent in narrow test envs).
        """
        if self._publisher is not None:
            return self._publisher
        from google.cloud import pubsub_v1  # type: ignore[import-not-found]
        self._publisher = pubsub_v1.PublisherClient()
        return self._publisher

    def _redacted_topic(self) -> str:
        """Show project + topic shape without exposing full path in logs."""
        tp = self.topic_path or ""
        # projects/PROJ/topics/TOP — keep first 5 chars of PROJ + topic.
        parts = tp.split("/")
        if len(parts) >= 4:
            proj = parts[1][:5] + "…" if len(parts[1]) > 5 else parts[1]
            return f"projects/{proj}/topics/{parts[3]}"
        return "<malformed>"

    def _fallback_publish(self, payload: dict) -> str:
        """Append `payload` to the JSONL fallback log.

        Path resolution: explicit `fallback_log_path` wins, then defer to
        `calibration_emit._default_log_path()` so we land in the same file
        v0.5 wrote to. This keeps existing readers (and v0.5 tests) intact.
        """
        # Late import — avoid circular with calibration_emit which uses us.
        from . import calibration_emit
        path = self.fallback_log_path or calibration_emit._default_log_path()
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except OSError as exc:
            logger.warning(
                "[human_override.pubsub_emitter] fallback JSONL write failed: %s",
                exc,
            )
            return "fallback:write_failed"
        return f"jsonl:{path}"

    @staticmethod
    def _to_dict(message: Any) -> dict:
        if isinstance(message, dict):
            return message
        if is_dataclass(message):
            return asdict(message)
        # Last-resort: assume it's already JSON-serializable via dict()
        try:
            return dict(message)
        except (TypeError, ValueError):
            return {"value": message}


def transport_status() -> dict:
    """Return the current emitter transport state (for /v1/overrides/transport/status).

    Reports redacted topic + fallback path. Never exposes the full topic
    path to clients (info-disclosure surface — projects/X/topics/Y leaks
    GCP project naming convention).
    """
    topic = os.environ.get(TOPIC_ENV_VAR)
    emulator = os.environ.get(EMULATOR_ENV_VAR)
    configured = bool(topic) and not emulator

    # Build a redacted view without instantiating an emitter (no side effects).
    redacted = "<unset>"
    if topic:
        parts = topic.split("/")
        if len(parts) >= 4:
            proj = parts[1][:5] + "…" if len(parts[1]) > 5 else parts[1]
            redacted = f"projects/{proj}/topics/{parts[3]}"
        else:
            redacted = "<malformed>"

    from . import calibration_emit
    return {
        "transport": "pubsub" if configured else "jsonl_fallback",
        "pubsub_configured": configured,
        "topic_redacted": redacted,
        "fallback_log_path": str(calibration_emit._default_log_path()),
        "emulator_in_use": bool(emulator),
    }
