"""OVS-Calibration v0.5 — full coverage of attribution + variance + revisions.

Covers (per PR brief):
  - source registry CRUD
  - three attribution stages (direct, temporal+entity, causal-chain stub)
  - layer assignment edges (7d, 30d, 90d boundaries)
  - variance pos/neg/zero
  - revision HMAC sign + verify + tamper detection
  - override-weight 3x policy
  - authority gate at 10% threshold
  - codification-bridge emission at >=50 stable outcomes
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
    list_links_for_outcome,
    # revisions
    CalibrationRevision, write_revision, get_revision, list_revisions,
    verify_revision,
    # authority
    OutcomeEventForWeight, RequiresSignoff, outcome_weight,
    check_calibration_authority, OVERRIDE_WEIGHT, DEFAULT_WEIGHT,
    REQUIRED_DUAL_SIGNERS,
    # codification bridge
    VarianceObservation, evaluate_stability, emit_candidate,
)
from engine.ovs_calibration import variance as variance_mod


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
        name="Carmen Beach Revenue",
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


def test_attribute_causal_chain_stub_returns_empty():
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
