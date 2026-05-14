"""scoreboard — `ScoreboardSnapshot` aggregating all 8 Penrose signals.

WHAT: Single façade that reads existing engine data stores and returns
a per-metric value with trend direction + penrose_signal label.

WHY: Per penrose_falsification_doctrine.md, "Without explicit framing,
the doctrine drifts into 'AI tooling that helps.'" This file IS the
framing instrument — one endpoint, eight signals, falsifiable.

WHERE: Reads:
  - drift_sentinel/codification_proposals.db      (codification_certificates)
  - drift_sentinel/human_overrides.db             (human_overrides)
  - drift_sentinel/ovs_calibration.db             (calibration_revisions, attribution_links)
  - drift_sentinel/penrose_scoreboard.db          (decision_timings, network_value_observations)
  - drift_sentinel/drift_history.db               (latest scan)

WHEN: Read on every HTTP hit; v0.6 has no cache — small data + SQLite.

HOW: Lazy imports for heavy deps. Stubs return explicit
`{"status": "...", "value": None, "formula": "...", "next_milestone": "..."}`
so no caller mistakes a stub for a real metric.

CONTEXT: 5 of 8 are real (codification, override, ovs_variance, cascade,
drift_critical). Decision Velocity returns empty-set graceful (no
recordings yet but schema live). Network Value is hard-stub awaiting PPEME.
Revenue-per-touch returns real touches + revenue null unless env var set.

penrose_signal: weakens
penrose_dimension: codification | override_rate | velocity | variance | cascade |
                   network_value | revenue_per_touch | drift_count
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


PENROSE_SCOREBOARD_VERSION = "v0.6"

METRIC_NAMES: tuple[str, ...] = (
    "codification_rate",
    "human_override_rate",
    "decision_velocity",
    "ovs_variance",
    "cascade_multiplier",
    "super_additive_network_value",
    "revenue_per_human_touch",
    "drift_critical_count",
)

# Target trend per signal per the doctrine § Scoreboard table.
_TARGET_TREND: dict[str, str] = {
    "codification_rate": "up",
    "human_override_rate": "down",
    "decision_velocity": "down",
    "ovs_variance": "down",
    "cascade_multiplier": "neutral",   # target → 2.2× (neither pure up nor down)
    "super_additive_network_value": "up",
    "revenue_per_human_touch": "up",
    "drift_critical_count": "down",    # target = 0 sustained
}

# Penrose-falsification semantics: "weakens" = evidence against Penrose's
# practical claim; "strengthens" = evidence for it. Per the doctrine, every
# scoreboard MOVE is one or the other (or neutral if within tolerance).
_SIGNAL_LABEL_FORMULAS: dict[str, str] = {
    "codification_rate": "patterns_promoted ÷ window_days × 90",
    "human_override_rate": "overrides ÷ decisions, per decision_class",
    "decision_velocity": "median(completed_at − started_at), per decision_class",
    "ovs_variance": "mean(|variance|) across CalibrationRevisions",
    "cascade_multiplier": "mean(cascade_multiplier) on AttributionLinks where layer_number > 1",
    "super_additive_network_value": "Δ_BFT_state_per_participant",
    "revenue_per_human_touch": "revenue_usd ÷ unique_human_decision_touches",
    "drift_critical_count": "count(violations.severity = 'critical') @ latest_scan",
}

# Env-var seam — operators set revenue side; we never synthesize.
REVENUE_USD_OVERRIDE_ENV = "PENROSE_REVENUE_USD_OVERRIDE"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _window_start_iso(window_days: int) -> str:
    return (
        datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    ).isoformat()


def _safe_open_readonly(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _stub_payload(
    *,
    status: str,
    formula: str,
    next_milestone: str,
    extras: Optional[dict] = None,
) -> dict:
    """Canonical stub shape — `value: null` so dashboards can detect."""
    body = {
        "status": status,
        "value": None,
        "formula": formula,
        "next_milestone": next_milestone,
    }
    if extras:
        body.update(extras)
    return body


# ─────────────────────────────────────────────────────────────────────────
# ScoreboardSnapshot
# ─────────────────────────────────────────────────────────────────────────


class ScoreboardSnapshot:
    """Aggregator for the 8-metric Penrose Falsification Scoreboard.

    Per WWWWH: WHY = single read for the Founder UI + Sunday weekly report.
    Construction is cheap; reads happen lazily per metric call.
    """

    def __init__(
        self,
        *,
        codification_db_path: Optional[str | Path] = None,
        overrides_db_path: Optional[str | Path] = None,
        ovs_db_path: Optional[str | Path] = None,
        penrose_db_path: Optional[str | Path] = None,
        drift_db_path: Optional[str | Path] = None,
    ) -> None:
        rr = _repo_root()
        self.codification_db_path = Path(codification_db_path) if codification_db_path else (
            rr / "drift_sentinel" / "codification_proposals.db"
        )
        self.overrides_db_path = Path(overrides_db_path) if overrides_db_path else (
            rr / "drift_sentinel" / "human_overrides.db"
        )
        self.ovs_db_path = Path(ovs_db_path) if ovs_db_path else (
            rr / "drift_sentinel" / "ovs_calibration.db"
        )
        self.penrose_db_path = Path(penrose_db_path) if penrose_db_path else (
            rr / "drift_sentinel" / "penrose_scoreboard.db"
        )
        self.drift_db_path = Path(drift_db_path) if drift_db_path else (
            rr / "drift_sentinel" / "drift_history.db"
        )

    # ── 1. Codification Rate ↑ ──────────────────────────────────────────
    def codification_rate(self, window_days: int = 90) -> dict:
        """Count of CodificationCertificates in window, normalized to 90 days.

        Target ↑ — every promoted pattern is one less ambiguous Claude call.
        """
        window_days = max(1, int(window_days))
        start = _window_start_iso(window_days)
        conn = _safe_open_readonly(self.codification_db_path)
        count = 0
        if conn is not None:
            try:
                try:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) FROM codification_certificates
                        WHERE signed_at >= ?
                        """,
                        (start,),
                    ).fetchone()
                    count = int(row[0]) if row else 0
                except sqlite3.OperationalError:
                    count = 0
            finally:
                conn.close()
        # Normalize to a 90-day window so quarterly trend is comparable.
        normalized = round(count / window_days * 90.0, 3)
        return {
            "metric": "codification_rate",
            "window_days": window_days,
            "patterns_promoted": count,
            "value": normalized,
            "normalized_window_days": 90,
            "unit": "patterns_per_90_days",
            "trend_target": _TARGET_TREND["codification_rate"],
            "formula": _SIGNAL_LABEL_FORMULAS["codification_rate"],
            "penrose_signal": "weakens" if count > 0 else "neutral",
            "computed_at": _now_iso(),
        }

    # ── 2. Human Override Rate ↓ ────────────────────────────────────────
    def human_override_rate(self, window_days: int = 30) -> dict:
        """Overrides ÷ decisions, per decision_class. Trend ↓ matures logic.

        v0.6 denominator-aware behavior: when codification proposals + overrides
        share a window, we approximate "decisions" by the override count itself
        per class IF no separate decision count is recorded. We always report
        the absolute count per class so dashboards can compute their own ratio
        against an authoritative denominator when available.
        """
        window_days = max(1, int(window_days))
        start = _window_start_iso(window_days)
        by_class: dict[str, dict] = {}
        total_overrides = 0
        conn = _safe_open_readonly(self.overrides_db_path)
        if conn is not None:
            try:
                try:
                    rows = conn.execute(
                        """
                        SELECT classification, overridden_at FROM human_overrides
                        WHERE overridden_at >= ?
                        """,
                        (start,),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                for r in rows:
                    cls = _extract_decision_class(r["classification"])
                    bucket = by_class.setdefault(
                        cls,
                        {"override_count": 0, "decision_class": cls},
                    )
                    bucket["override_count"] += 1
                    total_overrides += 1
            finally:
                conn.close()

        # Compute per-class rate; denominator = override_count when no
        # external decision count is recorded (rate = 1.0 in that case, which
        # is a legitimate "all observed decisions in this class were overridden"
        # signal — dashboards should pair with decision-volume telemetry).
        for cls, bucket in by_class.items():
            bucket["override_rate"] = 1.0 if bucket["override_count"] else 0.0

        return {
            "metric": "human_override_rate",
            "window_days": window_days,
            "by_class": by_class,
            "total_overrides": total_overrides,
            "trend_target": _TARGET_TREND["human_override_rate"],
            "formula": _SIGNAL_LABEL_FORMULAS["human_override_rate"],
            "penrose_signal": "strengthens" if total_overrides > 0 else "neutral",
            "computed_at": _now_iso(),
            "note": (
                "Denominator = decision-count is not yet recorded per class; "
                "dashboards should pair override_count with decision volume "
                "from learning_loop / pipeline telemetry"
            ),
        }

    # ── 3. Decision Velocity ↓ ──────────────────────────────────────────
    def decision_velocity(self, window_days: int = 30) -> dict:
        """Median seconds per decision_class, from `engine.penrose.velocity`.

        v0.6: returns the empty-set graceful response (null medians, 0
        sample) until callers wire `record_decision_timing(...)` into the
        pipeline. Schema is live — see velocity.py.
        """
        # Lazy import keeps the snapshot lightweight if velocity isn't queried.
        from . import velocity
        body = velocity.compute_decision_velocity(
            window_days=window_days, db_path=self.penrose_db_path
        )
        body["metric"] = "decision_velocity"
        body["trend_target"] = _TARGET_TREND["decision_velocity"]
        body["formula"] = _SIGNAL_LABEL_FORMULAS["decision_velocity"]
        # Penrose-signal: maturing logic ↔ median ↓ over time. With a single
        # snapshot we can't infer direction; we mark neutral and let trend
        # analysis on top of repeated snapshots fill in.
        body["penrose_signal"] = "neutral"
        return body

    # ── 4. OVS Variance ↓ ───────────────────────────────────────────────
    def ovs_variance(self, window_days: int = 30) -> dict:
        """Mean |variance_pct|-equivalent across CalibrationRevisions.

        Uses (after_value − before_value) / max(|before_value|, 1e-9) as
        the variance magnitude — same shape OVS-Calibration emits.
        """
        window_days = max(1, int(window_days))
        start = _window_start_iso(window_days)
        deltas: list[float] = []
        conn = _safe_open_readonly(self.ovs_db_path)
        if conn is not None:
            try:
                try:
                    rows = conn.execute(
                        """
                        SELECT before_value, after_value FROM calibration_revisions
                        WHERE signed_at >= ?
                        """,
                        (start,),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                for r in rows:
                    bv = float(r["before_value"])
                    av = float(r["after_value"])
                    denom = max(abs(bv), 1e-9)
                    deltas.append(abs(av - bv) / denom)
            finally:
                conn.close()

        mean_variance = round(statistics.fmean(deltas), 6) if deltas else None
        return {
            "metric": "ovs_variance",
            "window_days": window_days,
            "value": mean_variance,
            "sample_count": len(deltas),
            "unit": "fractional_magnitude",
            "trend_target": _TARGET_TREND["ovs_variance"],
            "formula": _SIGNAL_LABEL_FORMULAS["ovs_variance"],
            "penrose_signal": "weakens" if mean_variance is not None else "neutral",
            "computed_at": _now_iso(),
        }

    # ── 5. Cascade Multiplier → 2.2× ────────────────────────────────────
    def cascade_multiplier(self) -> dict:
        """Mean observed multiplier across AttributionLinks with layer > 1.

        Per Framework 5.12, three-system attribution targets ~2.2×.
        """
        multipliers: list[float] = []
        conn = _safe_open_readonly(self.ovs_db_path)
        if conn is not None:
            try:
                try:
                    rows = conn.execute(
                        """
                        SELECT cascade_multiplier FROM attribution_links
                        WHERE layer_number > 1
                        """,
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                multipliers = [float(r[0]) for r in rows if r[0] is not None]
            finally:
                conn.close()

        mean_mult = round(statistics.fmean(multipliers), 6) if multipliers else None
        target = 2.2
        signal = "neutral"
        if mean_mult is not None:
            # If observed multiplier is within ±15% of target, this is
            # evidence FOR the cascade claim (weakens Penrose). Otherwise
            # neutral (we don't punish low samples).
            if abs(mean_mult - target) / target <= 0.15:
                signal = "weakens"
        return {
            "metric": "cascade_multiplier",
            "value": mean_mult,
            "target": target,
            "sample_count": len(multipliers),
            "trend_target": _TARGET_TREND["cascade_multiplier"],
            "formula": _SIGNAL_LABEL_FORMULAS["cascade_multiplier"],
            "penrose_signal": signal,
            "computed_at": _now_iso(),
        }

    # ── 6. Super-Additive Network Value ↑ (STUB) ────────────────────────
    def super_additive_network_value(self) -> dict:
        """STUB — awaiting PPEME BFT state emission.

        Per memory penrose_falsification_doctrine.md §Strengthening Signals,
        single-tenant baseline is the current state. Computing this
        requires per-participant BFT state observations across time;
        PPEME owns BFT state today and has not wired emission here.

        Returns explicit null + formula + next_milestone so dashboards can
        show "not yet wired" without numeric deception.
        """
        from .network_value_emitter import count_observations
        obs_count = count_observations(db_path=self.penrose_db_path)
        return _stub_payload(
            status="awaiting_ppeme_wiring",
            formula=_SIGNAL_LABEL_FORMULAS["super_additive_network_value"],
            next_milestone="PPEME BFT state emission (penrose-v0.7)",
            extras={
                "metric": "super_additive_network_value",
                "observations_received": obs_count,
                "trend_target": _TARGET_TREND["super_additive_network_value"],
                "penrose_signal": "neutral",
                "computed_at": _now_iso(),
            },
        )

    # ── 7. Revenue per Human-Touch ↑ ────────────────────────────────────
    def revenue_per_human_touch(self, window_days: int = 90) -> dict:
        """Quarterly revenue ÷ unique human decision-touches.

        Real on the denominator (touch count from
        `human_touch_counter.count_human_touches`); revenue side reads env
        var `PENROSE_REVENUE_USD_OVERRIDE` — operator-set; never synthesized.
        """
        from .human_touch_counter import count_human_touches
        summary = count_human_touches(
            window_days=window_days,
            overrides_db_path=self.overrides_db_path,
            codification_db_path=self.codification_db_path,
        )
        revenue_raw = os.environ.get(REVENUE_USD_OVERRIDE_ENV)
        revenue_usd: Optional[float] = None
        if revenue_raw is not None and revenue_raw.strip():
            try:
                revenue_usd = float(revenue_raw)
            except ValueError:
                revenue_usd = None

        value: Optional[float] = None
        if revenue_usd is not None and summary.total_touches > 0:
            value = round(revenue_usd / summary.total_touches, 4)

        signal = "neutral"
        if revenue_usd is None:
            signal = "neutral"   # half-instrumented; abstain
        elif summary.total_touches == 0 and revenue_usd > 0:
            # Revenue with zero recorded human touches = Penrose-weakening
            signal = "weakens"

        return {
            "metric": "revenue_per_human_touch",
            "window_days": window_days,
            "value": value,
            "revenue_usd": revenue_usd,
            "revenue_source": (
                f"env:{REVENUE_USD_OVERRIDE_ENV}" if revenue_usd is not None
                else None
            ),
            "human_touches": summary.to_dict(),
            "unit": "usd_per_touch",
            "trend_target": _TARGET_TREND["revenue_per_human_touch"],
            "formula": _SIGNAL_LABEL_FORMULAS["revenue_per_human_touch"],
            "penrose_signal": signal,
            "computed_at": _now_iso(),
            "next_milestone": (
                None if revenue_usd is not None else
                "Wire revenue ingest from sales-os + carmen-beach revenue tables"
            ),
        }

    # ── 8. Drift Critical Count = 0 sustained ───────────────────────────
    def drift_critical_count(self) -> dict:
        """Reads the latest scan from `drift_history.db`, returns critical count."""
        conn = _safe_open_readonly(self.drift_db_path)
        if conn is None:
            return {
                "metric": "drift_critical_count",
                "value": None,
                "trend_target": _TARGET_TREND["drift_critical_count"],
                "formula": _SIGNAL_LABEL_FORMULAS["drift_critical_count"],
                "penrose_signal": "neutral",
                "status": "drift_history_unavailable",
                "computed_at": _now_iso(),
            }
        try:
            try:
                row = conn.execute(
                    """
                    SELECT scan_id, timestamp, critical, major, minor, info,
                           total_artifacts
                    FROM scans ORDER BY timestamp DESC LIMIT 1
                    """
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
        finally:
            conn.close()

        if row is None:
            return {
                "metric": "drift_critical_count",
                "value": None,
                "trend_target": _TARGET_TREND["drift_critical_count"],
                "formula": _SIGNAL_LABEL_FORMULAS["drift_critical_count"],
                "penrose_signal": "neutral",
                "status": "no_scans_recorded",
                "computed_at": _now_iso(),
            }
        critical = int(row["critical"])
        return {
            "metric": "drift_critical_count",
            "value": critical,
            "scan_id": row["scan_id"],
            "scan_timestamp": row["timestamp"],
            "major": int(row["major"]),
            "minor": int(row["minor"]),
            "info": int(row["info"]),
            "total_artifacts": int(row["total_artifacts"]),
            "trend_target": _TARGET_TREND["drift_critical_count"],
            "formula": _SIGNAL_LABEL_FORMULAS["drift_critical_count"],
            "penrose_signal": "weakens" if critical == 0 else "strengthens",
            "computed_at": _now_iso(),
        }

    # ── snapshot() — aggregate all 8 ────────────────────────────────────
    def snapshot(self) -> dict:
        """Aggregate read of every metric with metadata.

        Per WWWWH: WHAT = full 8-of-8 read; WHY = the Founder UI + Sunday
        report need a single payload to render the scoreboard; HOW = each
        metric called once + errors per-metric captured (never blocks).
        """
        metrics: dict[str, Any] = {}
        signals_summary = {"weakens": 0, "strengthens": 0, "neutral": 0,
                           "stub": 0, "error": 0}

        method_map = {
            "codification_rate":            lambda: self.codification_rate(),
            "human_override_rate":          lambda: self.human_override_rate(),
            "decision_velocity":            lambda: self.decision_velocity(),
            "ovs_variance":                 lambda: self.ovs_variance(),
            "cascade_multiplier":           lambda: self.cascade_multiplier(),
            "super_additive_network_value": lambda: self.super_additive_network_value(),
            "revenue_per_human_touch":      lambda: self.revenue_per_human_touch(),
            "drift_critical_count":         lambda: self.drift_critical_count(),
        }
        for name in METRIC_NAMES:
            try:
                body = method_map[name]()
                metrics[name] = body
                if body.get("status") == "awaiting_ppeme_wiring":
                    signals_summary["stub"] += 1
                else:
                    sig = body.get("penrose_signal", "neutral")
                    signals_summary[sig] = signals_summary.get(sig, 0) + 1
            except Exception as exc:   # noqa: BLE001 — defensive aggregate
                metrics[name] = {
                    "metric": name,
                    "value": None,
                    "penrose_signal": "neutral",
                    "error": f"{type(exc).__name__}: {exc}",
                    "computed_at": _now_iso(),
                }
                signals_summary["error"] += 1

        return {
            "scoreboard_version": PENROSE_SCOREBOARD_VERSION,
            "computed_at": _now_iso(),
            "metric_names": list(METRIC_NAMES),
            "metrics": metrics,
            "signals_summary": signals_summary,
            "doctrine_ref": (
                "memory/penrose_falsification_doctrine.md §Scoreboard"
            ),
        }


# ─────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────


def _extract_decision_class(classification_json: Optional[str]) -> str:
    """human_overrides.classification holds JSON-serialized OverrideClassification.

    For override-rate-per-class we group by the override_type rather than a
    formal `decision_class` since the override record is not class-typed
    today; this keeps the metric working until a proper class field lands.
    """
    if not classification_json:
        return "unknown"
    try:
        body = json.loads(classification_json)
    except (TypeError, ValueError):
        return "unknown"
    return str(body.get("type") or body.get("decision_class") or "unknown")
