"""human_override — capture every human override of an engine decision.

Per specs/human_override_engine_v0.md. v0 sub-package surface:
  - record(override): write to human_overrides table
  - classify(override): apply taxonomy + downstream weights
  - storage: SQLite schema + connection
"""
from __future__ import annotations

from .recorder import (
    OverrideClassification,
    OverrideRecord,
    OverrideType,
    classify_override,
    record_override,
)

__all__ = [
    "OverrideRecord",
    "OverrideClassification",
    "OverrideType",
    "record_override",
    "classify_override",
]
