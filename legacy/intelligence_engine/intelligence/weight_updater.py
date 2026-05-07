"""
intelligence/weight_updater.py
Updates engine.yaml weights based on variance analysis from outcomes.
This is the self-improvement mechanism — the system modifies its own
scoring weights based on what it learns from real-world outcomes.

Safety design:
- No single weight changes by more than ADJUSTMENT_CAP per cycle
- No weight goes below WEIGHT_MIN or above WEIGHT_MAX
- Each change is logged to weight_history in SQLite
- dry_run=True shows proposed changes without writing to disk
- File is written atomically (tmp → rename) to prevent corruption
"""

import sys
import os
import yaml
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence.db import DatabaseManager
from engine.config import load_config, EngineConfig


ADJUSTMENT_CAP = 0.3    # Max change per weight per update cycle
WEIGHT_MIN = 0.1        # Floor for any weight
WEIGHT_MAX = 5.0        # Ceiling for any weight


@dataclass
class WeightAdjustment:
    yaml_section: str       # "value_weights" | "penalty_weights" | "trust_multiplier"
    key_name: str
    old_value: float
    new_value: float
    adjustment_delta: float
    reason: str
    triggered_by: str       # decision_id or pattern_id
    confidence: str         # "low" | "medium" | "high"


def load_current_weights(yaml_path: str) -> dict:
    """Return the full engine.yaml as a dict."""
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f) or {}


def _clamp_delta(current: float, delta: float) -> tuple[float, float]:
    """Apply safety caps. Returns (clamped_delta, new_value)."""
    clamped_delta = max(-ADJUSTMENT_CAP, min(ADJUSTMENT_CAP, delta))
    new_value = current + clamped_delta
    new_value = max(WEIGHT_MIN, min(WEIGHT_MAX, new_value))
    actual_delta = new_value - current
    return actual_delta, new_value


def compute_weight_adjustments(
    db: DatabaseManager,
    yaml_path: str,
    min_samples: int = 2,
) -> list[WeightAdjustment]:
    """
    Analyze outcomes and compute proposed weight adjustments.
    Returns a list of WeightAdjustment objects (not yet applied).

    Rules:
    - Negative mean variance → likely overestimating value; reduce highest value weight
    - Elevated risk_surprise rate → increase downside_risk penalty
    - Positive mean variance → compounding_potential may be underweighted
    - Systematic low trust → no weight change, flag playbook update needed
    """
    adjustments: list[WeightAdjustment] = []
    summary = db.get_variance_summary()

    if summary["total_outcomes"] < min_samples:
        return adjustments

    weights = load_current_weights(yaml_path)
    vw = weights.get("value_weights", {})
    pw = weights.get("penalty_weights", {})
    mean_var = summary.get("mean_variance", 0.0)
    risk_rate = summary.get("risk_surprise_rate", 0.0)

    triggered_by = f"intelligence_cycle_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    confidence = "high" if summary["total_outcomes"] >= 10 else "medium" if summary["total_outcomes"] >= 5 else "low"

    # ── Rule 1: Negative mean variance → reduce revenue_impact weight ──────────
    if mean_var < -0.15 and "revenue_impact" in vw:
        delta = -0.05 * abs(mean_var)
        old = vw["revenue_impact"]
        actual_delta, new_val = _clamp_delta(old, delta)
        if abs(actual_delta) > 0.001:
            adjustments.append(WeightAdjustment(
                yaml_section="value_weights",
                key_name="revenue_impact",
                old_value=old,
                new_value=new_val,
                adjustment_delta=actual_delta,
                reason=f"Negative mean variance ({mean_var:.3f}) — revenue_impact overweighted",
                triggered_by=triggered_by,
                confidence=confidence,
            ))

    # ── Rule 2: Negative mean variance → increase uncertainty penalty ──────────
    if mean_var < -0.15 and "uncertainty" in pw:
        delta = 0.05 * abs(mean_var)
        old = pw["uncertainty"]
        actual_delta, new_val = _clamp_delta(old, delta)
        if abs(actual_delta) > 0.001:
            adjustments.append(WeightAdjustment(
                yaml_section="penalty_weights",
                key_name="uncertainty",
                old_value=old,
                new_value=new_val,
                adjustment_delta=actual_delta,
                reason=f"Negative mean variance ({mean_var:.3f}) — uncertainty underweighted",
                triggered_by=triggered_by,
                confidence=confidence,
            ))

    # ── Rule 3: Positive mean variance → increase compounding_potential weight ─
    if mean_var > 0.2 and "compounding_potential" in vw:
        delta = 0.03 * mean_var
        old = vw["compounding_potential"]
        actual_delta, new_val = _clamp_delta(old, delta)
        if abs(actual_delta) > 0.001:
            adjustments.append(WeightAdjustment(
                yaml_section="value_weights",
                key_name="compounding_potential",
                old_value=old,
                new_value=new_val,
                adjustment_delta=actual_delta,
                reason=f"Positive mean variance ({mean_var:.3f}) — compounding_potential underweighted",
                triggered_by=triggered_by,
                confidence=confidence,
            ))

    # ── Rule 4: High risk_surprise rate → increase downside_risk penalty ───────
    if risk_rate > 0.2 and "downside_risk" in pw:
        delta = 0.1 * risk_rate
        old = pw["downside_risk"]
        actual_delta, new_val = _clamp_delta(old, delta)
        if abs(actual_delta) > 0.001:
            adjustments.append(WeightAdjustment(
                yaml_section="penalty_weights",
                key_name="downside_risk",
                old_value=old,
                new_value=new_val,
                adjustment_delta=actual_delta,
                reason=f"Risk surprise rate {risk_rate:.0%} elevated — downside_risk penalty insufficient",
                triggered_by=triggered_by,
                confidence=confidence,
            ))

    return adjustments


def apply_weight_adjustments(
    adjustments: list[WeightAdjustment],
    yaml_path: str,
    db: DatabaseManager,
    claude_recommendations: dict = None,
    dry_run: bool = True,
) -> dict:
    """
    Apply weight adjustments to engine.yaml with atomic write.
    Also applies Claude recommendations (capped at ADJUSTMENT_CAP).

    dry_run=True: shows what would change without writing to disk.
    Returns {"applied": [...], "skipped": [...], "dry_run": bool}
    """
    applied = []
    skipped = []

    weights = load_current_weights(yaml_path)

    # Merge Claude recommendations as additional adjustments
    all_adjustments = list(adjustments)
    if claude_recommendations:
        for section in ("value_weights", "penalty_weights"):
            for key, delta in claude_recommendations.get(section, {}).items():
                current = weights.get(section, {}).get(key)
                if current is not None:
                    actual_delta, new_val = _clamp_delta(current, float(delta))
                    if abs(actual_delta) > 0.001:
                        all_adjustments.append(WeightAdjustment(
                            yaml_section=section,
                            key_name=key,
                            old_value=current,
                            new_value=new_val,
                            adjustment_delta=actual_delta,
                            reason=f"Claude recommendation: {claude_recommendations.get('reasoning', 'N/A')[:80]}",
                            triggered_by="claude_bridge",
                            confidence="medium",
                        ))

    if not all_adjustments:
        return {"applied": [], "skipped": [], "dry_run": dry_run,
                "message": "No adjustments warranted this cycle"}

    for adj in all_adjustments:
        section = weights.get(adj.yaml_section, {})
        if adj.key_name not in section:
            skipped.append({"key": f"{adj.yaml_section}.{adj.key_name}", "reason": "key not found in yaml"})
            continue

        if not dry_run:
            weights[adj.yaml_section][adj.key_name] = adj.new_value
            db.log_weight_change(
                section=adj.yaml_section,
                key=adj.key_name,
                old=adj.old_value,
                new=adj.new_value,
                reason=adj.reason,
                triggered_by=adj.triggered_by,
            )

        applied.append({
            "key": f"{adj.yaml_section}.{adj.key_name}",
            "old": adj.old_value,
            "new": adj.new_value,
            "delta": round(adj.adjustment_delta, 4),
            "reason": adj.reason,
            "confidence": adj.confidence,
        })

    # Atomic write: write to .tmp first, then rename
    if not dry_run and applied:
        tmp_path = yaml_path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                yaml.dump(weights, f, default_flow_style=False, sort_keys=True)
            # Validate it parses cleanly
            with open(tmp_path, "r") as f:
                yaml.safe_load(f)
            # Atomic rename
            os.replace(tmp_path, yaml_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"Failed to write updated engine.yaml: {e}")

    return {"applied": applied, "skipped": skipped, "dry_run": dry_run}
