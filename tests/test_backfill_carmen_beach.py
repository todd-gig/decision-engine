"""Tests for `scripts/backfill_carmen_beach_revenue.py`.

Coverage:
  - reads CSV correctly
  - dedups on booking_id (within CSV + against existing DB rows)
  - direct-write mode bypasses topic publish (writes to ovs_calibration.db)
  - dry-run produces no side effects
  - schema validates booking_id required + numeric gross_usd
  - pubsub-mode reports unavailable when env unset

penrose_signal: weakens
penrose_dimension: revenue_per_human_touch
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ovs_calibration import storage as ovs_storage
from scripts.backfill_carmen_beach_revenue import (
    BackfillReport,
    BackfillValidationError,
    _row_to_adapter_message,
    _validate_row,
    run_backfill,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _write_csv(path: Path, rows: list[dict]) -> Path:
    """Write a CSV with the canonical columns from `rows[0].keys()`."""
    if not rows:
        path.write_text(
            "booking_id,unit_id,check_in,check_out,gross_usd\n",
            encoding="utf-8",
        )
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _make_row(booking_id: str = "BK-001", **overrides) -> dict:
    base = {
        "booking_id": booking_id,
        "unit_id":    "UNIT-A",
        "check_in":   "2026-04-01",
        "check_out":  "2026-04-05",
        "gross_usd":  "1250.00",
        "net_usd":    "1100.00",
        "channel":    "Airbnb",
    }
    base.update(overrides)
    return base


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "ovs_calibration.db")


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    return tmp_path / "stvr.csv"


# ── Validation ─────────────────────────────────────────────────────────────


def test_validate_row_happy_path():
    raw = _make_row()
    norm = _validate_row(raw)
    assert norm["booking_id"] == "BK-001"
    assert norm["unit_id"] == "UNIT-A"
    assert norm["gross_usd"] == 1250.00
    assert norm["net_usd"] == 1100.00
    assert norm["channel"] == "Airbnb"


def test_validate_row_rejects_missing_booking_id():
    raw = _make_row(booking_id="")
    with pytest.raises(BackfillValidationError, match="missing required"):
        _validate_row(raw)


def test_validate_row_rejects_missing_unit_id():
    raw = _make_row(unit_id="")
    with pytest.raises(BackfillValidationError, match="missing required"):
        _validate_row(raw)


def test_validate_row_rejects_non_numeric_gross_usd():
    raw = _make_row(gross_usd="not-a-number")
    with pytest.raises(BackfillValidationError, match="numeric"):
        _validate_row(raw)


def test_validate_row_rejects_negative_gross_usd():
    raw = _make_row(gross_usd="-10")
    with pytest.raises(BackfillValidationError, match=">= 0"):
        _validate_row(raw)


def test_validate_row_accepts_empty_optional_net_usd():
    raw = _make_row(net_usd="")
    norm = _validate_row(raw)
    assert norm["net_usd"] is None


def test_row_to_adapter_message_aligns_with_adapter():
    """The adapter's transform is the single source of truth for shape."""
    raw = _make_row()
    norm = _validate_row(raw)
    msg = _row_to_adapter_message(norm)
    # metric aligns with the family the adapter emits for unit_id=UNIT-A
    assert msg.metric == "revenue.daily.UNIT-A"
    assert msg.observed_value == 1250.00
    assert msg.source_record_id == "BK-001"
    # check_out is what we used for observed_at (revenue recognition day)
    assert msg.observed_at.startswith("2026-04-05")


# ── dry-run mode ───────────────────────────────────────────────────────────


def test_dry_run_produces_no_db_writes(csv_path, tmp_db):
    _write_csv(csv_path, [_make_row("BK-1"), _make_row("BK-2")])
    report = run_backfill(csv_path, direct=True, dry_run=True, db_path=tmp_db)
    assert report.mode == "dry-run"
    assert report.rows_read == 2
    assert report.rows_dry_run == 2
    assert report.rows_persisted == 0

    # Verify nothing landed in the DB
    conn = ovs_storage.get_connection(tmp_db)
    try:
        rows = list(conn.execute("SELECT * FROM outcome_events"))
    finally:
        conn.close()
    assert rows == []


# ── direct-write mode ──────────────────────────────────────────────────────


def test_direct_mode_persists_rows(csv_path, tmp_db):
    _write_csv(csv_path, [_make_row("BK-1"), _make_row("BK-2", unit_id="UNIT-B")])
    report = run_backfill(csv_path, direct=True, db_path=tmp_db)
    assert report.mode == "direct"
    assert report.rows_read == 2
    assert report.rows_persisted == 2
    assert report.rows_published == 0
    assert report.rows_pubsub_unavailable == 0

    conn = ovs_storage.get_connection(tmp_db)
    try:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM outcome_events ORDER BY metric"))
    finally:
        conn.close()
    assert len(rows) == 2
    assert {r["metric"] for r in rows} == {"revenue.daily.UNIT-A", "revenue.daily.UNIT-B"}
    assert {r["source_record_id"] for r in rows} == {"BK-1", "BK-2"}
    assert {r["entity"] for r in rows} == {"carmen-beach"}


def test_direct_mode_dedups_within_csv(csv_path, tmp_db):
    """Two rows with same booking_id in one CSV produce one persisted row."""
    _write_csv(csv_path, [_make_row("BK-DUP"), _make_row("BK-DUP", gross_usd="9999")])
    report = run_backfill(csv_path, direct=True, db_path=tmp_db)
    assert report.rows_read == 2
    assert report.rows_persisted == 1
    assert report.duplicates_in_csv == 1

    conn = ovs_storage.get_connection(tmp_db)
    try:
        rows = list(conn.execute("SELECT * FROM outcome_events"))
    finally:
        conn.close()
    assert len(rows) == 1


def test_direct_mode_dedups_against_existing_db(csv_path, tmp_db):
    """Re-running backfill with same booking_id hits the adapter idempotency path."""
    _write_csv(csv_path, [_make_row("BK-A")])
    first = run_backfill(csv_path, direct=True, db_path=tmp_db)
    assert first.rows_persisted == 1

    # Re-run with same row
    second = run_backfill(csv_path, direct=True, db_path=tmp_db)
    assert second.rows_read == 1
    assert second.rows_persisted == 0
    assert second.rows_idempotent_skip == 1

    # Still exactly one event in the DB
    conn = ovs_storage.get_connection(tmp_db)
    try:
        rows = list(conn.execute("SELECT * FROM outcome_events"))
    finally:
        conn.close()
    assert len(rows) == 1


def test_direct_mode_skips_invalid_rows(csv_path, tmp_db):
    bad_empty = _make_row("BK-IGNORED")
    bad_empty["booking_id"] = ""   # empty booking_id, set directly to dodge kwarg collision
    _write_csv(csv_path, [
        _make_row("BK-GOOD"),
        _make_row("BK-BAD", gross_usd="not-a-number"),
        bad_empty,
    ])
    report = run_backfill(csv_path, direct=True, db_path=tmp_db)
    assert report.rows_read == 3
    assert report.rows_invalid == 2
    assert report.rows_persisted == 1


# ── pubsub mode (no creds available) ───────────────────────────────────────


def test_pubsub_mode_reports_unavailable_when_env_unset(csv_path, tmp_db, monkeypatch):
    """Without GCP_PROJECT, pubsub mode safely no-ops per the adapter contract."""
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("OVS_GCP_PROJECT", raising=False)

    _write_csv(csv_path, [_make_row("BK-1"), _make_row("BK-2")])
    report = run_backfill(csv_path, direct=False, dry_run=False, db_path=tmp_db)
    assert report.mode == "pubsub"
    assert report.rows_read == 2
    assert report.rows_pubsub_unavailable == 2
    assert report.rows_published == 0
    # No rows persisted in the DB (we didn't go through direct ingestion)
    conn = ovs_storage.get_connection(tmp_db)
    try:
        rows = list(conn.execute("SELECT * FROM outcome_events"))
    finally:
        conn.close()
    assert rows == []


# ── Misc ───────────────────────────────────────────────────────────────────


def test_run_backfill_raises_on_missing_csv(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_backfill(tmp_path / "missing.csv", direct=True, dry_run=False)


def test_report_to_dict_is_json_safe(csv_path, tmp_db):
    """The report shape must be JSON-serializable for CLI consumers."""
    import json
    _write_csv(csv_path, [_make_row("BK-1")])
    report = run_backfill(csv_path, direct=True, db_path=tmp_db)
    body = json.dumps(report.to_dict())
    assert "BK-1" in body
    assert "persisted" in body
