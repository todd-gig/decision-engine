"""human_touch_counter — count unique human decision-touches in a window.

WHAT: A decision is "human-touched" when EITHER a `human_override` row
exists referencing its decision_id/cert id, OR a `codification_certificate`
exists carrying a human signer on a candidate that produced the decision.

WHY: Per penrose_falsification_doctrine.md §Scoreboard item 7, Revenue-
per-Human-Touch operationalizes "decreasing human intervention with
increasing value". Without a precise touch counter, the denominator is
fictional and the ratio is meaningless. This module owns the denominator;
revenue (numerator) is operator-set via env var.

WHERE: Reads `drift_sentinel/human_overrides.db` (overrides table) and
`drift_sentinel/codification_proposals.db` (codification_certificates).

WHEN: Called by `ScoreboardSnapshot.revenue_per_human_touch(window_days=90)`.

HOW: Window filter on `overridden_at` and `signed_at`; deduplicate by
decision_id and decision_certificate_id; signers JSON is parsed and
non-empty signer counts as a touch (codification approval IS a touch).

CONTEXT: This is a real counter, not a stub. The revenue side is the
stub seam — env var or null + formula.

penrose_signal: weakens
penrose_dimension: revenue_per_touch
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


@dataclass
class HumanTouchSummary:
    """Per-source breakdown of human touches in the window.

    Per WWWWH: WHY = downstream needs to know whether touches concentrate
    in overrides or codification approvals (different remediation paths).
    """
    window_days: int
    override_touches: int = 0
    codification_signer_touches: int = 0
    unique_decision_ids_touched: int = 0
    total_touches: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    computed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "window_days": self.window_days,
            "override_touches": self.override_touches,
            "codification_signer_touches": self.codification_signer_touches,
            "unique_decision_ids_touched": self.unique_decision_ids_touched,
            "total_touches": self.total_touches,
            "by_source": dict(self.by_source),
            "computed_at": self.computed_at,
        }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _window_start(window_days: int) -> str:
    return (
        datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    ).isoformat()


def _safe_query(
    db_path: Path, sql: str, params: tuple = ()
) -> list[sqlite3.Row]:
    """Open read-only-ish; return [] if DB missing. Never raises on missing."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        try:
            return list(conn.execute(sql, params))
        except sqlite3.OperationalError:
            # Schema missing (e.g. fresh repo) — treat as zero touches
            return []
    finally:
        conn.close()


def count_human_touches(
    window_days: int = 90,
    *,
    overrides_db_path: Optional[str | Path] = None,
    codification_db_path: Optional[str | Path] = None,
) -> HumanTouchSummary:
    """Count unique human decision-touches in the past `window_days`.

    A touch is one of:
      - a row in `human_overrides` with `overridden_at >= window_start`
      - a row in `codification_certificates` with `signed_at >= window_start`
        AND `signers` JSON non-empty

    Dedup: decision_id (when set) and decision_certificate_id (when set)
    are tracked in a single set across both sources.
    """
    if window_days < 1:
        window_days = 1
    start = _window_start(window_days)

    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    ov_path = Path(overrides_db_path) if overrides_db_path else (
        repo_root / "drift_sentinel" / "human_overrides.db"
    )
    cod_path = Path(codification_db_path) if codification_db_path else (
        repo_root / "drift_sentinel" / "codification_proposals.db"
    )

    # ── Override-side touches ───────────────────────────────────────────
    override_rows = _safe_query(
        ov_path,
        """
        SELECT decision_id, decision_certificate_id, overridden_by_user_id
        FROM human_overrides
        WHERE overridden_at >= ?
        """,
        (start,),
    )
    override_touches = len(override_rows)

    unique_decisions: set[str] = set()
    for row in override_rows:
        did = row["decision_id"] or row["decision_certificate_id"]
        if did:
            unique_decisions.add(str(did))

    # ── Codification-side touches ───────────────────────────────────────
    cod_rows = _safe_query(
        cod_path,
        """
        SELECT id, candidate_id, signers, evidence_decision_ids
        FROM codification_certificates
        WHERE signed_at >= ?
        """,
        (start,),
    )
    codification_touches = 0
    for row in cod_rows:
        try:
            signers = json.loads(row["signers"]) if row["signers"] else []
        except (TypeError, ValueError):
            signers = []
        if not signers:
            continue
        codification_touches += 1
        try:
            evidence = (
                json.loads(row["evidence_decision_ids"])
                if row["evidence_decision_ids"] else []
            )
        except (TypeError, ValueError):
            evidence = []
        for eid in evidence:
            if eid:
                unique_decisions.add(str(eid))

    total = override_touches + codification_touches
    return HumanTouchSummary(
        window_days=window_days,
        override_touches=override_touches,
        codification_signer_touches=codification_touches,
        unique_decision_ids_touched=len(unique_decisions),
        total_touches=total,
        by_source={
            "human_overrides": override_touches,
            "codification_certificates": codification_touches,
        },
        computed_at=_now_iso(),
    )
