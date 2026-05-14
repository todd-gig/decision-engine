"""penrose — falsification scoreboard v0.6 (8/8 metrics endpoint).

Covers:
  - each of the 8 metric methods returns the expected shape + types
  - codification rate counts certificates in window
  - override rate aggregates by class
  - decision velocity returns median (synthetic data)
  - OVS variance reads CalibrationRevisions
  - cascade multiplier reads AttributionLinks
  - network_value returns stub structure (NOT a number)
  - revenue_per_human_touch returns count + null revenue when env unset
  - drift_critical_count reads from drift_history.db
  - snapshot() includes all 8 keys
  - HTTP endpoints return JSON
  - /v1/penrose/network-value/record accepts valid body + 422 on invalid

penrose_signal: weakens
penrose_dimension: codification | override_rate | velocity | variance |
                   cascade | network_value | revenue_per_touch | drift_count
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.penrose import (
    METRIC_NAMES,
    NETWORK_VALUE_STATE_DIMENSIONS,
    PENROSE_SCOREBOARD_VERSION,
    ScoreboardSnapshot,
    compute_decision_velocity,
    count_human_touches,
    list_observations,
    record_decision_timing,
    record_participant_bft_state,
)
from engine.penrose import scoreboard as scoreboard_mod
from engine.penrose import velocity as velocity_mod
from engine.penrose import network_value_emitter as nve_mod


# ── Fixtures ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
def isolated_paths(tmp_path: Path):
    """Each test gets its own SQLite paths — no shared state between tests."""
    return {
        "codification_db_path": str(tmp_path / "codification_proposals.db"),
        "overrides_db_path": str(tmp_path / "human_overrides.db"),
        "ovs_db_path": str(tmp_path / "ovs_calibration.db"),
        "penrose_db_path": str(tmp_path / "penrose_scoreboard.db"),
        "drift_db_path": str(tmp_path / "drift_history.db"),
    }


@pytest.fixture
def snapshot(isolated_paths) -> ScoreboardSnapshot:
    return ScoreboardSnapshot(**isolated_paths)


# ── DB seeders ──────────────────────────────────────────────────────────────


def _seed_codification_certs(db_path: str, count: int, days_ago: int = 5) -> None:
    """Create the table + insert `count` certificates within the window."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS codification_certificates (
                id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                signers TEXT NOT NULL,
                decision_class TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                evidence_decision_ids TEXT NOT NULL,
                proposed_spec TEXT NOT NULL,
                hmac TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                md_path TEXT
            )
            """
        )
        ts = _iso(_now() - timedelta(days=days_ago))
        for i in range(count):
            conn.execute(
                """
                INSERT INTO codification_certificates VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"CDC-{i:08X}",
                    f"cand-{i}",
                    json.dumps(["todd@gigaton.ai"]),
                    "new-module",
                    "Pattern observed >50 times with <5% exception rate.",
                    json.dumps([f"DEC-{i}"]),
                    "def x(): pass",
                    "deadbeef",
                    ts,
                    "v1.0",
                    "v1.0",
                    None,
                ),
            )
    finally:
        conn.close()


def _seed_overrides(db_path: str, count: int, days_ago: int = 2,
                    override_type: str = "reversal",
                    id_prefix: str = "") -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS human_overrides (
                override_id TEXT PRIMARY KEY,
                decision_id TEXT,
                decision_certificate_id TEXT,
                override_type TEXT NOT NULL,
                overridden_by_user_id TEXT NOT NULL,
                overridden_at TEXT NOT NULL,
                source_engine TEXT NOT NULL,
                surface TEXT NOT NULL,
                original_action TEXT NOT NULL,
                override_action TEXT NOT NULL,
                user_reasoning TEXT,
                freeform_metadata TEXT,
                classification TEXT NOT NULL,
                signature TEXT,
                sent_to_ovs_at TEXT,
                sent_to_codification_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ts = _iso(_now() - timedelta(days=days_ago))
        cls_json = json.dumps({
            "type": override_type,
            "ovs_weight": 3.0,
            "codification_action": "open_exception_case_now",
        })
        for i in range(count):
            conn.execute(
                """
                INSERT INTO human_overrides
                    (override_id, decision_id, decision_certificate_id,
                     override_type, overridden_by_user_id, overridden_at,
                     source_engine, surface, original_action,
                     override_action, user_reasoning, freeform_metadata,
                     classification, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"OV-{id_prefix}{override_type[:3]}-{i:08X}-{uuid.uuid4().hex[:6]}",
                    f"DEC-{id_prefix}{override_type[:3]}-{i}",
                    f"EC-{id_prefix}{override_type[:3]}-{i}",
                    override_type,
                    f"user-{i % 3}",
                    ts,
                    "sales-os",
                    "operator:detail",
                    "auto_send",
                    "hold",
                    "client budget exceeded by 30 percent",
                    None,
                    cls_json,
                    "sig-deadbeef",
                ),
            )
    finally:
        conn.close()


def _seed_ovs(db_path: str, revisions: list[tuple[float, float]],
              attribution_multipliers: list[float]) -> None:
    """Create the ovs_calibration tables + seed revisions + attribution links."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS calibration_revisions (
                id TEXT PRIMARY KEY,
                dimension TEXT NOT NULL,
                before_value REAL NOT NULL,
                after_value REAL NOT NULL,
                evidence_window_start TEXT NOT NULL,
                evidence_window_end TEXT NOT NULL,
                evidence_outcome_ids TEXT NOT NULL,
                computation_version TEXT NOT NULL,
                signed_by TEXT NOT NULL,
                hmac TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                md_path TEXT,
                schema_version TEXT NOT NULL DEFAULT 'v1'
            );
            CREATE TABLE IF NOT EXISTS attribution_links (
                id TEXT PRIMARY KEY,
                decision_certificate_id TEXT NOT NULL,
                outcome_event_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                attribution_method TEXT NOT NULL,
                layer_number INTEGER NOT NULL,
                cascade_multiplier REAL NOT NULL DEFAULT 1.0,
                attributed_at TEXT NOT NULL,
                attributed_by TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                schema_version TEXT NOT NULL DEFAULT 'v1'
            );
            """
        )
        ts = _iso(_now() - timedelta(days=3))
        for i, (bv, av) in enumerate(revisions):
            conn.execute(
                """
                INSERT INTO calibration_revisions VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"REV-{i:04X}", "trust.evidence_quality", bv, av,
                    ts, ts, json.dumps([]),
                    "v1", "todd@gigaton.ai", "hmac-abc", ts,
                    "calibration evidence window closed", None, "v1",
                ),
            )
        for i, mult in enumerate(attribution_multipliers):
            conn.execute(
                """
                INSERT INTO attribution_links VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"ATR-{i:04X}", f"EC-{i}", f"OUT-{i}", 0.8,
                    "temporal", 3, mult, ts, "system", "stage 2", "v1",
                ),
            )
    finally:
        conn.close()


def _seed_drift_scan(db_path: str, critical: int = 0, major: int = 1,
                     minor: int = 5, info: int = 0) -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                sources TEXT NOT NULL,
                total_artifacts INTEGER NOT NULL,
                critical INTEGER NOT NULL,
                major INTEGER NOT NULL,
                minor INTEGER NOT NULL,
                info INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                artifact TEXT NOT NULL,
                location TEXT,
                excerpt TEXT
            );
            """
        )
        ts = _iso(_now())
        conn.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?,?,?,?)",
            ("SCAN-PENROSE-TEST", ts, "local_codebase", 1500,
             critical, major, minor, info),
        )
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────────────────
# 1. Codification Rate
# ────────────────────────────────────────────────────────────────────────────


def test_codification_rate_counts_certificates_in_window(snapshot, isolated_paths):
    _seed_codification_certs(isolated_paths["codification_db_path"], count=6,
                             days_ago=10)
    body = snapshot.codification_rate(window_days=30)
    assert body["metric"] == "codification_rate"
    assert body["window_days"] == 30
    assert body["patterns_promoted"] == 6
    # 6 certs in 30 days, normalized to 90 days = 18
    assert body["value"] == pytest.approx(18.0, rel=1e-3)
    assert body["penrose_signal"] == "weakens"
    assert body["trend_target"] == "up"
    assert "computed_at" in body


def test_codification_rate_zero_when_db_missing(snapshot):
    body = snapshot.codification_rate()
    assert body["patterns_promoted"] == 0
    assert body["value"] == 0.0
    assert body["penrose_signal"] == "neutral"


# ────────────────────────────────────────────────────────────────────────────
# 2. Human Override Rate
# ────────────────────────────────────────────────────────────────────────────


def test_human_override_rate_aggregates_by_class(snapshot, isolated_paths):
    _seed_overrides(isolated_paths["overrides_db_path"], count=4,
                    override_type="reversal")
    _seed_overrides(isolated_paths["overrides_db_path"], count=2,
                    override_type="modification")
    body = snapshot.human_override_rate(window_days=30)
    assert body["metric"] == "human_override_rate"
    assert body["total_overrides"] == 6
    assert set(body["by_class"]) == {"reversal", "modification"}
    assert body["by_class"]["reversal"]["override_count"] == 4
    assert body["by_class"]["modification"]["override_count"] == 2
    assert body["penrose_signal"] == "strengthens"


def test_human_override_rate_empty_returns_neutral(snapshot):
    body = snapshot.human_override_rate()
    assert body["total_overrides"] == 0
    assert body["by_class"] == {}
    assert body["penrose_signal"] == "neutral"


# ────────────────────────────────────────────────────────────────────────────
# 3. Decision Velocity
# ────────────────────────────────────────────────────────────────────────────


def test_decision_velocity_returns_median_on_synthetic_data(isolated_paths):
    p = isolated_paths["penrose_db_path"]
    start = _now() - timedelta(minutes=10)
    record_decision_timing("DEC-1", "D1", _iso(start),
                           _iso(start + timedelta(seconds=2)),
                           db_path=p)
    record_decision_timing("DEC-2", "D1", _iso(start),
                           _iso(start + timedelta(seconds=4)),
                           db_path=p)
    record_decision_timing("DEC-3", "D1", _iso(start),
                           _iso(start + timedelta(seconds=6)),
                           db_path=p)
    record_decision_timing("DEC-4", "D3", _iso(start),
                           _iso(start + timedelta(seconds=20)),
                           db_path=p)
    body = compute_decision_velocity(window_days=30, db_path=p)
    assert body["overall_sample_count"] == 4
    assert body["by_class"]["D1"]["median_seconds"] == 4.0
    assert body["by_class"]["D1"]["sample_count"] == 3
    assert body["by_class"]["D3"]["median_seconds"] == 20.0
    assert body["overall_median_seconds"] == 5.0


def test_decision_velocity_graceful_empty(snapshot):
    body = snapshot.decision_velocity()
    assert body["metric"] == "decision_velocity"
    assert body["overall_sample_count"] == 0
    assert body["overall_median_seconds"] is None
    assert body["by_class"] == {}
    assert body["penrose_signal"] == "neutral"
    assert body["trend_target"] == "down"


def test_decision_velocity_completed_at_optional(isolated_paths):
    """A row inserted without completed_at should not surface in median."""
    p = isolated_paths["penrose_db_path"]
    start = _iso(_now() - timedelta(minutes=5))
    record_decision_timing("DEC-OPEN", "D1", start, completed_at=None,
                           db_path=p)
    body = compute_decision_velocity(window_days=30, db_path=p)
    assert body["overall_sample_count"] == 0


# ────────────────────────────────────────────────────────────────────────────
# 4. OVS Variance
# ────────────────────────────────────────────────────────────────────────────


def test_ovs_variance_reads_calibration_revisions(snapshot, isolated_paths):
    # Two revisions: 0.5→0.6 (20% delta) and 1.0→0.8 (20% delta) — mean = 0.20
    _seed_ovs(
        isolated_paths["ovs_db_path"],
        revisions=[(0.5, 0.6), (1.0, 0.8)],
        attribution_multipliers=[],
    )
    body = snapshot.ovs_variance(window_days=30)
    assert body["metric"] == "ovs_variance"
    assert body["sample_count"] == 2
    assert body["value"] == pytest.approx(0.2, abs=1e-6)
    assert body["penrose_signal"] == "weakens"


def test_ovs_variance_empty_returns_none(snapshot):
    body = snapshot.ovs_variance()
    assert body["value"] is None
    assert body["sample_count"] == 0


# ────────────────────────────────────────────────────────────────────────────
# 5. Cascade Multiplier
# ────────────────────────────────────────────────────────────────────────────


def test_cascade_multiplier_reads_attribution_links(snapshot, isolated_paths):
    _seed_ovs(
        isolated_paths["ovs_db_path"],
        revisions=[],
        attribution_multipliers=[2.0, 2.2, 2.4],
    )
    body = snapshot.cascade_multiplier()
    assert body["metric"] == "cascade_multiplier"
    assert body["sample_count"] == 3
    assert body["value"] == pytest.approx(2.2, abs=1e-6)
    # within ±15% of target 2.2 → weakens Penrose
    assert body["penrose_signal"] == "weakens"
    assert body["target"] == 2.2


def test_cascade_multiplier_off_target_neutral(snapshot, isolated_paths):
    _seed_ovs(
        isolated_paths["ovs_db_path"],
        revisions=[],
        attribution_multipliers=[1.0, 1.0, 1.0],
    )
    body = snapshot.cascade_multiplier()
    assert body["value"] == pytest.approx(1.0)
    # Well outside 15% band → neutral, not strengthens
    assert body["penrose_signal"] == "neutral"


# ────────────────────────────────────────────────────────────────────────────
# 6. Super-Additive Network Value (STUB — never a number)
# ────────────────────────────────────────────────────────────────────────────


def test_network_value_returns_stub_structure(snapshot):
    body = snapshot.super_additive_network_value()
    assert body["status"] == "awaiting_ppeme_wiring"
    assert body["value"] is None
    assert "formula" in body
    assert "next_milestone" in body
    assert body["next_milestone"].startswith("PPEME")
    assert body["metric"] == "super_additive_network_value"
    assert body["observations_received"] == 0


def test_network_value_record_canonical_9(isolated_paths):
    p = isolated_paths["penrose_db_path"]
    sv = {k: 0.5 for k in NETWORK_VALUE_STATE_DIMENSIONS}
    body = record_participant_bft_state("user-1", sv, db_path=p)
    assert body["participant_id"] == "user-1"
    assert body["state_vector"] == sv
    rows = list_observations(db_path=p)
    assert len(rows) == 1


def test_network_value_record_rejects_non_canonical(isolated_paths):
    p = isolated_paths["penrose_db_path"]
    with pytest.raises(ValueError, match="canonical 9 variables"):
        record_participant_bft_state("u", {"trust": 0.5}, db_path=p)


# ────────────────────────────────────────────────────────────────────────────
# 7. Revenue per Human-Touch
# ────────────────────────────────────────────────────────────────────────────


def test_revenue_per_human_touch_returns_count_and_null_revenue_when_env_unset(
    snapshot, isolated_paths, monkeypatch
):
    monkeypatch.delenv(scoreboard_mod.REVENUE_USD_OVERRIDE_ENV, raising=False)
    _seed_overrides(isolated_paths["overrides_db_path"], count=3)
    body = snapshot.revenue_per_human_touch(window_days=90)
    assert body["metric"] == "revenue_per_human_touch"
    assert body["value"] is None
    assert body["revenue_usd"] is None
    assert body["human_touches"]["total_touches"] == 3
    assert body["human_touches"]["override_touches"] == 3
    assert body["next_milestone"] is not None


def test_revenue_per_human_touch_uses_env_override(
    snapshot, isolated_paths, monkeypatch
):
    monkeypatch.setenv(scoreboard_mod.REVENUE_USD_OVERRIDE_ENV, "5000.00")
    _seed_overrides(isolated_paths["overrides_db_path"], count=4)
    body = snapshot.revenue_per_human_touch(window_days=90)
    assert body["revenue_usd"] == 5000.00
    assert body["value"] == pytest.approx(1250.0, abs=1e-3)
    assert body["revenue_source"] == f"env:{scoreboard_mod.REVENUE_USD_OVERRIDE_ENV}"


def test_count_human_touches_dedups_decisions(isolated_paths):
    _seed_overrides(isolated_paths["overrides_db_path"], count=5)
    s = count_human_touches(
        window_days=30,
        overrides_db_path=isolated_paths["overrides_db_path"],
        codification_db_path=isolated_paths["codification_db_path"],
    )
    assert s.override_touches == 5
    assert s.unique_decision_ids_touched == 5
    assert s.codification_signer_touches == 0


# ────────────────────────────────────────────────────────────────────────────
# 8. Drift Critical Count
# ────────────────────────────────────────────────────────────────────────────


def test_drift_critical_count_reads_latest_scan(snapshot, isolated_paths):
    _seed_drift_scan(isolated_paths["drift_db_path"],
                     critical=0, major=3, minor=11, info=0)
    body = snapshot.drift_critical_count()
    assert body["metric"] == "drift_critical_count"
    assert body["value"] == 0
    assert body["major"] == 3
    assert body["minor"] == 11
    assert body["penrose_signal"] == "weakens"   # 0 critical = doctrine win


def test_drift_critical_count_with_criticals_strengthens(snapshot, isolated_paths):
    _seed_drift_scan(isolated_paths["drift_db_path"], critical=2)
    body = snapshot.drift_critical_count()
    assert body["value"] == 2
    assert body["penrose_signal"] == "strengthens"


def test_drift_critical_count_missing_db_returns_none(snapshot):
    body = snapshot.drift_critical_count()
    assert body["value"] is None
    assert body["status"] in {"drift_history_unavailable", "no_scans_recorded"}


# ────────────────────────────────────────────────────────────────────────────
# snapshot() — full aggregate
# ────────────────────────────────────────────────────────────────────────────


def test_snapshot_includes_all_eight_metrics(snapshot):
    snap = snapshot.snapshot()
    assert snap["scoreboard_version"] == PENROSE_SCOREBOARD_VERSION
    assert set(snap["metrics"]) == set(METRIC_NAMES)
    assert len(snap["metrics"]) == 8
    # Every metric carries a penrose_signal label
    for name, body in snap["metrics"].items():
        # Stubs carry status= and value=None; others carry penrose_signal
        if body.get("status") == "awaiting_ppeme_wiring":
            assert body["value"] is None
        assert "penrose_signal" in body or body.get("status"), (
            f"{name} missing both signal and status"
        )


def test_snapshot_signals_summary_buckets(snapshot, isolated_paths):
    _seed_codification_certs(isolated_paths["codification_db_path"], count=2)
    snap = snapshot.snapshot()
    summary = snap["signals_summary"]
    # network_value always counted as stub
    assert summary["stub"] >= 1
    # codification with rows → weakens
    assert summary["weakens"] >= 1


# ────────────────────────────────────────────────────────────────────────────
# HTTP endpoints
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with the scoreboard pinned to a tmp DB tree."""
    from fastapi.testclient import TestClient
    from api.main import app

    paths = {
        "codification_db_path": str(tmp_path / "codification_proposals.db"),
        "overrides_db_path": str(tmp_path / "human_overrides.db"),
        "ovs_db_path": str(tmp_path / "ovs_calibration.db"),
        "penrose_db_path": str(tmp_path / "penrose_scoreboard.db"),
        "drift_db_path": str(tmp_path / "drift_history.db"),
    }

    original_init = ScoreboardSnapshot.__init__

    def patched_init(self, **kwargs):
        merged = {**paths, **kwargs}
        original_init(self, **merged)

    monkeypatch.setattr(ScoreboardSnapshot, "__init__", patched_init)

    # network-value POST uses module-level path resolution, not the
    # snapshot; patch its DB resolver to the same tmp file.
    monkeypatch.setattr(
        velocity_mod, "_default_db_path",
        lambda: Path(paths["penrose_db_path"]),
    )

    return TestClient(app)


def test_endpoint_scoreboard_returns_json(client):
    r = client.get("/v1/penrose/scoreboard")
    assert r.status_code == 200
    body = r.json()
    assert body["scoreboard_version"] == PENROSE_SCOREBOARD_VERSION
    assert set(body["metrics"]) == set(METRIC_NAMES)


def test_endpoint_single_metric_returns_detail(client):
    r = client.get("/v1/penrose/scoreboard/codification_rate?window_days=60")
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "codification_rate"
    assert body["window_days"] == 60


def test_endpoint_unknown_metric_404(client):
    r = client.get("/v1/penrose/scoreboard/totally_not_a_metric")
    assert r.status_code == 404


def test_endpoint_network_value_record_valid(client):
    payload = {
        "participant_id": "user-test",
        "state_vector": {k: 0.5 for k in NETWORK_VALUE_STATE_DIMENSIONS},
    }
    r = client.post("/v1/penrose/network-value/record", json=payload)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["participant_id"] == "user-test"
    assert "id" in body
    assert body["state_vector"]["trust"] == 0.5


def test_endpoint_network_value_record_422_on_invalid_state(client):
    # 422 from emitter ValueError (non-canonical vector)
    payload = {
        "participant_id": "user-test",
        "state_vector": {"trust": 0.5, "unknown_var": 0.1},
    }
    r = client.post("/v1/penrose/network-value/record", json=payload)
    assert r.status_code == 422


def test_endpoint_network_value_record_422_on_missing_field(client):
    r = client.post("/v1/penrose/network-value/record", json={})
    # Pydantic body validation → 422 (no participant_id)
    assert r.status_code == 422
