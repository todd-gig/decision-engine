"""Drift-history write-through — surface override drift to Gate 8.

v0.6 deliverable: graduate drift signals from the in-memory list returned
by `drift_signal.detect_drift_signals()` to direct writes into
`drift_sentinel/drift_history.db`. Gate 8 (`engine.gates.gate_8_drift_check`)
reads that DB and BLOCKS decisions when unresolved critical drift touches
the decision's domain — without this write-through, override-rate decay
never reaches that gate.

Schema target (from `drift_sentinel/drift_scan.py:init_history`):

  scans(scan_id, timestamp, sources, total_artifacts,
        critical, major, minor, info)
  violations(id AUTOINCREMENT, scan_id, rule_id, severity,
             artifact, location, excerpt)

Rule:
  rule_id = "OVERRIDE-DRIFT" (override-engine-emitted family)
  severity = "major" (Drift Sentinel taxonomy — codified-module
    decay is recoverable, not structurally non-negotiable)

Idempotency:
  Don't write the same (rule_id, artifact, location) twice within
  a 24h window. Gate 8 takes the *latest* scan and reports DISTINCT
  rule_id+artifact pairs, so churning duplicates of the same signal
  would compound the blast radius without adding information.

penrose_signal: weakens
penrose_dimension: override_rate
why: Without write-through, override drift dies in a Python list. With
it, the recursive self-governance loop closes: an engine's growing
override rate → drift_history row → Gate 8 blocks new decisions in that
domain → forces remediation. That's the Penrose-falsifier teeth: an
engine that gets corrected enough is allowed to fail-loud, not silently
keep deciding wrongly.
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # avoid circular import at module load
    from .drift_signal import OverrideDriftSignal


logger = logging.getLogger(__name__)


# Rule + severity per spec — kept in this module so callers don't have
# to know the Drift Sentinel taxonomy.
OVERRIDE_DRIFT_RULE_ID = "OVERRIDE-DRIFT"
OVERRIDE_DRIFT_SEVERITY = "major"
IDEMPOTENCY_WINDOW_HOURS = 24
DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0


def _default_drift_history_db() -> Path:
    """Path to the canonical drift_history.db this engine writes to.

    Mirrors `engine.gates._default_drift_db_path()` so writer + reader
    point at the exact same file when invoked from inside the
    `decision-engine/` repo tree.
    """
    here = Path(__file__).resolve().parent.parent.parent  # decision-engine/
    return here / "drift_sentinel" / "drift_history.db"


def _ensure_history_schema(conn: sqlite3.Connection) -> None:
    """Create scans + violations tables if they don't yet exist.

    Mirrors `drift_sentinel.drift_scan.init_history()`. We can't import
    that module here (heavy dependency surface — the scanner pulls YAML,
    AST utilities, etc.) so we inline the DDL. If the schemas ever diverge,
    drift_sentinel's CI will catch it — but this is the same long-stable
    shape both Gate 8 and the scanner have used since B-02 closed.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            scan_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            sources TEXT NOT NULL,
            total_artifacts INTEGER NOT NULL,
            critical INTEGER NOT NULL,
            major INTEGER NOT NULL,
            minor INTEGER NOT NULL,
            info INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            artifact TEXT NOT NULL,
            location TEXT,
            excerpt TEXT,
            FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
        )
    """)
    conn.commit()


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open `drift_history.db` in WAL mode with a short lock timeout.

    WAL reduces blocking on the readers (Gate 8 queries this DB on the
    pipeline hot path). Short timeout avoids holding the write side of
    the lock indefinitely if the scanner is mid-write.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        timeout=DEFAULT_LOCK_TIMEOUT_SECONDS,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _ensure_history_schema(conn)
    return conn


def _recently_written(
    conn: sqlite3.Connection,
    rule_id: str,
    artifact: str,
    location: Optional[str],
    *,
    window_hours: int = IDEMPOTENCY_WINDOW_HOURS,
) -> bool:
    """Return True iff (rule_id, artifact, location) was written < `window_hours` ago.

    We join violations → scans on scan_id so we can apply the time window
    using the scan's timestamp. (The violations table itself has no
    timestamp column — that's the schema; we anchor to scans.timestamp.)
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=window_hours)
    ).isoformat()
    sql = """
        SELECT 1 FROM violations v
        JOIN scans s ON v.scan_id = s.scan_id
        WHERE v.rule_id = ?
          AND v.artifact = ?
          AND COALESCE(v.location, '') = COALESCE(?, '')
          AND s.timestamp >= ?
        LIMIT 1
    """
    row = conn.execute(sql, (rule_id, artifact, location, cutoff)).fetchone()
    return row is not None


def write_override_drift_signal(
    signal: "OverrideDriftSignal",
    *,
    db_path: Optional[Path | str] = None,
) -> Optional[str]:
    """Write `signal` to `drift_history.db` so Gate 8 picks it up.

    Returns the scan_id used (existing or new) when the row is written.
    Returns None when the idempotency check suppressed the write.

    Behavior:
      1. Resolve drift_history.db (explicit > default).
      2. Open WAL + short timeout. Ensure schema.
      3. Idempotency check on (rule_id=OVERRIDE-DRIFT, artifact, location).
         The location is `f"{decision_class}@{override_rate_14d}"` so
         signals about the SAME class at the SAME rate compress; a fresh
         rate change creates a new row.
      4. Insert a synthetic `scans` row (sources='override_engine') AND
         a `violations` row pointing at it.

    Why a synthetic scan: Gate 8 selects the most-recent scan in the
    lookback window and reads violations from THAT scan only. If we
    inserted only a violation row, it would attach to the most-recent
    drift_sentinel scan and only show up if that scan is fresh. A
    dedicated synthetic scan per write keeps override drift visible
    regardless of how recently drift_sentinel last ran.
    """
    target = Path(db_path) if db_path else _default_drift_history_db()
    artifact = signal.artifact or signal.decision_class or "<unknown>"
    location = f"{signal.decision_class}@{signal.override_rate_14d:.4f}"
    excerpt = signal.notes[:500]  # excerpt field is text; keep bounded

    try:
        conn = _connect(target)
    except sqlite3.Error as exc:
        # Never raise into the override path. Non-Negotiable #1.
        logger.warning(
            "[human_override.drift_writer] connect failed (%s); "
            "skipping write for class=%s",
            exc, signal.decision_class,
        )
        return None

    try:
        if _recently_written(
            conn, OVERRIDE_DRIFT_RULE_ID, artifact, location,
        ):
            logger.debug(
                "[human_override.drift_writer] suppressed duplicate "
                "(<%dh) for %s @ %s",
                IDEMPOTENCY_WINDOW_HOURS, artifact, location,
            )
            return None

        scan_id = f"override-drift-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?,?,?,?)",
            (
                scan_id, now_iso, "override_engine",
                1,  # total_artifacts — one violation worth
                0,  # critical
                1 if OVERRIDE_DRIFT_SEVERITY == "major" else 0,
                0,  # minor
                0,  # info
            ),
        )
        conn.execute(
            "INSERT INTO violations (scan_id, rule_id, severity, "
            "artifact, location, excerpt) VALUES (?,?,?,?,?,?)",
            (
                scan_id, OVERRIDE_DRIFT_RULE_ID, OVERRIDE_DRIFT_SEVERITY,
                artifact, location, excerpt,
            ),
        )
        conn.commit()
        logger.info(
            "[human_override.drift_writer] wrote override drift "
            "scan_id=%s artifact=%s rate=%.4f sample=%d",
            scan_id, artifact, signal.override_rate_14d, signal.sample_size,
        )
        return scan_id
    except sqlite3.Error as exc:
        logger.warning(
            "[human_override.drift_writer] write failed for class=%s: %s",
            signal.decision_class, exc,
        )
        return None
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def flush_recent_patterns_to_drift(
    *,
    db_path_overrides: Optional[str] = None,
    db_path_drift: Optional[Path | str] = None,
    window_days: int = 1,
    decision_counts: Optional[dict[str, int]] = None,
) -> dict:
    """Manually trigger drift writes over the last `window_days` of overrides.

    Used by the `/v1/overrides/drift/flush` admin endpoint and ops scripts.
    `decision_counts` is optional — if absent we estimate by counting
    overrides per class and assuming a baseline 10× decision volume per
    class (conservative; flushes the signal but won't fire on tiny samples
    once real volume data is wired in).
    """
    from . import drift_signal  # local import to avoid cycle

    if decision_counts is None:
        # Conservative fallback: assume 10× the override volume per class
        # so the rate ends up at exactly 10% (the threshold) — surfaces
        # any class that *would* trip given equal real volume.
        from . import storage
        conn = storage.get_connection(db_path_overrides)
        try:
            conn.row_factory = sqlite3.Row
            from datetime import datetime as _dt, timezone as _tz
            from datetime import timedelta as _td
            cutoff = (
                _dt.now(_tz.utc) - _td(days=drift_signal.ROLLING_WINDOW_DAYS)
            ).isoformat()
            rows = conn.execute(
                "SELECT freeform_metadata, decision_certificate_id, "
                "source_engine FROM human_overrides WHERE overridden_at >= ?",
                (cutoff,),
            ).fetchall()
            estimated: dict[str, int] = {}
            for row in rows:
                cls = drift_signal._resolve_decision_class_safe(row)
                estimated[cls] = estimated.get(cls, 0) + 1
            # Assume real decision volume = override count * 10 → rate = 10%
            decision_counts = {k: v * 10 for k, v in estimated.items()}
        finally:
            conn.close()

    signals = drift_signal.detect_drift_signals(
        decision_counts=decision_counts,
        db_path=db_path_overrides,
    )
    written: list[str] = []
    suppressed: int = 0
    for sig in signals:
        scan_id = write_override_drift_signal(sig, db_path=db_path_drift)
        if scan_id is not None:
            written.append(scan_id)
        else:
            suppressed += 1
    return {
        "signals_detected": len(signals),
        "signals_written": len(written),
        "signals_suppressed_by_idempotency": suppressed,
        "scan_ids": written,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
    }
