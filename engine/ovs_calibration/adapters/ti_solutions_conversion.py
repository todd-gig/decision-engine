"""TiSolutionsConversionAdapter — Pub/Sub adapter for Ti Solutions conversions.

Subscribed topic: `outcomes.ti-solutions.conversion`

Expected message shape (HubSpot-style conversion event JSON):
  {
    "deal_id":             str,        # used as source_record_id
    "deal_stage":          str,        # 'qualified' | 'closed_won' | 'closed_lost' | ...
    "metric":              str,        # default 'conversion.<deal_stage>'
    "observed_value":      float,      # 1.0 / 0.0 — whether the conversion happened
    "expected_value":      float|null,
    "observed_at":         str,        # ISO-8601 (stage transition timestamp)
    "deal_amount_usd":     float|null,
    "extras":              dict
  }

Ti Solutions decision-engine projections target metrics in the
`conversion.<stage>` family (e.g., `conversion.closed_won`, `conversion.qualified`)
so the attribution daemon's direct stage fires on stage-transition events.

penrose_signal: weakens
penrose_dimension: variance | cascade
"""
from __future__ import annotations

from .base import AdapterMessage, EntityAdapterBase


class TiSolutionsConversionAdapter(EntityAdapterBase):
    """Ti Solutions conversion outcomes -> OVS-Calibration outcome stream."""

    entity = "ti-solutions"
    topic_suffix = "conversion"

    def transform(self, raw: dict) -> AdapterMessage:
        if not isinstance(raw, dict):
            raise ValueError("raw message must be a dict")

        deal_id = raw.get("deal_id") or raw.get("source_record_id") or ""
        deal_stage = raw.get("deal_stage") or raw.get("stage") or ""

        default_metric = (
            f"conversion.{deal_stage}" if deal_stage else "conversion"
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
        if deal_stage and "deal_stage" not in extras:
            extras["deal_stage"] = deal_stage
        if raw.get("deal_amount_usd") is not None:
            extras["deal_amount_usd"] = raw["deal_amount_usd"]

        return AdapterMessage(
            metric=metric,
            observed_value=observed_value,
            observed_at=raw.get("observed_at") or "",
            source_record_id=deal_id,
            expected_value=expected_value,
            unit=raw.get("unit") or "rate",
            extras=extras,
        )
