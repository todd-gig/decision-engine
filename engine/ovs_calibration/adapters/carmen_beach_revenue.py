"""CarmenBeachRevenueAdapter — Pub/Sub adapter for PDC revenue events.

Subscribed topic: `outcomes.carmen-beach.revenue`

Expected message shape (JSON):
  {
    "unit_id":            str,        # property unit identifier
    "booking_id":         str,        # used as source_record_id (idempotency)
    "metric":             str,        # default 'revenue.daily.<unit_id>'
    "observed_value":     float,      # USD revenue captured for the day
    "expected_value":     float|null, # optional engine projection
    "observed_at":        str,        # ISO-8601
    "unit":               'usd',
    "extras":             dict        # arbitrary passthrough (channel, etc.)
  }

PDC pricing decisions emit projection.metric in the family
`revenue.daily.<unit_id>` so the attribution daemon's direct stage fires
immediately when the engine sees a same-unit revenue outcome.

penrose_signal: weakens
penrose_dimension: variance | cascade
"""
from __future__ import annotations

from .base import AdapterMessage, EntityAdapterBase


class CarmenBeachRevenueAdapter(EntityAdapterBase):
    """PDC revenue outcomes -> OVS-Calibration outcome stream."""

    entity = "carmen-beach"
    topic_suffix = "revenue"

    def transform(self, raw: dict) -> AdapterMessage:
        if not isinstance(raw, dict):
            raise ValueError("raw message must be a dict")

        unit_id = raw.get("unit_id") or raw.get("property_unit_id") or ""
        booking_id = raw.get("booking_id") or raw.get("source_record_id") or ""

        # Default metric naming aligns with the decision-side projection metric
        # family so direct attribution can fire on first ingest.
        default_metric = (
            f"revenue.daily.{unit_id}" if unit_id else "revenue.daily"
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
        if unit_id and "unit_id" not in extras:
            extras["unit_id"] = unit_id

        return AdapterMessage(
            metric=metric,
            observed_value=observed_value,
            observed_at=raw.get("observed_at") or "",
            source_record_id=booking_id,
            expected_value=expected_value,
            unit=raw.get("unit") or "usd",
            extras=extras,
        )
