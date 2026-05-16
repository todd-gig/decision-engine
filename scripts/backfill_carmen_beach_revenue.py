"""backfill_carmen_beach_revenue — one-time CSV-driven revenue backfill.

WHAT: Operator-run script that reads a Google Sheets CSV export of
PDC STVR bookings and publishes one OutcomeEvent per row into
OVS-Calibration. Used once-per-historical-window to seed the system so
the Penrose `revenue_per_human_touch` metric becomes real for past
periods.

WHY: The Pub/Sub ingest pipeline streams future events, but historical
revenue from the STVR Drive sheet (per `google_drive_asset_map.md`)
needs an operator-driven seed. Operator-driven — never autonomous —
enforces Non-Negotiable #6 (no synthesized data). The script reads
exactly what the operator hands it; it never makes up bookings.

WHERE: CSV input (path supplied via --csv). Writes outcome events to
the same SQLite store used by the live adapter
(`<repo>/drift_sentinel/ovs_calibration.db`), via
`engine.ovs_calibration.adapters.ingest_outcome(...)` when --direct is
set, or via the Pub/Sub topic `outcomes.carmen-beach.revenue` otherwise.

WHEN: Backfill mode is a one-time operation per historical CSV. The
script de-duplicates on `booking_id` so re-running with the same input
never double-counts.

HOW:
  1. Read CSV, expecting columns: booking_id, unit_id, check_in,
     check_out, gross_usd, (optional: net_usd, channel).
  2. Validate each row against the PDC revenue schema.
  3. For each valid row:
       --direct: call `ingest_outcome(...)` with source_record_id=booking_id
       (default): publish to Pub/Sub topic (lazy import; no-op if google-cloud-pubsub
                  is unavailable, dry_run-like result returned).
  4. Aggregate stats: rows_read, rows_skipped, rows_persisted, rows_published.

CONTEXT: The STVR sheet referenced in
`~/.claude/projects/-Users-admin/memory/google_drive_asset_map.md` is the
operator's source of truth. We do not auto-pull the sheet here — the
operator exports CSV and runs the script. This keeps the data-trust
chain visible: operator chose to backfill X bookings; here are the
booking_ids in audit.

penrose_signal: weakens
penrose_dimension: revenue_per_human_touch
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from engine.ovs_calibration.adapters import (
    CarmenBeachRevenueAdapter,
    ingest_outcome,
)
from engine.ovs_calibration.adapters.base import AdapterMessage


logger = logging.getLogger(__name__)


# ── Schema ─────────────────────────────────────────────────────────────────


# Required CSV columns (mirrors the schema registered by
# scripts.bootstrap_outcome_sources.CARMEN_BEACH_REVENUE.schema)
REQUIRED_COLUMNS = ("booking_id", "unit_id", "check_in", "check_out", "gross_usd")
OPTIONAL_COLUMNS = ("net_usd", "channel")


class BackfillValidationError(ValueError):
    """Raised when a row fails schema validation. Always references booking_id when known."""


# ── Result models ──────────────────────────────────────────────────────────


@dataclass
class RowResult:
    """One CSV row's outcome.

    status:
      - 'persisted'         — direct ingest wrote a new outcome event
      - 'idempotent_skip'   — adapter returned persisted=False (booking_id already ingested)
      - 'published'         — published to Pub/Sub topic
      - 'pubsub_unavailable' — would publish but pubsub libs/env not configured
      - 'dry_run'           — print-only mode
      - 'invalid'           — schema validation failed; reasoning carries why
    """
    booking_id: str
    status: str
    reasoning: str = ""
    outcome_event_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "booking_id": self.booking_id,
            "status": self.status,
            "reasoning": self.reasoning,
            "outcome_event_id": self.outcome_event_id,
        }


@dataclass
class BackfillReport:
    """Aggregate over all rows; the JSON payload printed by the CLI."""
    csv_path: str
    mode: str                      # 'direct' | 'pubsub' | 'dry-run'
    rows_read: int = 0
    rows_invalid: int = 0
    rows_persisted: int = 0
    rows_idempotent_skip: int = 0
    rows_published: int = 0
    rows_dry_run: int = 0
    rows_pubsub_unavailable: int = 0
    duplicates_in_csv: int = 0
    started_at: str = ""
    completed_at: str = ""
    results: list[RowResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "csv_path": self.csv_path,
            "mode": self.mode,
            "rows_read": self.rows_read,
            "rows_invalid": self.rows_invalid,
            "rows_persisted": self.rows_persisted,
            "rows_idempotent_skip": self.rows_idempotent_skip,
            "rows_published": self.rows_published,
            "rows_dry_run": self.rows_dry_run,
            "rows_pubsub_unavailable": self.rows_pubsub_unavailable,
            "duplicates_in_csv": self.duplicates_in_csv,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "results": [r.to_dict() for r in self.results],
        }


# ── Validation + transform ─────────────────────────────────────────────────


def _validate_row(row: dict) -> dict:
    """Validate one CSV row dict; return a normalized dict or raise.

    WHY: keep validation explicit + colocated so the error reason on the
    RowResult is actionable. We never reach into the adapter's transform
    without first knowing the row has the required keys.
    """
    missing = [c for c in REQUIRED_COLUMNS if not row.get(c)]
    if missing:
        booking_id = row.get("booking_id") or "<missing>"
        raise BackfillValidationError(
            f"booking {booking_id!r}: missing required columns: {missing}"
        )
    booking_id = (row.get("booking_id") or "").strip()
    unit_id = (row.get("unit_id") or "").strip()
    if not booking_id:
        raise BackfillValidationError("booking_id is empty")
    if not unit_id:
        raise BackfillValidationError(
            f"booking {booking_id!r}: unit_id is empty"
        )

    try:
        gross_usd = float(row["gross_usd"])
    except (TypeError, ValueError):
        raise BackfillValidationError(
            f"booking {booking_id!r}: gross_usd must be numeric; got {row.get('gross_usd')!r}"
        )
    if gross_usd < 0:
        raise BackfillValidationError(
            f"booking {booking_id!r}: gross_usd must be >= 0"
        )

    net_usd = row.get("net_usd")
    if net_usd not in (None, "", "null"):
        try:
            net_usd = float(net_usd)
        except (TypeError, ValueError):
            raise BackfillValidationError(
                f"booking {booking_id!r}: net_usd must be numeric or empty; "
                f"got {net_usd!r}"
            )
    else:
        net_usd = None

    return {
        "booking_id": booking_id,
        "unit_id": unit_id,
        "check_in": (row.get("check_in") or "").strip(),
        "check_out": (row.get("check_out") or "").strip(),
        "gross_usd": gross_usd,
        "net_usd": net_usd,
        "channel": (row.get("channel") or "").strip() or None,
    }


def _row_to_adapter_message(normalized: dict) -> AdapterMessage:
    """Build the AdapterMessage the PDC adapter expects.

    WHY use the adapter's transform: keeps a single source of truth for
    how a raw STVR record becomes an outcome event (metric naming,
    extras handling). The adapter's transform is deterministic + side-
    effect-free so it's safe to invoke here.
    """
    raw = {
        "booking_id": normalized["booking_id"],
        "unit_id": normalized["unit_id"],
        "observed_value": normalized["gross_usd"],
        # observed_at = check_out so the revenue lands on the day the
        # booking actually completed (closer to "when revenue is recognized").
        "observed_at": _iso_date_to_iso8601(normalized["check_out"]),
        "unit": "usd",
        "extras": {
            "check_in": normalized["check_in"],
            "check_out": normalized["check_out"],
            "net_usd": normalized["net_usd"],
            "channel": normalized["channel"],
        },
    }
    return CarmenBeachRevenueAdapter().transform(raw)


def _iso_date_to_iso8601(date_str: str) -> str:
    """Promote YYYY-MM-DD to ISO-8601 UTC midnight; pass through other shapes.

    WHY: outcome_events.observed_at is TEXT with no format constraint, but
    callers that filter by window need a parseable timestamp. CSV exports
    typically carry YYYY-MM-DD; we normalize to ISO-8601.
    """
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return date_str  # already ISO-8601 or some other shape; let downstream decide


# ── Publish path (Pub/Sub) ──────────────────────────────────────────────────


def _publish_to_pubsub(payload: dict) -> tuple[bool, str]:
    """Publish one message to outcomes.carmen-beach.revenue.

    Returns (success, reasoning). Lazy-imports google.cloud.pubsub_v1 to
    mirror the adapter's no-op-fallback contract: when libs or env are
    unavailable, we don't fail; we return (False, '...') and the caller
    records a `pubsub_unavailable` result.
    """
    project_id = (
        os.environ.get("GCP_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
        or os.environ.get("OVS_GCP_PROJECT")
    )
    if not project_id:
        return False, "GCP_PROJECT (or GCP_PROJECT_ID, OVS_GCP_PROJECT) unset"

    try:
        from google.cloud import pubsub_v1   # type: ignore[import-untyped]
    except ImportError:
        return False, "google-cloud-pubsub not installed"

    topic = "outcomes.carmen-beach.revenue"
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic)
    try:
        future = publisher.publish(
            topic_path, data=json.dumps(payload).encode("utf-8")
        )
        msg_id = future.result(timeout=10)
    except Exception as exc:  # noqa: BLE001 — operator path, surface error reasoning
        return False, f"publish failed: {exc!r}"
    return True, f"published message_id={msg_id}"


# ── Backfill core ───────────────────────────────────────────────────────────


def _read_csv_rows(csv_path: Path) -> Iterable[dict]:
    """Generator over CSV rows as dicts. Strips BOM if present."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def run_backfill(
    csv_path: str | Path,
    *,
    direct: bool = False,
    dry_run: bool = False,
    db_path: Optional[str] = None,
) -> BackfillReport:
    """Read CSV + process each row according to mode.

    Modes (priority order):
      - dry_run=True   -> mode='dry-run', no side effects
      - direct=True    -> mode='direct',  call ingest_outcome(...)
      - default        -> mode='pubsub',  publish to topic
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    if dry_run:
        mode = "dry-run"
    elif direct:
        mode = "direct"
    else:
        mode = "pubsub"

    report = BackfillReport(
        csv_path=str(csv_path),
        mode=mode,
        started_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    seen_booking_ids: set[str] = set()

    for raw_row in _read_csv_rows(csv_path):
        report.rows_read += 1
        try:
            normalized = _validate_row(raw_row)
        except BackfillValidationError as exc:
            booking_id = raw_row.get("booking_id") or "<missing>"
            report.rows_invalid += 1
            report.results.append(RowResult(
                booking_id=str(booking_id),
                status="invalid",
                reasoning=str(exc),
            ))
            continue

        booking_id = normalized["booking_id"]
        if booking_id in seen_booking_ids:
            # CSV-local dedup: same booking_id appears twice in this file.
            report.duplicates_in_csv += 1
            report.results.append(RowResult(
                booking_id=booking_id,
                status="idempotent_skip",
                reasoning="duplicate booking_id within this CSV",
            ))
            continue
        seen_booking_ids.add(booking_id)

        msg = _row_to_adapter_message(normalized)

        if mode == "dry-run":
            report.rows_dry_run += 1
            report.results.append(RowResult(
                booking_id=booking_id,
                status="dry_run",
                reasoning=(
                    f"would emit metric={msg.metric!r} value={msg.observed_value} "
                    f"observed_at={msg.observed_at!r}"
                ),
            ))
            continue

        if mode == "direct":
            try:
                result = ingest_outcome(
                    "carmen-beach", msg,
                    db_path=db_path,
                    source_id=None,
                )
            except Exception as exc:  # noqa: BLE001 — operator path, capture per-row error
                report.rows_invalid += 1
                report.results.append(RowResult(
                    booking_id=booking_id,
                    status="invalid",
                    reasoning=f"direct ingest failed: {exc!r}",
                ))
                continue
            if result.persisted:
                report.rows_persisted += 1
                status = "persisted"
            else:
                report.rows_idempotent_skip += 1
                status = "idempotent_skip"
            report.results.append(RowResult(
                booking_id=booking_id,
                status=status,
                reasoning=result.reasoning,
                outcome_event_id=result.outcome_event_id,
            ))
            continue

        # mode == "pubsub"
        payload = {
            "booking_id": booking_id,
            "unit_id": normalized["unit_id"],
            "metric": msg.metric,
            "observed_value": msg.observed_value,
            "observed_at": msg.observed_at,
            "unit": "usd",
            "extras": dict(msg.extras),
        }
        ok, reasoning = _publish_to_pubsub(payload)
        if ok:
            report.rows_published += 1
            report.results.append(RowResult(
                booking_id=booking_id,
                status="published",
                reasoning=reasoning,
            ))
        else:
            report.rows_pubsub_unavailable += 1
            report.results.append(RowResult(
                booking_id=booking_id,
                status="pubsub_unavailable",
                reasoning=reasoning,
            ))

    report.completed_at = datetime.now(tz=timezone.utc).isoformat()
    return report


# ── CLI ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_carmen_beach_revenue",
        description=(
            "One-time CSV-driven backfill for PDC STVR revenue into "
            "OVS-Calibration. Operator-driven; never fabricates rows."
        ),
    )
    parser.add_argument(
        "--csv", required=True,
        help="Path to STVR CSV export "
             "(columns: booking_id, unit_id, check_in, check_out, gross_usd[, net_usd, channel])",
    )
    parser.add_argument(
        "--direct", action="store_true",
        help="Write directly to OVS-Calibration via ingest_outcome (skips Pub/Sub)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print intent only; never writes + never publishes",
    )
    parser.add_argument(
        "--db-path", default=None,
        help="Override path to ovs_calibration.db (default repo location); "
             "only meaningful with --direct",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.direct:
        # Dry-run wins; document why.
        logger.warning(
            "--dry-run + --direct both set; --dry-run takes precedence "
            "(no side effects)"
        )
    report = run_backfill(
        args.csv,
        direct=args.direct,
        dry_run=args.dry_run,
        db_path=args.db_path,
    )
    print(json.dumps(report.to_dict(), indent=2, default=str))
    return 0 if report.rows_invalid == 0 else 1


if __name__ == "__main__":  # pragma: no cover — exercised via cli.py + tests
    sys.exit(main())
