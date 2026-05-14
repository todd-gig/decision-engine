"""GigatonUIUsageAdapter — Pub/Sub adapter for Gigaton-UI feature usage.

Subscribed topic: `outcomes.gigaton-ui.usage`

Expected message shape (feature usage event JSON):
  {
    "user_id":            str,
    "org_id":             str,
    "feature":            str,        # e.g., 'capability.preview', 'wizard.step.3'
    "event_id":           str,        # used as source_record_id (idempotency)
    "metric":             str,        # default 'usage.<feature>'
    "observed_value":     float,      # count / duration_ms / count of clicks
    "expected_value":     float|null,
    "observed_at":        str,        # ISO-8601
    "kind":               str,        # 'count' | 'latency_ms' | 'nps' — guides metric_kind
    "extras":             dict
  }

Gigaton-UI emits feature-level usage outcomes that decisions like rollout
gating, capability tier unlocks, and gamification thresholds project against.

penrose_signal: weakens
penrose_dimension: variance | cascade
"""
from __future__ import annotations

from .base import AdapterMessage, EntityAdapterBase


class GigatonUIUsageAdapter(EntityAdapterBase):
    """Gigaton-UI usage outcomes -> OVS-Calibration outcome stream."""

    entity = "gigaton-ui"
    topic_suffix = "usage"

    def transform(self, raw: dict) -> AdapterMessage:
        if not isinstance(raw, dict):
            raise ValueError("raw message must be a dict")

        feature = raw.get("feature") or ""
        event_id = raw.get("event_id") or raw.get("source_record_id") or ""

        default_metric = (
            f"usage.{feature}" if feature else "usage"
        )
        metric = raw.get("metric") or default_metric

        observed_value = raw.get("observed_value")
        if observed_value is None:
            raise ValueError("observed_value is required")
        try:
            observed_value = float(observed_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"observed_value must be numeric; got {observed_value!r}"
            ) from exc

        expected_value = raw.get("expected_value")
        if expected_value is not None:
            try:
                expected_value = float(expected_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"expected_value must be numeric or null; got {expected_value!r}"
                ) from exc

        extras = dict(raw.get("extras") or {})
        for k in ("user_id", "org_id", "feature", "kind"):
            v = raw.get(k)
            if v is not None and k not in extras:
                extras[k] = v

        # Default unit guides downstream variance kind inference (the
        # variance computer also keyword-matches `count` / `latency_ms` /
        # `nps` against DEFAULT_ABSOLUTE_KEYWORDS — keeping the unit aligned
        # makes that automatic).
        unit = raw.get("unit") or raw.get("kind") or "count"

        return AdapterMessage(
            metric=metric,
            observed_value=observed_value,
            observed_at=raw.get("observed_at") or "",
            source_record_id=event_id,
            expected_value=expected_value,
            unit=unit,
            extras=extras,
        )
