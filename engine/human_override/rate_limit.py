"""Per-overrider rate-limit alerting.

Per spec decision #7: "Per-overrider rate-limiting — >10 overrides per
hour by same person triggers Admin alert. Why: very high override rate
signals broken engine OR operator confused; either deserves human
attention; rate limit catches both."

Crucial constraint (Non-Negotiable #1): we LOG an alert, we never block
the override. Suppressing an override violates Human-Agency-First.

penrose_signal: weakens
penrose_dimension: override_rate
why: A single operator overriding at >10/hour is a signal the codified
logic has degraded OR the operator's mental model has diverged. Either
way, the platform needs to *see* this, not buffer it. The alert is the
trigger for human-attention routing.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import storage


logger = logging.getLogger(__name__)


# Threshold from spec decision #7. Spec says ">10 per hour" — we interpret
# as "11+ in a rolling 60-minute window".
RATE_LIMIT_PER_HOUR = 10


def _count_recent_overrides(
    user_id: str,
    window: timedelta,
    db_path: Optional[str] = None,
) -> int:
    """Return # of overrides by `user_id` in the last `window`."""
    cutoff = (datetime.now(timezone.utc) - window).isoformat()
    conn = storage.get_connection(db_path)
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM human_overrides
            WHERE overridden_by_user_id = ? AND overridden_at >= ?
            """,
            (user_id, cutoff),
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def check_rate(
    overrider_user_id: str,
    db_path: Optional[str] = None,
    *,
    threshold_per_hour: int = RATE_LIMIT_PER_HOUR,
    window_minutes: int = 60,
) -> Optional[dict]:
    """Check if `overrider_user_id` has breached the per-hour threshold.

    Returns:
      - None if below threshold
      - dict with alert payload (and logs WARNING) if at/above threshold

    Never blocks. Never raises. Per Non-Negotiable #1.
    """
    window = timedelta(minutes=window_minutes)
    count = _count_recent_overrides(overrider_user_id, window, db_path=db_path)
    if count <= threshold_per_hour:
        return None
    alert = {
        "severity": "WARNING",
        "alert": "human_override_rate_limit_exceeded",
        "overrider_user_id": overrider_user_id,
        "count_in_window": count,
        "window_minutes": window_minutes,
        "threshold_per_hour": threshold_per_hour,
        "detected_at": datetime.now(tz=timezone.utc).isoformat(),
        "recommended_action": (
            "Route to Admin: broken engine OR confused operator — "
            "review last hour of overrides by this user."
        ),
    }
    logger.warning(
        "[human_override.rate_limit] %s overrode %d times in last %dmin "
        "(threshold=%d/hr); routing to Admin",
        overrider_user_id, count, window_minutes, threshold_per_hour,
    )
    return alert
