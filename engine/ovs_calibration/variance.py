"""Variance computer — observed vs expected from decision certificates.

Per outcome_calibration_engine_spec.md §Variance computation. Pulls
`projection.expected_value` from the decision certificate, observed value
from the outcome event, and computes:
  - proportional metrics (pricing, conversion, revenue):
        variance = (observed - expected) / expected
  - absolute metrics (NPS, count, raw operational signal):
        variance = observed - expected

The per-class config lives in `config/engine.yaml::variance_metric_kinds`
with a sane proportional default — see _metric_kind() for the fallback rules.

WHY: variance is the rawest, hardest-edge measurement of "did the decision
predict correctly?". A single canonical computer keeps every calibration
revision and codification-candidate score comparable across decision classes.

penrose_signal: weakens
penrose_dimension: variance
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ─────────────────────────────────────────────
# Config — metric-kind lookup
# ─────────────────────────────────────────────

# Default: proportional. Absolute metrics must be explicitly listed because
# proportional-as-default avoids hidden divide-by-zero asymmetries when the
# expected value is small. The lists below seed the v0.5 set; ops can add
# more via config/engine.yaml without code changes.
DEFAULT_ABSOLUTE_KEYWORDS = (
    "nps",
    "count",
    "tickets",
    "incidents",
    "headcount",
    "latency_ms",
)

DEFAULT_PROPORTIONAL_KEYWORDS = (
    "revenue",
    "occupancy",
    "conversion",
    "price",
    "margin",
    "rate",
    "ratio",
    "pct",
)


class MetricKind(str, Enum):
    PROPORTIONAL = "proportional"  # (observed - expected) / |expected|
    ABSOLUTE = "absolute"          # observed - expected
    UNKNOWN = "unknown"            # treat as proportional but flag


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────


@dataclass
class DecisionProjection:
    """Subset of a decision certificate this computer reads.

    Mirrors the projection block defined in outcome_calibration_engine_spec.md
    §Consumer integration. Kept as a dataclass (not a Pydantic) so this module
    doesn't pull FastAPI into the variance path.
    """
    metric: str
    expected_value: float
    horizon_days: int = 0
    confidence: float = 0.0


@dataclass
class DecisionCertificateLike:
    """Minimal certificate-shaped input.

    Real callers pass either an existing engine.models.Certificate (with a
    projection attribute added in v0.6+) or this lightweight stand-in.
    """
    decision_certificate_id: str
    decision_class: str
    projection: DecisionProjection
    issued_at: str = ""


@dataclass
class OutcomeEventLike:
    """Minimal outcome-event shape needed for variance.

    Independent of storage layer to keep variance pure-function.
    """
    id: str
    metric: str
    observed_value: float
    observed_at: str = ""
    source: str = ""
    expected_value: Optional[float] = None


@dataclass
class VarianceResult:
    """Result of computing variance for one (decision, outcome) pair."""
    decision_certificate_id: str
    outcome_event_id: str
    expected_value: float
    observed_value: float
    raw_diff: float              # observed - expected (always signed)
    variance: float              # per-kind interpretation
    variance_pct: float          # variance expressed as decimal fraction
    direction: str               # "positive" | "negative" | "neutral"
    metric_kind: str             # MetricKind value
    computation_version: str = "v0.5"
    computed_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    notes: str = ""


# ─────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────


def compute_variance(
    decision_certificate: DecisionCertificateLike,
    outcome_event: OutcomeEventLike,
    *,
    metric_kind_override: str | None = None,
    neutral_band_pct: float = 0.10,
) -> VarianceResult:
    """Compute the variance between a decision's projection and an outcome.

    Args:
        decision_certificate: certificate-shaped object with a `.projection`
        outcome_event: outcome-shaped object with a `.observed_value`
        metric_kind_override: force "proportional" or "absolute" regardless
            of name-based inference
        neutral_band_pct: |variance_pct| below this is "neutral" (default ±10%)

    Returns: VarianceResult — the row a calibration revision can write
    against.

    Raises: ValueError if the certificate's projection metric does not match
    the outcome's metric (caller's responsibility to attribute correctly).
    """
    proj = decision_certificate.projection
    if proj.metric != outcome_event.metric:
        raise ValueError(
            f"projection metric {proj.metric!r} != outcome metric "
            f"{outcome_event.metric!r}; cannot compute variance across "
            f"mismatched metrics"
        )

    kind = (
        MetricKind(metric_kind_override)
        if metric_kind_override
        else _metric_kind(proj.metric)
    )

    expected = float(proj.expected_value)
    observed = float(outcome_event.observed_value)
    raw_diff = observed - expected

    if kind == MetricKind.ABSOLUTE:
        variance = raw_diff
        # For ABSOLUTE metrics, variance_pct is informational; computed
        # over |expected| if non-zero so the neutral-band still works.
        variance_pct = (
            raw_diff / abs(expected) if expected != 0 else (1.0 if observed != 0 else 0.0)
        )
    else:
        # PROPORTIONAL (and UNKNOWN, which we treat as proportional but flag)
        if expected == 0:
            # Zero expectation with non-zero observation is +100% by
            # convention; matches learning_loop.py:140-141.
            variance_pct = 1.0 if observed > 0 else (-1.0 if observed < 0 else 0.0)
            variance = variance_pct
        else:
            variance_pct = raw_diff / abs(expected)
            variance = variance_pct

    if variance_pct > neutral_band_pct:
        direction = "positive"
    elif variance_pct < -neutral_band_pct:
        direction = "negative"
    else:
        direction = "neutral"

    notes = ""
    if kind == MetricKind.UNKNOWN:
        notes = (
            f"metric {proj.metric!r} did not match any configured kind; "
            f"defaulted to proportional"
        )

    return VarianceResult(
        decision_certificate_id=decision_certificate.decision_certificate_id,
        outcome_event_id=outcome_event.id,
        expected_value=expected,
        observed_value=observed,
        raw_diff=raw_diff,
        variance=variance,
        variance_pct=variance_pct,
        direction=direction,
        metric_kind=kind.value,
        notes=notes,
    )


# ─────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────


def _metric_kind(metric_name: str) -> MetricKind:
    """Infer metric kind from the metric name.

    Lookup precedence:
      1. config/engine.yaml::variance_metric_kinds (explicit per-class map)
      2. Built-in absolute-keyword match (count/nps/etc.)
      3. Built-in proportional-keyword match (revenue/conversion/etc.)
      4. UNKNOWN — caller may override
    """
    explicit = _load_explicit_kinds().get(metric_name)
    if explicit in ("proportional", "absolute"):
        return MetricKind(explicit)

    lowered = metric_name.lower()
    for kw in DEFAULT_ABSOLUTE_KEYWORDS:
        if kw in lowered:
            return MetricKind.ABSOLUTE
    for kw in DEFAULT_PROPORTIONAL_KEYWORDS:
        if kw in lowered:
            return MetricKind.PROPORTIONAL
    return MetricKind.UNKNOWN


_EXPLICIT_KINDS_CACHE: dict[str, str] | None = None


def _load_explicit_kinds() -> dict[str, str]:
    """Lazy-load config/engine.yaml::variance_metric_kinds.

    Returns {} if the file is absent or the key isn't present. We cache
    after first read because variance is called per-attribution and we
    don't want a YAML hit per call.
    """
    global _EXPLICIT_KINDS_CACHE
    if _EXPLICIT_KINDS_CACHE is not None:
        return _EXPLICIT_KINDS_CACHE
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        _EXPLICIT_KINDS_CACHE = {}
        return _EXPLICIT_KINDS_CACHE

    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(here))
    config_path = os.path.join(repo_root, "config", "engine.yaml")
    if not os.path.exists(config_path):
        _EXPLICIT_KINDS_CACHE = {}
        return _EXPLICIT_KINDS_CACHE

    with open(config_path, "r") as f:
        data: Any = yaml.safe_load(f) or {}
    kinds = data.get("variance_metric_kinds") or {}
    if not isinstance(kinds, dict):
        kinds = {}
    _EXPLICIT_KINDS_CACHE = {str(k): str(v) for k, v in kinds.items()}
    return _EXPLICIT_KINDS_CACHE


def reset_metric_kind_cache() -> None:
    """Test helper — clear the cached YAML kinds table."""
    global _EXPLICIT_KINDS_CACHE
    _EXPLICIT_KINDS_CACHE = None
