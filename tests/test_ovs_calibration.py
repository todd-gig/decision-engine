"""OVS-Calibration v0.5 + v0.6 — full coverage.

v0.5 coverage (unchanged):
  - source registry CRUD
  - three attribution stages (direct, temporal+entity, causal-chain stub)
  - layer assignment edges (7d, 30d, 90d boundaries)
  - variance pos/neg/zero
  - revision HMAC sign + verify + tamper detection
  - override-weight 3x policy
  - authority gate at 10% threshold
  - codification-bridge emission at >=50 stable outcomes

v0.6 coverage (this PR):
  - causal-chain attribution real implementation (1-hop, 2-hop, 4-hop)
  - max-depth cap (chain stops at MAX_CAUSAL_CHAIN_HOPS=4)
  - confidence multiplicative (0.85 per hop)
  - terminal-link cascade multiplier matches Framework 5.12 per-systems
  - counterfactual direct (rejected + observable alternative)
  - counterfactual comparative (cross-entity divergence)
  - counterfactual temporal (pre/post regime change)
  - counterfactual rejects synthesized cases (returns None)
  - adapter ingestion (mock pubsub callback)
  - adapter no-crash when subscription unconfigured
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ovs_calibration import (
    # sources
    OutcomeSource, register_source, get_source, list_sources, update_health,
    # variance
    DecisionCertificateLike, DecisionProjection, OutcomeEventLike,
    compute_variance, MetricKind,
    # attribution
    AttributionLink, assign_layer, cascade_multiplier_for_layer,
    cascade_multiplier_for_systems, attribute_direct, attribute_temporal_entity,
    attribute_causal_chain, attribute, persist_link, list_links_for_decision,
    list_links_for_outcome, walk_causal_chain,
    MAX_CAUSAL_CHAIN_HOPS, CAUSAL_CHAIN_HOP_DECAY,
    # revisions
    CalibrationRevision, write_revision, get_revision, list_revisions,
    verify_revision,
    # authority
    OutcomeEventForWeight, RequiresSignoff, outcome_weight,
    check_calibration_authority, OVERRIDE_WEIGHT, DEFAULT_WEIGHT,
    REQUIRED_DUAL_SIGNERS,
    # codification bridge
    VarianceObservation, evaluate_stability, emit_candidate,
    # counterfactual (v0.6)
    CounterfactualRecord, CounterfactualScore, score_counterfactual,
    persist_counterfactual, get_counterfactual, list_counterfactuals,
    verify_counterfactual,
)
from engine.ovs_calibration import variance as variance_mod
from engine.ovs_calibration.adapters import (
    CarmenBeachRevenueAdapter, TiSolutionsConversionAdapter,
    GigatonUIUsageAdapter, all_adapters, ingest_outcome,
)


def _utc(s: str) -> str:
    return s if s.endswith("+00:00") or s.endswith("Z") else s + "+00:00"


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "ovs_calibration.db")


@pytest.fixture
def tmp_md_dir(tmp_path: Path) -> Path:
    d = tmp_path / "calibration-revisions"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(autouse=True)
def _reset_variance_cache():
    """Each test starts with a fresh metric-kind cache so YAML edits don't leak."""
    variance_mod.reset_metric_kind_cache()
    yield
    variance_mod.reset_metric_kind_cache()


# ─────────────────────────────────────────────
# 1. Source registry CRUD
# ─────────────────────────────────────────────


def test_register_source_round_trips(tmp_db):
    src = OutcomeSource(
        name="PDC Revenue",
        kind="revenue",
        entity="carmen-beach",
        ingestion_contract="webhook",
        schema={"observed_value": "float", "metric": "string"},
        owner="todd@gigaton.ai",
        decision_class_metric_map={"pricing.dynamic.carmen-beach": "revenue.daily"},
    )
    body = register_source(src, db_path=tmp_db)
    assert body["id"] == src.id
    assert body["kind"] == "revenue"
    assert body["decision_class_metric_map"] == {
        "pricing.dynamic.carmen-beach": "revenue.daily"
    }

    fetched = get_source(src.id, db_path=tmp_db)
    assert fetched is not None
    assert fetched["entity"] == "carmen-beach"
    assert fetched["schema"] == {"observed_value": "float", "metric": "string"}


def test_list_sources_filters_by_kind_and_entity(tmp_db):
    register_source(OutcomeSource(
        name="A", kind="revenue", entity="carmen-beach",
        ingestion_contract="pubsub", schema={}, owner="todd",
    ), db_path=tmp_db)
    register_source(OutcomeSource(
        name="B", kind="conversion", entity="ti-solutions",
        ingestion_contract="webhook", schema={}, owner="todd",
    ), db_path=tmp_db)
    register_source(OutcomeSource(
        name="C", kind="revenue", entity="ti-solutions",
        ingestion_contract="polling", schema={}, owner="todd",
    ), db_path=tmp_db)

    rev = list_sources(kind="revenue", db_path=tmp_db)
    assert {s["name"] for s in rev} == {"A", "C"}

    ti = list_sources(entity="ti-solutions", db_path=tmp_db)
    assert {s["name"] for s in ti} == {"B", "C"}


def test_register_source_rejects_invalid_kind():
    with pytest.raises(ValueError, match="kind must be one of"):
        OutcomeSource(
            name="x", kind="bogus", entity="e",
            ingestion_contract="pubsub", schema={}, owner="o",
        )


def test_update_health_persists(tmp_db):
    src = OutcomeSource(
        name="x", kind="revenue", entity="carmen-beach",
        ingestion_contract="webhook", schema={}, owner="todd",
    )
    register_source(src, db_path=tmp_db)
    updated = update_health(src.id, "degraded", db_path=tmp_db)
    assert updated["health_status"] == "degraded"


def test_update_health_rejects_invalid_value(tmp_db):
    src = OutcomeSource(
        name="x", kind="revenue", entity="carmen-beach",
        ingestion_contract="webhook", schema={}, owner="todd",
    )
    register_source(src, db_path=tmp_db)
    with pytest.raises(ValueError):
        update_health(src.id, "bogus-state", db_path=tmp_db)


# ─────────────────────────────────────────────
# 2. Layer assignment edges
# ─────────────────────────────────────────────


@pytest.mark.parametrize("delta_days,expected_layer", [
    (0, 1),
    (3, 1),
    (6.99, 1),
    (7, 2),       # 7d boundary -> layer 2
    (7.01, 2),
    (15, 2),
    (29.99, 2),
    (30, 3),      # 30d boundary -> layer 3
    (60, 3),
    (89.99, 3),
    (90, 4),      # 90d boundary -> layer 4
    (180, 4),
])
def test_assign_layer_boundaries(delta_days, expected_layer):
    decision_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome_at = decision_at + timedelta(days=delta_days)
    assert assign_layer(decision_at, outcome_at) == expected_layer


def test_cascade_multiplier_per_layer_doctrine():
    """Framework 5.12: 1.0x / 0.7x / 0.35x / 0.0x"""
    assert cascade_multiplier_for_layer(1) == 1.0
    assert cascade_multiplier_for_layer(2) == 0.7
    assert cascade_multiplier_for_layer(3) == 0.35
    assert cascade_multiplier_for_layer(4) == 0.0
    with pytest.raises(ValueError):
        cascade_multiplier_for_layer(5)


def test_cascade_multiplier_per_systems_linear():
    """Framework 5.12: 1 system 1.0x -> 4 systems 2.2x linear interp."""
    assert cascade_multiplier_for_systems(1) == 1.0
    assert cascade_multiplier_for_systems(2) == 1.4
    assert cascade_multiplier_for_systems(3) == 1.8
    assert cascade_multiplier_for_systems(4) == 2.2
    # Clamping
    assert cascade_multiplier_for_systems(0) == 1.0
    assert cascade_multiplier_for_systems(99) == 2.2


# ─────────────────────────────────────────────
# 3. Three attribution stages
# ─────────────────────────────────────────────


def _make_decision(metric="revenue.daily.unit-123", expected=4200, issued="2026-05-01T00:00:00+00:00", horizon=14):
    return DecisionCertificateLike(
        decision_certificate_id="dec-1",
        decision_class="pricing.dynamic.carmen-beach",
        projection=DecisionProjection(
            metric=metric, expected_value=expected, horizon_days=horizon, confidence=0.7,
        ),
        issued_at=issued,
    )


def _make_outcome(metric="revenue.daily.unit-123", observed=4650, source="carmen-beach", at="2026-05-08T00:00:00+00:00"):
    return OutcomeEventLike(
        id="ev-1", metric=metric, observed_value=observed,
        observed_at=at, source=source,
    )


def test_attribute_direct_matches_metric():
    decision = _make_decision()
    outcome = _make_outcome()
    link = attribute_direct(decision, outcome)
    assert link is not None
    assert link.confidence == 1.0
    assert link.attribution_method == "direct"
    assert link.layer_number == 2  # 7 days exactly between 2026-05-01 and 2026-05-08
    assert link.reasoning.startswith("Direct:")


def test_attribute_direct_returns_none_when_metric_mismatch():
    decision = _make_decision(metric="revenue.daily.unit-123")
    outcome = _make_outcome(metric="conversion.lead_to_close")
    assert attribute_direct(decision, outcome) is None


def test_attribute_temporal_entity_matches_when_entity_in_metric():
    """Entity match via substring in outcome.source or metric."""
    decision = _make_decision(metric="revenue.daily", horizon=14)
    outcome = OutcomeEventLike(
        id="ev-2", metric="revenue.daily.unit-1",
        observed_value=4500, observed_at="2026-05-05T00:00:00+00:00",
        source="carmen-beach",
    )
    link = attribute_temporal_entity(
        decision, outcome, decision_entity="carmen-beach", horizon_days=14,
    )
    assert link is not None
    assert link.attribution_method == "temporal"
    assert 0.3 <= link.confidence <= 0.95
    # 4 days into 14-day horizon -> within 0.5*horizon bonus
    assert link.confidence >= 0.7 + 0.15  # base + horizon_bonus
    # Reasoning contains entity + delta info
    assert "carmen-beach" in link.reasoning


def test_attribute_temporal_entity_skips_when_entity_missing():
    decision = _make_decision()
    outcome = OutcomeEventLike(
        id="ev-3", metric="revenue.daily.unit-1",
        observed_value=4500, observed_at="2026-05-05T00:00:00+00:00",
        source="ti-solutions",  # Different entity
    )
    link = attribute_temporal_entity(
        decision, outcome, decision_entity="carmen-beach", horizon_days=14,
    )
    assert link is None


def test_attribute_temporal_entity_lowers_confidence_outside_horizon():
    decision = _make_decision(metric="revenue.daily", horizon=14)
    # 30 days out, way past 14d horizon * 1.5 = 21d
    outcome = OutcomeEventLike(
        id="ev-4", metric="revenue.daily.unit-1",
        observed_value=4500, observed_at="2026-05-31T00:00:00+00:00",
        source="carmen-beach",
    )
    link = attribute_temporal_entity(
        decision, outcome, decision_entity="carmen-beach", horizon_days=14,
    )
    assert link is not None
    # base 0.7 - 0.20 (outside 1.5*horizon) = 0.5; layer is 2 (30d boundary -> layer 3 if >=30)
    assert link.confidence <= 0.7
    assert link.layer_number in (2, 3)


def test_attribute_causal_chain_returns_empty_without_chain_inputs():
    """Doctrine: no synthesis. Without chain_links or resolver, returns []."""
    decision = _make_decision()
    outcome = _make_outcome()
    assert attribute_causal_chain(decision, outcome) == []


def test_attribute_orchestration_runs_direct_first(tmp_db):
    decision = _make_decision()
    outcome = _make_outcome()
    links = attribute(decision, outcome, decision_entity="carmen-beach", horizon_days=14)
    assert len(links) == 1
    assert links[0].attribution_method == "direct"


def test_attribute_orchestration_falls_back_to_temporal_when_metric_mismatch():
    decision = _make_decision(metric="revenue.daily")
    # outcome metric is a sub-key family member, but not a direct exact match
    outcome = OutcomeEventLike(
        id="ev-5", metric="revenue.daily.unit-1",
        observed_value=4500, observed_at="2026-05-05T00:00:00+00:00",
        source="carmen-beach",
    )
    links = attribute(decision, outcome, decision_entity="carmen-beach", horizon_days=14)
    # Direct should be None (metrics differ), temporal should fire (prefix family match)
    assert len(links) == 1
    assert links[0].attribution_method == "temporal"


def test_persist_and_list_links(tmp_db):
    decision = _make_decision()
    outcome = _make_outcome()
    links = attribute(decision, outcome, decision_entity="carmen-beach")
    for link in links:
        persist_link(link, db_path=tmp_db)
    by_dec = list_links_for_decision("dec-1", db_path=tmp_db)
    by_out = list_links_for_outcome("ev-1", db_path=tmp_db)
    assert len(by_dec) == 1
    assert len(by_out) == 1


def test_attribution_link_validates_reasoning():
    with pytest.raises(ValueError, match="reasoning is required"):
        AttributionLink(
            decision_certificate_id="d", outcome_event_id="o",
            confidence=0.9, attribution_method="direct",
            layer_number=1, cascade_multiplier=1.0, reasoning="",
        )


def test_attribution_link_validates_confidence_bounds():
    with pytest.raises(ValueError, match="confidence"):
        AttributionLink(
            decision_certificate_id="d", outcome_event_id="o",
            confidence=1.5, attribution_method="direct",
            layer_number=1, cascade_multiplier=1.0, reasoning="x" * 10,
        )


# ─────────────────────────────────────────────
# 4. Variance pos/neg/zero
# ─────────────────────────────────────────────


def test_compute_variance_positive_proportional():
    decision = _make_decision(metric="revenue.daily", expected=4200)
    outcome = OutcomeEventLike(
        id="ev-6", metric="revenue.daily", observed_value=4650,
        observed_at="2026-05-08T00:00:00+00:00", source="carmen-beach",
    )
    result = compute_variance(decision, outcome)
    assert result.expected_value == 4200
    assert result.observed_value == 4650
    assert result.raw_diff == 450
    assert result.direction == "positive"
    assert result.metric_kind == "proportional"
    # (4650 - 4200) / 4200 = 0.1071...
    assert abs(result.variance_pct - 0.1071) < 0.001


def test_compute_variance_negative_proportional():
    decision = _make_decision(metric="revenue.daily", expected=4200)
    outcome = OutcomeEventLike(
        id="ev-7", metric="revenue.daily", observed_value=3500,
        observed_at="2026-05-08T00:00:00+00:00", source="carmen-beach",
    )
    result = compute_variance(decision, outcome)
    assert result.direction == "negative"
    assert result.raw_diff == -700
    assert result.variance_pct < -0.10


def test_compute_variance_neutral_within_band():
    decision = _make_decision(metric="revenue.daily", expected=4200)
    # 4% above expected — inside default 10% neutral band
    outcome = OutcomeEventLike(
        id="ev-8", metric="revenue.daily", observed_value=4368,
        observed_at="2026-05-08T00:00:00+00:00", source="carmen-beach",
    )
    result = compute_variance(decision, outcome)
    assert result.direction == "neutral"


def test_compute_variance_zero_expectation():
    decision = _make_decision(metric="revenue.daily", expected=0)
    outcome = OutcomeEventLike(
        id="ev-9", metric="revenue.daily", observed_value=100,
        observed_at="2026-05-08T00:00:00+00:00", source="carmen-beach",
    )
    result = compute_variance(decision, outcome)
    assert result.variance_pct == 1.0  # +100% convention when expected==0


def test_compute_variance_absolute_metric_via_keyword():
    """`incidents.weekly` is keyword-matched as absolute via DEFAULT_ABSOLUTE_KEYWORDS."""
    decision = DecisionCertificateLike(
        decision_certificate_id="dec-abs",
        decision_class="ops.incidents",
        projection=DecisionProjection(metric="incidents.weekly", expected_value=5),
        issued_at="2026-05-01T00:00:00+00:00",
    )
    outcome = OutcomeEventLike(
        id="ev-abs", metric="incidents.weekly", observed_value=8,
        observed_at="2026-05-05T00:00:00+00:00", source="ti-solutions",
    )
    result = compute_variance(decision, outcome)
    assert result.metric_kind == "absolute"
    assert result.variance == 3  # 8 - 5 (absolute, not proportional)


def test_compute_variance_raises_on_metric_mismatch():
    decision = _make_decision(metric="revenue.daily")
    outcome = OutcomeEventLike(
        id="ev-10", metric="conversion.lead",
        observed_value=10, observed_at="2026-05-08T00:00:00+00:00",
    )
    with pytest.raises(ValueError, match="projection metric"):
        compute_variance(decision, outcome)


def test_compute_variance_override_forces_absolute():
    decision = _make_decision(metric="revenue.daily", expected=100)
    outcome = OutcomeEventLike(
        id="ev-11", metric="revenue.daily", observed_value=120,
        observed_at="2026-05-08T00:00:00+00:00", source="carmen-beach",
    )
    proportional = compute_variance(decision, outcome)
    absolute = compute_variance(decision, outcome, metric_kind_override="absolute")
    assert proportional.metric_kind == "proportional"
    assert absolute.metric_kind == "absolute"
    assert absolute.variance == 20  # observed - expected, not pct


# ─────────────────────────────────────────────
# 5. Revision HMAC sign + verify + tamper
# ─────────────────────────────────────────────


def test_revision_sign_and_verify_round_trip(tmp_db, tmp_md_dir):
    rev = CalibrationRevision(
        dimension="trust.outcome_history.pricing.dynamic.carmen-beach",
        before_value=0.50,
        after_value=0.53,
        evidence_window_start="2026-05-01T00:00:00+00:00",
        evidence_window_end="2026-05-08T00:00:00+00:00",
        evidence_outcome_ids=["ev-1", "ev-2", "ev-3"],
        computation_version="v0.5",
        signed_by="todd@gigaton.ai",
        reasoning="Stable positive variance over 7 days; 3 attributed outcomes; bumping trust 6%",
    )
    body = write_revision(rev, db_path=tmp_db, md_dir=tmp_md_dir)
    assert body["hmac"]
    assert body["md_path"]

    # Verify round-trip works
    assert verify_revision(rev.id, db_path=tmp_db) is True


def test_revision_verify_detects_db_tamper(tmp_db, tmp_md_dir):
    rev = CalibrationRevision(
        dimension="trust.outcome_history.pricing",
        before_value=0.50, after_value=0.53,
        evidence_window_start="2026-05-01T00:00:00+00:00",
        evidence_window_end="2026-05-08T00:00:00+00:00",
        evidence_outcome_ids=["ev-1"],
        computation_version="v0.5",
        signed_by="todd@gigaton.ai",
        reasoning="Stable positive variance; bumping trust by a small amount",
    )
    write_revision(rev, db_path=tmp_db, md_dir=tmp_md_dir)

    # Tamper: change after_value directly via SQL
    import sqlite3
    with sqlite3.connect(tmp_db) as conn:
        conn.execute(
            "UPDATE calibration_revisions SET after_value = ? WHERE id = ?",
            (999.0, rev.id),
        )
    # Verification should now fail (signed payload no longer matches)
    assert verify_revision(rev.id, db_path=tmp_db) is False


def test_revision_verify_detects_md_tamper(tmp_db, tmp_md_dir):
    rev = CalibrationRevision(
        dimension="trust.outcome_history.pricing",
        before_value=0.50, after_value=0.53,
        evidence_window_start="2026-05-01T00:00:00+00:00",
        evidence_window_end="2026-05-08T00:00:00+00:00",
        evidence_outcome_ids=["ev-1"],
        computation_version="v0.5",
        signed_by="todd@gigaton.ai",
        reasoning="Stable positive variance; bumping trust by a small amount",
    )
    write_revision(rev, db_path=tmp_db, md_dir=tmp_md_dir)
    # Tamper the MD file's hmac frontmatter
    md_path = Path(rev.md_path)
    text = md_path.read_text(encoding="utf-8")
    md_path.write_text(
        text.replace(rev.hmac, "0" * len(rev.hmac)),
        encoding="utf-8",
    )
    assert verify_revision(rev.id, db_path=tmp_db) is False


def test_revision_rejects_short_reasoning():
    with pytest.raises(ValueError, match="reasoning is required"):
        CalibrationRevision(
            dimension="x",
            before_value=0.5, after_value=0.5,
            evidence_window_start="2026-05-01T00:00:00+00:00",
            evidence_window_end="2026-05-08T00:00:00+00:00",
            evidence_outcome_ids=[],
            computation_version="v0.5",
            signed_by="todd",
            reasoning="too short",
        )


def test_list_revisions_filters_by_dimension(tmp_db, tmp_md_dir):
    rev1 = CalibrationRevision(
        dimension="trust.A", before_value=0.5, after_value=0.51,
        evidence_window_start="2026-05-01T00:00:00+00:00",
        evidence_window_end="2026-05-08T00:00:00+00:00",
        evidence_outcome_ids=["ev-1"], computation_version="v0.5",
        signed_by="todd@gigaton.ai",
        reasoning="Within 10% magnitude; routine automated calibration",
    )
    rev2 = CalibrationRevision(
        dimension="trust.B", before_value=0.4, after_value=0.41,
        evidence_window_start="2026-05-01T00:00:00+00:00",
        evidence_window_end="2026-05-08T00:00:00+00:00",
        evidence_outcome_ids=["ev-2"], computation_version="v0.5",
        signed_by="todd@gigaton.ai",
        reasoning="Within 10% magnitude; routine automated calibration",
    )
    write_revision(rev1, db_path=tmp_db, md_dir=tmp_md_dir)
    write_revision(rev2, db_path=tmp_db, md_dir=tmp_md_dir)

    only_a = list_revisions(dimension="trust.A", db_path=tmp_db)
    assert len(only_a) == 1
    assert only_a[0]["dimension"] == "trust.A"
    assert only_a[0]["verified"] is True


# ─────────────────────────────────────────────
# 6. Override-event weight 3x
# ─────────────────────────────────────────────


def test_outcome_weight_override_is_3x():
    assert outcome_weight(OutcomeEventForWeight(source="override")) == OVERRIDE_WEIGHT
    assert outcome_weight(OutcomeEventForWeight(source="override")) == 3.0


def test_outcome_weight_default_is_1x():
    assert outcome_weight(OutcomeEventForWeight(source="carmen-beach")) == DEFAULT_WEIGHT
    assert outcome_weight(OutcomeEventForWeight(source="ti-solutions")) == 1.0
    assert outcome_weight(OutcomeEventForWeight(source="")) == 1.0


# ─────────────────────────────────────────────
# 7. Authority gate at 10% threshold
# ─────────────────────────────────────────────


def test_authority_gate_passes_below_10_percent():
    """A 5% bump is automated — no signoff required."""
    result = check_calibration_authority(
        dimension="trust.outcome_history.pricing",
        before_value=0.50, after_value=0.525,  # +5%
        computation_version="v0.5",
        previous_computation_version="v0.5",
        is_new_dimension=False,
    )
    assert result is None  # automated write OK


def test_authority_gate_requires_dual_signers_at_10_percent():
    """At exactly 10% magnitude, dual-signer required."""
    result = check_calibration_authority(
        dimension="trust.outcome_history.pricing",
        before_value=0.50, after_value=0.55,  # +10% exact
        computation_version="v0.5",
        previous_computation_version="v0.5",
        is_new_dimension=False,
    )
    assert isinstance(result, RequiresSignoff)
    assert result.required_signers == REQUIRED_DUAL_SIGNERS
    assert any("magnitude" in r for r in result.reasons)


def test_authority_gate_satisfied_with_dual_signers():
    """When both todd + matt sign, gate passes even for >=10%."""
    result = check_calibration_authority(
        dimension="trust.outcome_history.pricing",
        before_value=0.50, after_value=0.65,  # +30%
        computation_version="v0.5",
        previous_computation_version="v0.5",
        is_new_dimension=False,
        signers=["todd@gigaton.ai", "matt@gigaton.ai"],
    )
    assert result is None


def test_authority_gate_requires_signoff_for_new_dimension():
    result = check_calibration_authority(
        dimension="trust.outcome_history.new_class",
        before_value=0.0, after_value=0.5,
        computation_version="v0.5",
        previous_computation_version=None,
        is_new_dimension=True,
    )
    assert isinstance(result, RequiresSignoff)
    assert result.is_new_dimension is True


def test_authority_gate_requires_signoff_on_computation_version_bump():
    result = check_calibration_authority(
        dimension="trust.outcome_history.pricing",
        before_value=0.5, after_value=0.505,  # tiny magnitude
        computation_version="v0.6",
        previous_computation_version="v0.5",
        is_new_dimension=False,
    )
    assert isinstance(result, RequiresSignoff)
    assert result.computation_version_bump is True


def test_authority_gate_zero_before_value_uses_absolute_magnitude():
    """When before_value==0 we can't divide; |after| becomes the magnitude."""
    result = check_calibration_authority(
        dimension="trust.outcome_history.pricing",
        before_value=0.0, after_value=0.05,  # |0.05| >= 0.10 threshold? No -> automated
        computation_version="v0.5",
        previous_computation_version="v0.5",
        is_new_dimension=False,
    )
    assert result is None

    result2 = check_calibration_authority(
        dimension="trust.outcome_history.pricing",
        before_value=0.0, after_value=0.15,  # |0.15| >= 0.10 threshold -> signoff
        computation_version="v0.5",
        previous_computation_version="v0.5",
        is_new_dimension=False,
    )
    assert isinstance(result2, RequiresSignoff)


# ─────────────────────────────────────────────
# 8. Codification-bridge emission at >=50 stable outcomes
# ─────────────────────────────────────────────


def test_evaluate_stability_eligible_at_50_low_variance():
    obs = [VarianceObservation(outcome_event_id=f"ev-{i}", variance=0.05) for i in range(50)]
    eligible, n, p50, p90 = evaluate_stability(obs)
    assert eligible is True
    assert n == 50
    assert p90 <= 0.10


def test_evaluate_stability_blocked_below_50():
    obs = [VarianceObservation(outcome_event_id=f"ev-{i}", variance=0.05) for i in range(49)]
    eligible, n, p50, p90 = evaluate_stability(obs)
    assert eligible is False
    assert n == 49


def test_evaluate_stability_blocked_above_variance_threshold():
    """50 outcomes but p90 |variance| > 0.10 -> ineligible.

    Nearest-rank p90 at n=50 is sorted[round(0.9 * 49)] = sorted[44].
    We need the top 6+ values to be >0.10 so that sorted[44] exceeds the band.
    """
    obs = [VarianceObservation(outcome_event_id=f"ev-{i}", variance=0.05) for i in range(40)]
    obs.extend(
        VarianceObservation(outcome_event_id=f"ev-{i}", variance=0.25) for i in range(40, 50)
    )
    eligible, n, p50, p90 = evaluate_stability(obs)
    assert eligible is False
    assert p90 > 0.10


def test_emit_candidate_opens_proposal_when_eligible(tmp_path):
    """The bridge writes to the codification queue when threshold hit."""
    obs = [
        VarianceObservation(outcome_event_id=f"ev-{i}", variance=0.04)
        for i in range(50)
    ]
    proposals_db = str(tmp_path / "codification_proposals.db")
    emission = emit_candidate(
        decision_class="pricing.dynamic.carmen-beach",
        observations=obs,
        why="ovs_calibration: stable for 50 outcomes; eligible for codification",
        proposals_db_path=proposals_db,
    )
    assert emission.eligible is True
    assert emission.proposal_id is not None
    # Verify the proposal exists in the codification queue
    from engine.codification import get_proposal
    body = get_proposal(emission.proposal_id, db_path=proposals_db)
    assert body is not None
    assert body["queue_status"] == "open"
    assert "ovs_calibration" in body["why"]


def test_emit_candidate_skips_when_ineligible(tmp_path):
    obs = [VarianceObservation(outcome_event_id=f"ev-{i}", variance=0.04) for i in range(10)]
    proposals_db = str(tmp_path / "codification_proposals.db")
    emission = emit_candidate(
        decision_class="pricing.dynamic.carmen-beach",
        observations=obs,
        proposals_db_path=proposals_db,
    )
    assert emission.eligible is False
    assert emission.proposal_id is None
    assert "sample_size=10" in (emission.skipped_reason or "")


# ─────────────────────────────────────────────
# 9. End-to-end smoke: attribute -> variance -> revision
# ─────────────────────────────────────────────


def test_end_to_end_attribute_variance_revision(tmp_db, tmp_md_dir):
    decision = _make_decision(metric="revenue.daily", expected=4200, horizon=14)
    outcome = OutcomeEventLike(
        id="ev-e2e", metric="revenue.daily", observed_value=4400,
        observed_at="2026-05-05T00:00:00+00:00", source="carmen-beach",
    )

    # 1. Attribute
    links = attribute(decision, outcome, decision_entity="carmen-beach", horizon_days=14)
    assert len(links) == 1
    persist_link(links[0], db_path=tmp_db)

    # 2. Variance
    vr = compute_variance(decision, outcome)
    assert vr.direction == "neutral"  # 4.76% < 10% band
    assert abs(vr.variance_pct - 0.0476) < 0.001

    # 3. Revision (within 10% threshold -> automated)
    auth = check_calibration_authority(
        dimension="trust.outcome_history.pricing.dynamic.carmen-beach",
        before_value=0.50, after_value=0.502,  # tiny bump
        computation_version="v0.5",
        previous_computation_version="v0.5",
        is_new_dimension=False,
    )
    assert auth is None

    rev = CalibrationRevision(
        dimension="trust.outcome_history.pricing.dynamic.carmen-beach",
        before_value=0.50, after_value=0.502,
        evidence_window_start="2026-05-01T00:00:00+00:00",
        evidence_window_end="2026-05-08T00:00:00+00:00",
        evidence_outcome_ids=["ev-e2e"],
        computation_version="v0.5",
        signed_by="todd@gigaton.ai",
        reasoning=(
            "Single neutral-band outcome for revenue.daily on carmen-beach; "
            "tiny upward trust nudge; routine automated calibration"
        ),
    )
    body = write_revision(rev, db_path=tmp_db, md_dir=tmp_md_dir)
    assert verify_revision(body["id"], db_path=tmp_db) is True


# ═════════════════════════════════════════════════════════════════════
# v0.6 — Causal-chain attribution (real implementation)
# ═════════════════════════════════════════════════════════════════════


def _chain_hop(decision_id, system="", issued_at="2026-04-25T00:00:00+00:00",
               metric="revenue.daily"):
    return {
        "decision_certificate_id": decision_id,
        "system": system,
        "issued_at": issued_at,
        "projection_metric": metric,
    }


def test_causal_chain_returns_empty_when_only_terminal_in_chain_links():
    """No real chain — just the terminal. We don't fabricate hops."""
    decision = _make_decision()
    outcome = _make_outcome()
    links = attribute_causal_chain(
        decision, outcome,
        chain_links=[],  # explicitly empty
    )
    assert links == []


def test_causal_chain_two_hop_via_chain_links():
    """Two-hop chain: terminal + 1 ancestor. Confidence decay = 0.85."""
    decision = _make_decision()  # decision-1
    outcome = _make_outcome()
    parent_hop = _chain_hop("dec-parent", system="carmen-beach")
    links = attribute_causal_chain(
        decision, outcome,
        chain_links=[parent_hop],
    )
    assert len(links) == 2
    terminal = links[0]
    ancestor = links[1]
    assert terminal.chain_terminal is True
    assert terminal.chain_position == 1
    assert terminal.confidence == 1.0
    assert ancestor.chain_terminal is False
    assert ancestor.chain_position == 2
    assert abs(ancestor.confidence - 0.85) < 1e-6
    assert terminal.chain_root_decision_id == "dec-parent"
    assert ancestor.chain_root_decision_id == "dec-parent"
    assert all(link.attribution_method == "causal-chain" for link in links)


def test_causal_chain_four_hop_max_depth():
    """4-hop chain: confidences 1.0, 0.85, 0.7225, 0.614125."""
    decision = _make_decision()
    outcome = _make_outcome()
    hops = [
        _chain_hop("dec-p1", system="carmen-beach"),
        _chain_hop("dec-p2", system="ti-solutions"),
        _chain_hop("dec-p3", system="gigaton-ui"),
    ]
    links = attribute_causal_chain(
        decision, outcome,
        chain_links=hops,
    )
    assert len(links) == 4  # 1 terminal + 3 ancestors
    confidences = [link.confidence for link in links]
    expected = [
        1.0,
        round(CAUSAL_CHAIN_HOP_DECAY, 6),
        round(CAUSAL_CHAIN_HOP_DECAY ** 2, 6),
        round(CAUSAL_CHAIN_HOP_DECAY ** 3, 6),
    ]
    for actual, want in zip(confidences, expected):
        assert abs(actual - want) < 1e-5


def test_causal_chain_caps_at_max_depth():
    """5+ hops in chain_links — only first MAX_CAUSAL_CHAIN_HOPS used."""
    decision = _make_decision()
    outcome = _make_outcome()
    hops = [
        _chain_hop(f"dec-p{i}", system=f"system-{i}")
        for i in range(1, 10)
    ]
    links = attribute_causal_chain(
        decision, outcome,
        chain_links=hops,
    )
    assert len(links) == MAX_CAUSAL_CHAIN_HOPS
    assert all(0 <= link.chain_position <= MAX_CAUSAL_CHAIN_HOPS for link in links)


def test_causal_chain_terminal_cascade_uses_per_systems_multiplier():
    """Terminal cascade_multiplier follows Framework 5.12 per-system math.

    1 system  -> 1.0×
    2 systems -> 1.4×
    3 systems -> 1.8×
    4 systems -> 2.2×
    """
    decision = _make_decision()
    outcome = _make_outcome(source="carmen-beach")

    # 1 system  → terminal cascade = 1.0  (only carmen-beach observed)
    links_1 = attribute_causal_chain(
        decision, outcome,
        chain_links=[_chain_hop("dec-p1", system="carmen-beach")],
    )
    assert links_1[0].cascade_multiplier == 1.0
    assert links_1[0].chain_systems_count == 1

    # 2 systems → 1.4
    links_2 = attribute_causal_chain(
        decision, outcome,
        chain_links=[_chain_hop("dec-p1", system="ti-solutions")],
    )
    assert links_2[0].cascade_multiplier == 1.4
    assert links_2[0].chain_systems_count == 2

    # 3 systems → 1.8
    links_3 = attribute_causal_chain(
        decision, outcome,
        chain_links=[
            _chain_hop("dec-p1", system="ti-solutions"),
            _chain_hop("dec-p2", system="gigaton-ui"),
        ],
    )
    assert links_3[0].cascade_multiplier == 1.8
    assert links_3[0].chain_systems_count == 3

    # 4 systems → 2.2 (cap at brief's 4-system anchor)
    links_4 = attribute_causal_chain(
        decision, outcome,
        chain_links=[
            _chain_hop("dec-p1", system="ti-solutions"),
            _chain_hop("dec-p2", system="gigaton-ui"),
            _chain_hop("dec-p3", system="liquifex"),
        ],
    )
    assert links_4[0].cascade_multiplier == 2.2
    assert links_4[0].chain_systems_count == 4


def test_causal_chain_via_resolver_walk():
    """Stage 3 can walk via decision_resolver instead of pre-built chain_links."""
    decision = _make_decision()
    outcome = _make_outcome()

    decision_graph = {
        "dec-1": {
            "decision_certificate_id": "dec-1",
            "parent_certificate_id": "dec-parent",
            "evidence_certificate_ids": [],
            "system": "carmen-beach",
            "issued_at": "2026-04-30T00:00:00+00:00",
            "projection_metric": "revenue.daily",
        },
        "dec-parent": {
            "decision_certificate_id": "dec-parent",
            "parent_certificate_id": "dec-grandparent",
            "evidence_certificate_ids": [],
            "system": "ti-solutions",
            "issued_at": "2026-04-20T00:00:00+00:00",
            "projection_metric": "qualification.lead",
        },
        "dec-grandparent": {
            "decision_certificate_id": "dec-grandparent",
            "parent_certificate_id": None,
            "evidence_certificate_ids": [],
            "system": "gigaton-ui",
            "issued_at": "2026-04-10T00:00:00+00:00",
            "projection_metric": "usage.wizard.complete",
        },
    }

    def resolver(decision_id):
        return decision_graph.get(decision_id)

    links = attribute_causal_chain(
        decision, outcome,
        decision_resolver=resolver,
    )
    assert len(links) == 3  # terminal + 2 ancestors walked
    assert links[0].chain_position == 1
    assert links[1].decision_certificate_id == "dec-parent"
    assert links[2].decision_certificate_id == "dec-grandparent"
    # 3 distinct systems
    assert links[0].chain_systems_count == 3


def test_walk_causal_chain_persists(tmp_db):
    """walk_causal_chain(persist=True) writes rows with chain fields."""
    decision = _make_decision()
    outcome = _make_outcome()
    walk_causal_chain(
        decision, outcome,
        chain_links=[
            _chain_hop("dec-p1", system="ti-solutions"),
            _chain_hop("dec-p2", system="gigaton-ui"),
        ],
        persist=True, db_path=tmp_db,
    )
    rows = list_links_for_outcome("ev-1", db_path=tmp_db)
    assert len(rows) == 3
    # Confirm chain fields round-tripped through SQLite
    by_pos = sorted(rows, key=lambda r: r["chain_position"])
    assert by_pos[0]["chain_terminal"] == 1
    assert by_pos[0]["chain_systems_count"] == 3
    assert by_pos[2]["chain_position"] == 3


def test_attribute_orchestration_includes_causal_chain_when_chain_links_provided():
    """High-level attribute() should pass chain_links into stage 3."""
    decision = _make_decision()
    outcome = _make_outcome()
    links = attribute(
        decision, outcome,
        decision_entity="carmen-beach",
        chain_links=[_chain_hop("dec-p1", system="ti-solutions")],
    )
    # Direct fires (metrics match), then chain appends 2 hops
    assert any(link.attribution_method == "direct" for link in links)
    assert any(link.attribution_method == "causal-chain" for link in links)
    assert len(links) == 1 + 2


# ═════════════════════════════════════════════════════════════════════
# v0.6 — Counterfactual scoring
# ═════════════════════════════════════════════════════════════════════


def test_counterfactual_direct_observable():
    """Direct: rejected + observed alternative outcome -> scored."""
    score = score_counterfactual(
        rejected_decision_id="dec-rejected-1",
        observed_alternative_outcome_ids=["ev-alt-1"],
        kind="direct",
        rejected_projection_value=5000,
        observed_alternative_value=4200,
        alternative_chosen_id="dec-chosen-1",
    )
    assert score is not None
    assert score.kind == "direct"
    # rejected would have outperformed (5000 vs 4200) → positive score
    assert score.inferred_counterfactual_score > 0
    # 5000 / 4200 - 1 ≈ +0.19
    assert abs(score.inferred_counterfactual_score - (800 / 4200)) < 1e-3
    assert score.confidence >= 0.5


def test_counterfactual_comparative_observable():
    """Comparative: same pattern, different entities, both outcomes seen."""
    score = score_counterfactual(
        rejected_decision_id="dec-conservative",
        observed_alternative_outcome_ids=["ev-aggressive-1", "ev-aggressive-2"],
        kind="comparative",
        rejected_projection_value=3000,
        observed_alternative_value=4200,
        evidence_metadata={
            "comparing_entities": ["carmen-beach", "ti-solutions"],
            "pattern": "aggressive_pricing",
        },
        reasoning="Conservative would have underperformed aggressive at both entities",
    )
    assert score is not None
    assert score.kind == "comparative"
    # rejected (conservative) was projected lower → negative score
    assert score.inferred_counterfactual_score < 0
    assert "comparing_entities" in score.evidence_metadata


def test_counterfactual_temporal_observable():
    """Temporal: pre/post regime change."""
    score = score_counterfactual(
        rejected_decision_id="dec-pre-regime",
        observed_alternative_outcome_ids=["ev-post-1", "ev-post-2", "ev-post-3"],
        kind="temporal",
        rejected_projection_value=100,
        observed_alternative_value=80,
        evidence_metadata={
            "regime_change_at": "2026-03-15T00:00:00+00:00",
            "regime_label": "post-pricing-doctrine-shift",
        },
    )
    assert score is not None
    assert score.kind == "temporal"
    # +3 outcomes → confidence boost
    assert score.confidence >= 0.55


def test_counterfactual_returns_none_when_unobservable_direct():
    """Direct with no observable outcome ids → None (no synthesis)."""
    score = score_counterfactual(
        rejected_decision_id="dec-rejected-2",
        observed_alternative_outcome_ids=[],  # nothing observed
        kind="direct",
        rejected_projection_value=5000,
        observed_alternative_value=4200,
    )
    assert score is None


def test_counterfactual_returns_none_when_unobservable_comparative():
    """Comparative without comparing_entities metadata → None."""
    score = score_counterfactual(
        rejected_decision_id="dec-rejected-3",
        observed_alternative_outcome_ids=["ev-alt-1"],
        kind="comparative",
        rejected_projection_value=5000,
        observed_alternative_value=4200,
        evidence_metadata={},  # missing comparing_entities
    )
    assert score is None


def test_counterfactual_returns_none_when_unobservable_temporal():
    """Temporal without regime_change_at → None."""
    score = score_counterfactual(
        rejected_decision_id="dec-rejected-4",
        observed_alternative_outcome_ids=["ev-alt-1"],
        kind="temporal",
        rejected_projection_value=5000,
        observed_alternative_value=4200,
        evidence_metadata={"label": "no_regime"},  # missing regime_change_at
    )
    assert score is None


def test_counterfactual_comparative_requires_two_entities():
    score = score_counterfactual(
        rejected_decision_id="dec-cmp",
        observed_alternative_outcome_ids=["ev-x"],
        kind="comparative",
        evidence_metadata={"comparing_entities": ["only-one"]},
    )
    assert score is None


def test_counterfactual_persist_and_verify(tmp_db):
    """persist + HMAC + retrieve + verify round-trip."""
    score = score_counterfactual(
        rejected_decision_id="dec-rej-persist",
        observed_alternative_outcome_ids=["ev-1", "ev-2"],
        kind="direct",
        rejected_projection_value=1000,
        observed_alternative_value=900,
        alternative_chosen_id="dec-chosen-persist",
    )
    assert score is not None
    persisted = persist_counterfactual(score, db_path=tmp_db, scored_by="todd@gigaton.ai")
    assert persisted["hmac"]
    record_id = persisted["id"]

    rec = get_counterfactual(record_id, db_path=tmp_db)
    assert rec is not None
    assert rec.kind == "direct"
    assert rec.scored_by == "todd@gigaton.ai"
    assert verify_counterfactual(record_id, db_path=tmp_db) is True


def test_counterfactual_persist_detects_db_tamper(tmp_db):
    score = score_counterfactual(
        rejected_decision_id="dec-rej-tamper",
        observed_alternative_outcome_ids=["ev-1"],
        kind="direct",
        rejected_projection_value=1000,
        observed_alternative_value=900,
    )
    persisted = persist_counterfactual(score, db_path=tmp_db)
    import sqlite3 as _sql
    with _sql.connect(tmp_db) as conn:
        conn.execute(
            "UPDATE counterfactual_records SET inferred_counterfactual_score=? WHERE id=?",
            (99.0, persisted["id"]),
        )
    assert verify_counterfactual(persisted["id"], db_path=tmp_db) is False


def test_counterfactual_record_rejects_short_reasoning():
    with pytest.raises(ValueError, match="reasoning"):
        CounterfactualRecord(
            rejected_decision_id="dec-1",
            kind="direct",
            observed_alternative_outcome_ids=["ev-1"],
            inferred_counterfactual_score=0.1,
            confidence=0.8,
            reasoning="short",
        )


def test_counterfactual_record_rejects_empty_outcome_ids():
    """Speculative counterfactual guard at the dataclass level."""
    with pytest.raises(ValueError, match="speculative"):
        CounterfactualRecord(
            rejected_decision_id="dec-1",
            kind="direct",
            observed_alternative_outcome_ids=[],
            inferred_counterfactual_score=0.0,
            confidence=0.0,
            reasoning="x" * 30,
        )


def test_list_counterfactuals_filters(tmp_db):
    for kind, alt_id in [("direct", "alt-1"), ("comparative", None), ("temporal", None)]:
        meta = {}
        if kind == "comparative":
            meta = {"comparing_entities": ["a", "b"]}
        if kind == "temporal":
            meta = {"regime_change_at": "2026-03-01T00:00:00+00:00"}
        score = score_counterfactual(
            rejected_decision_id=f"dec-{kind}",
            observed_alternative_outcome_ids=["ev-1"],
            kind=kind,
            rejected_projection_value=100,
            observed_alternative_value=90,
            alternative_chosen_id=alt_id,
            evidence_metadata=meta,
        )
        persist_counterfactual(score, db_path=tmp_db)
    direct_rows = list_counterfactuals(kind="direct", db_path=tmp_db)
    assert len(direct_rows) == 1
    assert direct_rows[0]["kind"] == "direct"


# ═════════════════════════════════════════════════════════════════════
# v0.6 — Per-entity adapters
# ═════════════════════════════════════════════════════════════════════


def test_carmen_beach_adapter_transform():
    adapter = CarmenBeachRevenueAdapter()
    msg = adapter.transform({
        "unit_id": "unit-42",
        "booking_id": "bk-abc",
        "observed_value": 4200,
        "observed_at": "2026-05-08T00:00:00+00:00",
    })
    assert msg.metric == "revenue.daily.unit-42"
    assert msg.observed_value == 4200.0
    assert msg.source_record_id == "bk-abc"
    assert msg.unit == "usd"
    assert msg.extras["unit_id"] == "unit-42"


def test_carmen_beach_adapter_transform_rejects_missing_value():
    adapter = CarmenBeachRevenueAdapter()
    with pytest.raises(ValueError, match="observed_value is required"):
        adapter.transform({"unit_id": "u1", "booking_id": "bk-1"})


def test_ti_solutions_adapter_transform():
    adapter = TiSolutionsConversionAdapter()
    msg = adapter.transform({
        "deal_id": "deal-1",
        "deal_stage": "closed_won",
        "observed_value": 1.0,
        "observed_at": "2026-05-08T00:00:00+00:00",
        "deal_amount_usd": 25000,
    })
    assert msg.metric == "conversion.closed_won"
    assert msg.extras["deal_stage"] == "closed_won"
    assert msg.extras["deal_amount_usd"] == 25000
    assert msg.source_record_id == "deal-1"


def test_gigaton_ui_adapter_transform():
    adapter = GigatonUIUsageAdapter()
    msg = adapter.transform({
        "user_id": "u1",
        "org_id": "o1",
        "feature": "wizard.step.3",
        "event_id": "evt-1",
        "observed_value": 1,
        "observed_at": "2026-05-08T00:00:00+00:00",
        "kind": "count",
    })
    assert msg.metric == "usage.wizard.step.3"
    assert msg.extras["user_id"] == "u1"
    assert msg.extras["feature"] == "wizard.step.3"
    assert msg.unit == "count"


def test_adapter_ingest_message_persists(tmp_db):
    adapter = CarmenBeachRevenueAdapter(db_path=tmp_db)
    raw = {
        "unit_id": "u-99",
        "booking_id": "bk-99",
        "observed_value": 5100,
        "observed_at": "2026-05-08T00:00:00+00:00",
    }
    result = adapter.ingest_message(raw)
    assert result is not None
    assert result.persisted is True
    # Idempotent on source_record_id
    result_2 = adapter.ingest_message(raw)
    assert result_2 is not None
    assert result_2.persisted is False
    assert result.outcome_event_id == result_2.outcome_event_id


def test_adapter_status_reports_unconfigured(monkeypatch):
    """No GCP_PROJECT → adapter is configured=False and run_subscriber no-ops."""
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("OVS_GCP_PROJECT", raising=False)
    adapter = CarmenBeachRevenueAdapter()
    status = adapter.status()
    assert status.configured is False
    assert "GCP_PROJECT" in (status.note or "")
    # run_subscriber returns None silently — no crash
    result = adapter.run_subscriber(blocking=False)
    assert result is None


def test_adapter_run_subscriber_uses_mock_pubsub(monkeypatch, tmp_db):
    """When pubsub is mocked, run_subscriber wires the callback correctly."""
    monkeypatch.setenv("GCP_PROJECT", "fake-project")

    # Build a fake pubsub_v1 module
    import sys as _sys
    import types as _types

    captured: dict = {"callback": None, "subscribed_to": None}

    class _FakeMessage:
        def __init__(self, payload: bytes):
            self.data = payload
            self.message_id = "test-msg-1"
            self.ack_called = False
            self.nack_called = False
        def ack(self):
            self.ack_called = True
        def nack(self):
            self.nack_called = True

    class _FakeFuture:
        def __init__(self):
            self.cancelled = False
        def result(self):
            return None
        def cancel(self):
            self.cancelled = True

    class _FakeSubscriberClient:
        def __init__(self):
            pass
        def subscription_path(self, project, name):
            captured["subscribed_to"] = f"projects/{project}/subscriptions/{name}"
            return captured["subscribed_to"]
        def subscribe(self, path, callback):
            captured["callback"] = callback
            return _FakeFuture()

    fake_module = _types.ModuleType("google.cloud.pubsub_v1")
    fake_module.SubscriberClient = _FakeSubscriberClient  # type: ignore[attr-defined]
    fake_google = _types.ModuleType("google")
    fake_cloud = _types.ModuleType("google.cloud")
    fake_cloud.pubsub_v1 = fake_module  # type: ignore[attr-defined]
    fake_google.cloud = fake_cloud  # type: ignore[attr-defined]

    monkeypatch.setitem(_sys.modules, "google", fake_google)
    monkeypatch.setitem(_sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(_sys.modules, "google.cloud.pubsub_v1", fake_module)

    adapter = CarmenBeachRevenueAdapter(db_path=tmp_db)
    future = adapter.run_subscriber(blocking=False)
    assert future is not None
    assert captured["callback"] is not None
    assert "carmen-beach" in captured["subscribed_to"]

    import json as _json
    msg = _FakeMessage(_json.dumps({
        "unit_id": "u1", "booking_id": "bk-mock-1",
        "observed_value": 4200, "observed_at": "2026-05-08T00:00:00+00:00",
    }).encode("utf-8"))
    captured["callback"](msg)
    assert msg.ack_called is True
    assert adapter.status().messages_persisted == 1


def test_adapter_run_subscriber_no_pubsub_lib_no_crash(monkeypatch):
    """No google.cloud.pubsub_v1 installed → no-op fallback."""
    monkeypatch.setenv("GCP_PROJECT", "fake-project")
    # Ensure import fails
    import builtins
    real_import = builtins.__import__

    def _broken_import(name, *args, **kwargs):
        if name.startswith("google.cloud.pubsub_v1") or (
            name == "google.cloud" and args and args[2] and "pubsub_v1" in args[2]
        ):
            raise ImportError("simulated missing pubsub lib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _broken_import)

    adapter = TiSolutionsConversionAdapter()
    result = adapter.run_subscriber(blocking=False)
    assert result is None
    assert "google-cloud-pubsub not installed" in (adapter.status().note or "")


def test_all_adapters_registry():
    adapters = all_adapters()
    entities = {a.entity for a in adapters}
    assert entities == {"carmen-beach", "ti-solutions", "gigaton-ui"}
    topics = {a.topic for a in adapters}
    assert topics == {
        "outcomes.carmen-beach.revenue",
        "outcomes.ti-solutions.conversion",
        "outcomes.gigaton-ui.usage",
    }


def test_ingest_outcome_helper_writes_event(tmp_db):
    from engine.ovs_calibration.adapters import AdapterMessage
    msg = AdapterMessage(
        metric="revenue.daily.unit-7",
        observed_value=1234.0,
        observed_at="2026-05-08T00:00:00+00:00",
        source_record_id="bk-direct-1",
        unit="usd",
    )
    res = ingest_outcome("carmen-beach", msg, db_path=tmp_db)
    assert res.persisted is True
    assert res.outcome_event_id.startswith("ev-")
