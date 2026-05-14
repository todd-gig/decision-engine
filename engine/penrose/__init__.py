"""penrose — Falsification Scoreboard (8/8 metrics endpoint).

Surfaces all 8 Penrose-Falsification signals from the ecosystem as a single
read-only API. Per `~/.claude/projects/-Users-admin/memory/penrose_falsification_doctrine.md`,
Gigaton's success ≡ Penrose practically weakened. This scoreboard is the
quarterly-reviewable evidence side.

Eight signals:
  1. codification_rate         — patterns promoted Claude→Python (target ↑)
  2. human_override_rate       — overrides ÷ decisions, per class (target ↓)
  3. decision_velocity         — median sec/decision (target ↓)
  4. ovs_variance              — |variance| across CalibrationRevisions (target ↓)
  5. cascade_multiplier        — mean observed multiplier when ≥3 systems share
                                  a decision; targets 2.2× (Framework 5.12)
  6. super_additive_network_value — STUB (awaits PPEME BFT wiring)
  7. revenue_per_human_touch   — touch counter live; revenue side via env var
                                  PENROSE_REVENUE_USD_OVERRIDE
  8. drift_critical_count      — latest scan, sustained 0 target

Hard rule: stubs return explicit null + formula + next_milestone keys.
Never synthesize a metric value the dashboard would read as real.

v0.6 surface:
  - ScoreboardSnapshot           — façade with one method per metric + snapshot()
  - compute_decision_velocity    — reads timing audit table; ALTER on first write
  - record_participant_bft_state — PPEME inbox writer (table empty until wired)
  - count_human_touches          — counts decisions touched by humans

penrose_signal: weakens
penrose_dimension: codification | override_rate | velocity | variance | cascade |
                   network_value | revenue_per_touch | drift_count
"""
from __future__ import annotations

from .scoreboard import (
    METRIC_NAMES,
    PENROSE_SCOREBOARD_VERSION,
    ScoreboardSnapshot,
)
from .velocity import (
    compute_decision_velocity,
    record_decision_timing,
)
from .network_value_emitter import (
    NETWORK_VALUE_TABLE,
    NETWORK_VALUE_STATE_DIMENSIONS,
    record_participant_bft_state,
    list_observations,
)
from .human_touch_counter import (
    count_human_touches,
    HumanTouchSummary,
)

__all__ = [
    "PENROSE_SCOREBOARD_VERSION",
    "METRIC_NAMES",
    "ScoreboardSnapshot",
    "compute_decision_velocity",
    "record_decision_timing",
    "NETWORK_VALUE_TABLE",
    "NETWORK_VALUE_STATE_DIMENSIONS",
    "record_participant_bft_state",
    "list_observations",
    "count_human_touches",
    "HumanTouchSummary",
]
