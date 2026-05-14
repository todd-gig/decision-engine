"""Drift Sentinel — Framework 5.19 BFT rules.

CRIT-010 state_vector_substitution
MAJ-016  decision_without_state_estimate
MAJ-017  forecast_without_confidence_bands
MAJ-018  uncalibrated_forecast_as_authority
MIN-007  interaction_without_effect_vector
MIN-008  interaction_without_cost

Each rule has at least one passing case, one failing case, and one edge case.

WHY these tests exist:
    Framework 5.19 (Business Field Theory) was promoted to canonical
    doctrine on 2026-05-13. The 6 rules above were added to
    DRIFT_RULES.yaml the same day, with T+72hr activation slated for
    ~2026-05-16. Per `feedback_doctrine_claim_vs_committed_code.md`,
    YAML-only rules are inert until a Python handler fires them.
    Without these tests + handlers, T+72 activation would have been
    doctrine-claim-only (same drift class as the MAJ-013/14/15 gap
    caught the day before in audit_findings_2026_05_14_seven_silent_drifts).

    This file confirms the handlers fire on documented anti-patterns
    from `bft_package_integration_plan.md` and `mtheory_business_field_theory.md`
    and stay quiet on the canonical Mtheory shapes.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "drift_sentinel"))

from drift_scan import (  # noqa: E402
    Artifact,
    _check_decision_without_state_estimate,
    _check_forecast_without_confidence_bands,
    _check_interaction_without_cost,
    _check_interaction_without_effect_vector,
    _check_state_vector_substitution,
    _check_uncalibrated_forecast_as_authority,
)

_CRIT_010 = {
    "id": "CRIT-010",
    "severity": "critical",
    "remediation": "Use the canonical 9 variables exactly. See §5.19.",
}
_MAJ_016 = {
    "id": "MAJ-016",
    "severity": "major",
    "remediation": "Attach state vector estimate. §5.19.",
}
_MAJ_017 = {
    "id": "MAJ-017",
    "severity": "major",
    "remediation": "Surface p10/p50/p90 distribution. §5.19.",
}
_MAJ_018 = {
    "id": "MAJ-018",
    "severity": "major",
    "remediation": "Label as pre_mtheory or wait for calibration. §5.19.",
}
_MIN_007 = {
    "id": "MIN-007",
    "severity": "minor",
    "remediation": "Register in interaction_catalog with delta_i. §5.19.",
}
_MIN_008 = {
    "id": "MIN-008",
    "severity": "minor",
    "remediation": "Populate estimated_cost on the catalog entry. §5.19.",
}


def _py(name: str, body: str, identifier: str | None = None) -> Artifact:
    return Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier=identifier or f"engine/{name}.py",
        content=body,
        metadata={"ext": ".py", "repo": "ppeme", "size": len(body)},
    )


def _md(name: str, body: str) -> Artifact:
    return Artifact(
        source="local_codebase",
        artifact_type="markdown",
        identifier=f"docs/{name}.md",
        content=body,
        metadata={"ext": ".md", "repo": "ppeme", "size": len(body)},
    )


def _yaml(name: str, body: str) -> Artifact:
    return Artifact(
        source="local_codebase",
        artifact_type="config",
        identifier=f"specs/{name}.yaml",
        content=body,
        metadata={"ext": ".yaml", "repo": "ppeme", "size": len(body)},
    )


# ============================================================================
# CRIT-010 state_vector_substitution
# ============================================================================

def test_crit010_passes_canonical_nine() -> None:
    body = """
STATE_VARIABLES = [
    "trust", "attention", "clarity", "desire", "urgency",
    "value", "friction", "social_proof", "context_fit",
]
"""
    assert _check_state_vector_substitution(_py("state", body), _CRIT_010) == []


def test_crit010_fires_on_substitution() -> None:
    body = """
STATE_VARIABLES = [
    "trust", "engagement", "intent", "loyalty", "urgency",
    "value", "friction", "social_proof", "context_fit",
]
"""
    out = _check_state_vector_substitution(_py("bad_state", body), _CRIT_010)
    assert len(out) == 1
    assert out[0].rule_id == "CRIT-010"
    assert "engagement" in out[0].excerpt or "extra=" in out[0].excerpt


def test_crit010_edge_case_pre_mtheory_fixture_exempt() -> None:
    body = """
STATE_VARIABLES = ["a", "b", "c"]
"""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="tests/historical/pre_mtheory_state.py",
        content=body,
        metadata={"ext": ".py", "repo": "ppeme", "size": len(body)},
    )
    assert _check_state_vector_substitution(art, _CRIT_010) == []


def test_crit010_edge_case_noqa_suppresses() -> None:
    body = """
# noqa: CRIT-010 — intentional partial vector for unit test
STATE_VARIABLES = ["trust", "attention"]
"""
    assert _check_state_vector_substitution(_py("noqa_state", body), _CRIT_010) == []


# ============================================================================
# MAJ-016 decision_without_state_estimate
# ============================================================================

def test_maj016_passes_with_state_vector_field() -> None:
    body = """
cert = {
    "decision_class": "D3",
    "state_vector_at_decision": {"trust": 0.6, "attention": 0.5},
    "decision_id": "EC-123",
}
"""
    assert _check_decision_without_state_estimate(_py("cert_ok", body), _MAJ_016) == []


def test_maj016_fires_on_d3_missing_state() -> None:
    body = """
cert = {
    "decision_class": "D3",
    "decision_id": "EC-456",
    "owner": "todd",
}
"""
    out = _check_decision_without_state_estimate(_py("cert_bad", body), _MAJ_016)
    assert len(out) == 1
    assert out[0].rule_id == "MAJ-016"
    assert "D3" in out[0].excerpt


def test_maj016_edge_d1_exempt() -> None:
    body = """
cert = {
    "decision_class": "D1",
    "decision_id": "EC-789",
}
"""
    assert _check_decision_without_state_estimate(_py("d1_ok", body), _MAJ_016) == []


def test_maj016_edge_state_estimate_alias_accepted() -> None:
    body = """
cert = {
    "decision_class": "D5",
    "state_estimate": [0.1, 0.2, 0.3],
    "decision_id": "EC-321",
}
"""
    assert _check_decision_without_state_estimate(_py("alias_ok", body), _MAJ_016) == []


# ============================================================================
# MAJ-017 forecast_without_confidence_bands
# ============================================================================

def test_maj017_passes_with_p10_p50_p90() -> None:
    body = """
forecast = compute_forecast(state)
distribution = {"p10": 100, "p50": 200, "p90": 350}
return forecast, distribution
"""
    assert _check_forecast_without_confidence_bands(_py("fcst_ok", body), _MAJ_017) == []


def test_maj017_fires_on_single_point_forecast() -> None:
    body = """
def predict():
    forecast = 12345.67
    return forecast
"""
    out = _check_forecast_without_confidence_bands(_py("fcst_bad", body), _MAJ_017)
    assert len(out) >= 1
    assert out[0].rule_id == "MAJ-017"


def test_maj017_edge_monte_carlo_satisfies() -> None:
    body = """
def predict():
    forecast = run_monte_carlo(state, draws=10000)
    return forecast
"""
    assert _check_forecast_without_confidence_bands(_py("mc_ok", body), _MAJ_017) == []


def test_maj017_edge_noqa_suppresses() -> None:
    body = """
# noqa: MAJ-017 — historical fixture; calibration trusted
forecast = 999
"""
    assert _check_forecast_without_confidence_bands(_py("legacy", body), _MAJ_017) == []


# ============================================================================
# MAJ-018 uncalibrated_forecast_as_authority
# ============================================================================

def test_maj018_passes_with_calibration_label() -> None:
    body = """
forecast_id = "FCST-001"
pre_mtheory = True
return f"We recommend X driven by forecast {forecast_id}"
"""
    assert _check_uncalibrated_forecast_as_authority(_py("auth_ok", body), _MAJ_018) == []


def test_maj018_fires_on_unlabeled_authority_use() -> None:
    body = """
forecast_id = "FCST-002"
recommend(strategy="aggressive", driver=forecast_id)
"""
    out = _check_uncalibrated_forecast_as_authority(_py("auth_bad", body), _MAJ_018)
    assert len(out) >= 1
    assert out[0].rule_id == "MAJ-018"


def test_maj018_edge_no_authority_verb_no_fire() -> None:
    body = """
forecast_id = "FCST-003"
log.debug(f"forecast id {forecast_id}")
"""
    assert _check_uncalibrated_forecast_as_authority(_py("log_only", body), _MAJ_018) == []


def test_maj018_edge_production_grade_label_accepted() -> None:
    body = """
forecast_id = "FCST-004"
calibration_status = "production_grade"
recommend(forecast_id)
"""
    assert _check_uncalibrated_forecast_as_authority(_py("prod_grade", body), _MAJ_018) == []


# ============================================================================
# MIN-007 interaction_without_effect_vector
# ============================================================================

def test_min007_passes_with_catalog_link() -> None:
    body = """
from ppeme.interaction_catalog import lookup_delta_i
def handler():
    delta_i = lookup_delta_i("button_signup_click")
    emit_event("button_signup_click", delta_i=delta_i)
"""
    assert _check_interaction_without_effect_vector(_py("emit_ok", body), _MIN_007) == []


def test_min007_fires_on_uncatalogued_emit() -> None:
    body = """
def handler():
    emit_event("random_button", payload={"foo": "bar"})
    log.info("done")
"""
    out = _check_interaction_without_effect_vector(_py("emit_bad", body), _MIN_007)
    assert len(out) >= 1
    assert out[0].rule_id == "MIN-007"


def test_min007_edge_tests_dir_exempt() -> None:
    body = """
def test_thing():
    emit_event("test_event")
"""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="tests/test_emit.py",
        content=body,
        metadata={"ext": ".py", "repo": "ppeme", "size": len(body)},
    )
    assert _check_interaction_without_effect_vector(art, _MIN_007) == []


def test_min007_edge_noqa_suppresses() -> None:
    body = """
# noqa: MIN-007 — emitted for telemetry only, catalog entry pending
emit_event("telemetry_ping")
"""
    assert _check_interaction_without_effect_vector(_py("telemetry", body), _MIN_007) == []


# ============================================================================
# MIN-008 interaction_without_cost
# ============================================================================

def test_min008_passes_when_estimated_cost_present() -> None:
    body = """
interaction_catalog.upsert(
    interaction_id="signup_click",
    delta_i=[0.1, 0.2],
    estimated_cost=0.05,
)
"""
    assert _check_interaction_without_cost(_py("cost_ok", body), _MIN_008) == []


def test_min008_fires_on_missing_cost() -> None:
    body = """
interaction_catalog.insert(
    interaction_id="newsletter_open",
    delta_i=[0.01, 0.02, 0.03],
)
"""
    out = _check_interaction_without_cost(_py("cost_bad", body), _MIN_008)
    assert len(out) >= 1
    assert out[0].rule_id == "MIN-008"


def test_min008_edge_sql_insert_with_cost() -> None:
    body = """
INSERT INTO interaction_catalog (interaction_id, delta_i, estimated_cost)
VALUES ('homepage_cta', '[0.4,0.2]', 0.03);
"""
    art = Artifact(
        source="local_codebase",
        artifact_type="config",
        identifier="db/seeds/interactions.sql",
        content=body,
        metadata={"ext": ".sql", "repo": "ppeme", "size": len(body)},
    )
    assert _check_interaction_without_cost(art, _MIN_008) == []


def test_min008_edge_noqa_suppresses() -> None:
    body = """
# noqa: MIN-008 — cost calibration pending vertical rollout
interaction_catalog.create(interaction_id="trial_modal")
"""
    assert _check_interaction_without_cost(_py("noqa_cost", body), _MIN_008) == []
