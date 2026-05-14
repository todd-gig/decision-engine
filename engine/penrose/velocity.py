"""velocity — Decision Velocity instrumentation (Penrose Scoreboard signal 3).

WHAT: Records `decision_id, decision_class, started_at, completed_at`
timestamps and computes median seconds-per-decision within a window.

WHY: Per penrose_falsification_doctrine.md §Scoreboard item 3, Decision
Velocity ↓ is direct evidence that decision logic is maturing — a repeated
class should get faster over time. Without per-decision timing, the
"system gets faster with use" claim is anecdotal.

WHERE: SQLite table `decision_timings` in `drift_sentinel/penrose_scoreboard.db`.
Single file shared with the network-value inbox so the entire Penrose
scoreboard is local-first auditable in one place.

WHEN: `record_decision_timing(...)` is called by `engine.pipeline` once the
hooks land. Until callers wire in, the schema exists + median returns the
empty-set graceful response (`null` median + sample_count=0).

HOW: ALTER TABLE on first write if pre-existing schema lacks columns;
median computed in Python over rows in the window.

CONTEXT: v0.6 acceptable behavior — recording is opt-in; querying never
fails. Calls outside the window or with `completed_at IS NULL` skipped.

penrose_signal: weakens
penrose_dimension: velocity
"""
from __future__ import annotations

import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

DEFAULT_DB_FILENAME = "penrose_scoreboard.db"
TIMINGS_TABLE = "decision_timings"


def _default_db_path() -> Path:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    candidate = repo_root / "drift_sentinel" / DEFAULT_DB_FILENAME
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open + ensure schema. Shared DB for all penrose sub-package storage."""
    path = Path(db_path) if db_path else _default_db_path()
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {TIMINGS_TABLE} (
            decision_id     TEXT PRIMARY KEY,
            decision_class  TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            completed_at    TEXT,
            duration_ms     INTEGER,
            created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_decision_timings_class
            ON {TIMINGS_TABLE}(decision_class, started_at);
        """
    )
    # v0.6 graceful migration: pre-existing tables may lack columns.
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({TIMINGS_TABLE})")}
    if "duration_ms" not in cols:
        conn.execute(f"ALTER TABLE {TIMINGS_TABLE} ADD COLUMN duration_ms INTEGER")
    if "completed_at" not in cols:
        conn.execute(f"ALTER TABLE {TIMINGS_TABLE} ADD COLUMN completed_at TEXT")


def _parse_iso(ts: str) -> datetime:
    """Parse ISO-8601, treating naive as UTC."""
    s = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def record_decision_timing(
    decision_id: str,
    decision_class: str,
    started_at: str,
    completed_at: Optional[str] = None,
    *,
    db_path: str | Path | None = None,
) -> dict:
    """Upsert one decision timing row. Idempotent on decision_id.

    Per WWWWH: WHY = signal substrate for velocity metric; HOW = computes
    duration_ms when both timestamps present.
    """
    duration_ms: Optional[int] = None
    if completed_at:
        delta = _parse_iso(completed_at) - _parse_iso(started_at)
        duration_ms = max(0, int(delta.total_seconds() * 1000))

    conn = get_connection(db_path)
    try:
        conn.execute(
            f"""
            INSERT INTO {TIMINGS_TABLE}
                (decision_id, decision_class, started_at, completed_at, duration_ms)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                decision_class = excluded.decision_class,
                started_at     = excluded.started_at,
                completed_at   = COALESCE(excluded.completed_at, {TIMINGS_TABLE}.completed_at),
                duration_ms    = COALESCE(excluded.duration_ms, {TIMINGS_TABLE}.duration_ms)
            """,
            (decision_id, decision_class, started_at, completed_at, duration_ms),
        )
        return {
            "decision_id": decision_id,
            "decision_class": decision_class,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
        }
    finally:
        conn.close()


def compute_decision_velocity(
    window_days: int = 30,
    *,
    db_path: str | Path | None = None,
) -> dict:
    """Median seconds-per-decision, grouped by decision_class, within window.

    Returns:
        {
          "window_days": int,
          "computed_at": ISO-8601 UTC,
          "by_class": {class: {"median_seconds": float|None,
                               "p25_seconds": float|None,
                               "p75_seconds": float|None,
                               "sample_count": int}},
          "overall_median_seconds": float|None,
          "overall_sample_count": int,
        }

    Empty-set graceful: returns null medians + 0 counts when no completed
    timings exist in the window — never raises, never fakes a number.
    """
    if window_days < 1:
        window_days = 1
    now = datetime.now(tz=timezone.utc)
    window_start = (now - timedelta(days=window_days)).isoformat()

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT decision_class, duration_ms FROM {TIMINGS_TABLE}
            WHERE started_at >= ?
              AND completed_at IS NOT NULL
              AND duration_ms IS NOT NULL
            """,
            (window_start,),
        ).fetchall()
    finally:
        conn.close()

    by_class: dict[str, list[int]] = {}
    for cls, dur_ms in rows:
        by_class.setdefault(cls, []).append(int(dur_ms))

    classes_out: dict[str, dict] = {}
    overall: list[int] = []
    for cls, durations in by_class.items():
        durations.sort()
        overall.extend(durations)
        n = len(durations)
        classes_out[cls] = {
            "median_seconds": round(statistics.median(durations) / 1000.0, 3)
                              if n else None,
            "p25_seconds": round(_percentile(durations, 25) / 1000.0, 3)
                           if n else None,
            "p75_seconds": round(_percentile(durations, 75) / 1000.0, 3)
                           if n else None,
            "sample_count": n,
        }

    overall_median = (
        round(statistics.median(overall) / 1000.0, 3) if overall else None
    )

    return {
        "window_days": window_days,
        "computed_at": now.isoformat(),
        "by_class": classes_out,
        "overall_median_seconds": overall_median,
        "overall_sample_count": len(overall),
    }


def _percentile(sorted_values: list[int], pct: float) -> float:
    """Linear-interpolation percentile over a SORTED list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)
