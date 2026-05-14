"""Tests for `scripts/bootstrap_outcome_sources.py` + startup gate.

Coverage:
  - bootstrap_all registers 3 sources when none exist
  - bootstrap_all is idempotent (running twice doesn't duplicate)
  - bootstrap_one with --source carmen-beach-revenue registers just that
  - dry-run produces no DB writes
  - schema validates booking_id required (Carmen Beach spec)
  - startup-gate honors PENROSE_BOOTSTRAP_SOURCES=0 (no auto-register)

penrose_signal: weakens
penrose_dimension: revenue_per_human_touch
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ovs_calibration import list_sources
from scripts.bootstrap_outcome_sources import (
    CANONICAL_SOURCES,
    CARMEN_BEACH_REVENUE,
    GIGATON_UI_USAGE,
    TI_SOLUTIONS_CONVERSION,
    BootstrapResult,
    bootstrap_all,
    bootstrap_one,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "ovs_calibration.db")


# ── bootstrap_all ───────────────────────────────────────────────────────────


def test_bootstrap_all_registers_three_when_none_exist(tmp_db):
    results = bootstrap_all(idempotent=True, db_path=tmp_db)
    assert len(results) == 3
    assert all(isinstance(r, BootstrapResult) for r in results)
    statuses = sorted(r.status for r in results)
    assert statuses == ["registered", "registered", "registered"]

    # Verify each canonical source landed in the DB
    rows = list_sources(db_path=tmp_db)
    assert len(rows) == 3
    names = {r["name"] for r in rows}
    assert names == {
        "carmen-beach-revenue",
        "ti-solutions-conversion",
        "gigaton-ui-usage",
    }


def test_bootstrap_all_is_idempotent(tmp_db):
    """Second invocation returns already_registered, not duplicate rows."""
    first = bootstrap_all(idempotent=True, db_path=tmp_db)
    assert all(r.status == "registered" for r in first)

    second = bootstrap_all(idempotent=True, db_path=tmp_db)
    assert all(r.status == "already_registered" for r in second)

    # Still exactly 3 rows
    rows = list_sources(db_path=tmp_db)
    assert len(rows) == 3


def test_bootstrap_all_persists_decision_class_map(tmp_db):
    """The decision_class_metric_map round-trips through register_source."""
    bootstrap_all(idempotent=True, db_path=tmp_db)
    cb_rows = list_sources(entity="carmen-beach", db_path=tmp_db)
    assert len(cb_rows) == 1
    row = cb_rows[0]
    assert row["decision_class_metric_map"] == {
        "pricing.dynamic.carmen-beach": "revenue.daily.unit",
        "pricing.adr.carmen-beach":     "revenue.adr.unit",
    }


def test_bootstrap_all_rejects_non_idempotent_mode(tmp_db):
    with pytest.raises(ValueError, match="non-idempotent"):
        bootstrap_all(idempotent=False, db_path=tmp_db)


# ── bootstrap_one ───────────────────────────────────────────────────────────


def test_bootstrap_one_registers_just_carmen_beach(tmp_db):
    result = bootstrap_one("carmen-beach-revenue", db_path=tmp_db)
    assert result.status == "registered"
    assert result.entity == "carmen-beach"
    assert result.source_id is not None

    rows = list_sources(db_path=tmp_db)
    assert len(rows) == 1
    assert rows[0]["name"] == "carmen-beach-revenue"


def test_bootstrap_one_idempotent_on_rerun(tmp_db):
    bootstrap_one("ti-solutions-conversion", db_path=tmp_db)
    again = bootstrap_one("ti-solutions-conversion", db_path=tmp_db)
    assert again.status == "already_registered"
    rows = list_sources(db_path=tmp_db)
    assert len(rows) == 1


def test_bootstrap_one_unknown_name_raises():
    with pytest.raises(KeyError, match="unknown canonical source"):
        bootstrap_one("nonexistent-source")


# ── dry-run ─────────────────────────────────────────────────────────────────


def test_dry_run_produces_no_db_writes(tmp_db):
    results = bootstrap_all(idempotent=True, dry_run=True, db_path=tmp_db)
    assert all(r.status == "dry_run" for r in results)
    # No rows written
    rows = list_sources(db_path=tmp_db)
    assert rows == []


def test_dry_run_one_source_produces_no_writes(tmp_db):
    result = bootstrap_one("gigaton-ui-usage", dry_run=True, db_path=tmp_db)
    assert result.status == "dry_run"
    assert result.source_id is None
    # The body still describes what WOULD have been registered
    assert result.body["entity"] == "gigaton-ui"
    assert result.body["kind"] == "operational"
    rows = list_sources(db_path=tmp_db)
    assert rows == []


# ── schema validation ──────────────────────────────────────────────────────


def test_carmen_beach_schema_requires_booking_id():
    """booking_id is the idempotency key + therefore required in the schema."""
    schema = CARMEN_BEACH_REVENUE.schema
    assert "booking_id" in schema["required"]
    assert "unit_id" in schema["required"]
    assert "gross_usd" in schema["required"]


def test_carmen_beach_schema_persisted_to_db(tmp_db):
    """After register, the registry row carries the full schema."""
    bootstrap_one("carmen-beach-revenue", db_path=tmp_db)
    rows = list_sources(entity="carmen-beach", db_path=tmp_db)
    assert len(rows) == 1
    schema = rows[0]["schema"]
    assert "booking_id" in schema["required"]
    assert schema["properties"]["gross_usd"]["minimum"] == 0


def test_canonical_sources_have_complete_metadata():
    """All canonical sources have non-empty owner + ingestion contract + map."""
    for spec in CANONICAL_SOURCES.values():
        assert spec.owner
        assert spec.ingestion_contract in {"pubsub", "webhook", "polling"}
        assert spec.kind in {"revenue", "conversion", "operational",
                             "satisfaction", "external"}
        assert spec.decision_class_metric_map, (
            f"{spec.name}: decision_class_metric_map must not be empty"
        )
        assert spec.schema.get("required"), (
            f"{spec.name}: schema must declare required fields"
        )


def test_ti_solutions_schema_required_fields():
    schema = TI_SOLUTIONS_CONVERSION.schema
    assert set(schema["required"]) >= {"deal_id", "stage", "transitioned_at"}


def test_gigaton_ui_schema_required_fields():
    schema = GIGATON_UI_USAGE.schema
    assert set(schema["required"]) >= {"user_id", "feature", "event", "occurred_at"}


# ── startup gate ───────────────────────────────────────────────────────────


def test_startup_gate_honors_disabled_env(monkeypatch):
    """PENROSE_BOOTSTRAP_SOURCES=0 keeps the gate closed."""
    from api import main as api_main
    monkeypatch.setenv("PENROSE_BOOTSTRAP_SOURCES", "0")
    assert api_main._bootstrap_sources_enabled() is False

    monkeypatch.setenv("PENROSE_BOOTSTRAP_SOURCES", "")
    assert api_main._bootstrap_sources_enabled() is False

    monkeypatch.delenv("PENROSE_BOOTSTRAP_SOURCES", raising=False)
    assert api_main._bootstrap_sources_enabled() is False


def test_startup_gate_truthy_values(monkeypatch):
    from api import main as api_main
    for truthy in ("1", "true", "TRUE", "yes", "YES", "on", "On"):
        monkeypatch.setenv("PENROSE_BOOTSTRAP_SOURCES", truthy)
        assert api_main._bootstrap_sources_enabled() is True, (
            f"expected truthy for {truthy!r}"
        )


def test_startup_gate_does_not_fire_when_disabled(monkeypatch, tmp_db):
    """The startup hook is a no-op when the env is unset.

    We invoke the hook directly (vs spinning up an ASGI app) so the
    assertion is against the function's contract, not the framework.
    """
    from api import main as api_main
    monkeypatch.delenv("PENROSE_BOOTSTRAP_SOURCES", raising=False)
    # Direct invocation; should NOT call into bootstrap_all
    api_main._maybe_bootstrap_outcome_sources()
    # No-op; no exceptions raised.


def test_startup_gate_fires_when_enabled(monkeypatch, tmp_path):
    """When env=1, the hook calls bootstrap_all and logs counts."""
    from api import main as api_main

    calls: list[bool] = []

    def _fake_bootstrap_all(*, idempotent: bool = True):
        calls.append(idempotent)
        return []  # empty result is fine; we're testing the call

    monkeypatch.setenv("PENROSE_BOOTSTRAP_SOURCES", "1")
    monkeypatch.setattr(
        "scripts.bootstrap_outcome_sources.bootstrap_all",
        _fake_bootstrap_all,
    )
    api_main._maybe_bootstrap_outcome_sources()
    assert calls == [True]


def test_startup_gate_non_blocking_on_failure(monkeypatch):
    """Bootstrap failure must NOT propagate out of the startup hook."""
    from api import main as api_main

    def _boom(*, idempotent: bool = True):
        raise RuntimeError("simulated bootstrap explosion")

    monkeypatch.setenv("PENROSE_BOOTSTRAP_SOURCES", "1")
    monkeypatch.setattr(
        "scripts.bootstrap_outcome_sources.bootstrap_all",
        _boom,
    )
    # Should not raise — startup must remain healthy
    api_main._maybe_bootstrap_outcome_sources()


# ── per-entity revenue route ────────────────────────────────────────────────


def test_per_entity_revenue_endpoint_smoke(tmp_path, monkeypatch):
    """GET /v1/penrose/revenue/touch-rate returns by_entity panel.

    Smoke test: with empty DBs, we expect known entities present + value=None.
    """
    # Point the helper at isolated DBs (none exist -> empty panel)
    from engine.penrose import revenue_per_touch_by_entity
    body = revenue_per_touch_by_entity(
        window_days=30,
        ovs_db_path=tmp_path / "ovs.db",
        overrides_db_path=tmp_path / "ov.db",
        codification_db_path=tmp_path / "cod.db",
    )
    assert body["window_days"] == 30
    entities = {row["entity"] for row in body["by_entity"]}
    assert {"carmen-beach", "ti-solutions", "gigaton-ui"} <= entities
    # Every row has explicit null value since nothing's ingested
    for row in body["by_entity"]:
        assert row["value"] is None
        assert row["revenue_usd"] == 0
        assert row["total_touches"] == 0
    assert body["codification_touches_pooled"] == 0


def test_per_entity_revenue_route_via_fastapi(tmp_path, monkeypatch):
    """End-to-end through FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    resp = client.get("/v1/penrose/revenue/touch-rate?window_days=14")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 14
    assert "by_entity" in body
    assert isinstance(body["by_entity"], list)


def test_per_entity_revenue_route_rejects_bad_window():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    assert client.get("/v1/penrose/revenue/touch-rate?window_days=0").status_code == 422
    assert client.get("/v1/penrose/revenue/touch-rate?window_days=1000").status_code == 422
