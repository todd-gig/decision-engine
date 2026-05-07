"""
intelligence/causal_engine.py
Builds a causal variable graph from outcome data.

Identifies which input variables (from DecisionObject scoring dimensions)
causally drive positive vs negative outcomes by computing correlations
between input variables and composite_variance_score.

NOTE ON CAUSATION vs CORRELATION:
causal_confidence is labeled low/medium/high based on sample count, not
statistical significance. With small datasets (N<10), this is pattern
correlation. The system is architecturally designed to improve as data
accumulates — RTQL's CausalChecks model distinguishes qualified signals
from certified ones, and the same principle applies here.
"""

import sys
import os
import json
import math
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence.db import DatabaseManager


@dataclass
class CausalEdge:
    variable_name: str
    variable_value_band: str        # "high (4-5)", "mid (2-3)", "low (0-1)"
    outcome_direction: str          # "positive" | "negative" | "neutral"
    correlation_strength: float     # -1.0 to 1.0 (Pearson r or simple proportion)
    sample_count: int
    causal_confidence: str          # "low" (<5), "medium" (5-15), "high" (>15)
    decision_class: str


def _band(value: float, max_val: float = 5.0) -> str:
    """Categorize a numeric score into a human-readable band."""
    if value is None:
        return "unknown"
    frac = value / max_val if max_val > 0 else 0
    if frac >= 0.7:
        return "high"
    elif frac >= 0.4:
        return "mid"
    else:
        return "low"


def _pearson(xs: list[float], ys: list[float]) -> float:
    """
    Compute Pearson correlation coefficient between two lists.
    Returns 0.0 if fewer than 3 paired data points (not enough for meaningful correlation).
    """
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def _causal_confidence(n: int) -> str:
    if n >= 15:
        return "high"
    elif n >= 5:
        return "medium"
    else:
        return "low"


def _extract_scores_from_result_json(result_json: str) -> dict:
    """
    Parse the pipeline_result_json blob to extract key numeric variables
    that can be correlated with outcomes.
    Returns a flat dict of variable_name → float.
    """
    try:
        data = json.loads(result_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    scores: dict[str, float] = {}

    # Top-level pipeline metrics
    for key in ("net_value_score", "trust_total", "alignment_composite",
                "priority_score"):
        val = data.get(key)
        if val is not None:
            scores[key] = float(val)

    # RTQL multiplier
    rtql = data.get("rtql_result", {})
    if isinstance(rtql, dict):
        mult = rtql.get("trust_multiplier")
        if mult is not None:
            scores["rtql_multiplier"] = float(mult)

    # Value scores
    vs = data.get("value_scores") or data.get("value_assessment", {})
    if isinstance(vs, dict):
        for k in ("revenue_impact", "cost_efficiency", "time_leverage",
                  "strategic_alignment", "customer_human_benefit",
                  "knowledge_asset_creation", "compounding_potential",
                  "reversibility", "downside_risk", "execution_drag",
                  "uncertainty", "ethical_misalignment"):
            val = vs.get(k)
            if val is not None:
                scores[f"value.{k}"] = float(val)

    # Trust scores
    ts = data.get("trust_scores") or {}
    if isinstance(ts, dict):
        for k in ("evidence_quality", "logic_integrity", "outcome_history",
                  "context_fit", "stakeholder_clarity", "risk_containment",
                  "auditability"):
            val = ts.get(k)
            if val is not None:
                scores[f"trust.{k}"] = float(val)

    return scores


def build_causal_graph(db: DatabaseManager) -> list[CausalEdge]:
    """
    For each decision class that has matched outcomes:
    1. Load all (decision, outcome) pairs via JOIN
    2. Extract numeric input variables from pipeline_result_json
    3. For each variable compute correlation with composite_variance_score
    4. Build causal edges

    Returns edges sorted by abs(correlation_strength) descending.
    Persists edges to causal_graphs table.
    """
    paired = db.get_decisions_with_outcomes()
    edges: list[CausalEdge] = []

    if len(paired) < 2:
        return edges

    # Group by decision_class
    from collections import defaultdict
    by_class: dict[str, list[dict]] = defaultdict(list)
    for row in paired:
        by_class[row["decision_class"]].append(row)

    for dclass, rows in by_class.items():
        # Build per-variable correlation arrays
        var_arrays: dict[str, list[tuple[float, float]]] = defaultdict(list)

        for row in rows:
            variance = row.get("composite_variance_score")
            if variance is None:
                continue
            variance = float(variance)

            result_json = row.get("pipeline_result_json", "")
            scores = _extract_scores_from_result_json(result_json)

            for var_name, var_val in scores.items():
                var_arrays[var_name].append((var_val, variance))

        # Compute correlation for each variable
        for var_name, pairs in var_arrays.items():
            if len(pairs) < 2:
                continue

            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            r = _pearson(xs, ys)

            # Determine direction from correlation sign
            if r > 0.1:
                direction = "positive"
            elif r < -0.1:
                direction = "negative"
            else:
                direction = "neutral"

            # Determine value band from median of xs
            sorted_xs = sorted(xs)
            median_x = sorted_xs[len(sorted_xs) // 2]
            value_band = _band(median_x)

            confidence = _causal_confidence(len(pairs))

            edge = CausalEdge(
                variable_name=var_name,
                variable_value_band=value_band,
                outcome_direction=direction,
                correlation_strength=round(r, 4),
                sample_count=len(pairs),
                causal_confidence=confidence,
                decision_class=dclass,
            )
            edges.append(edge)

            # Persist to DB
            db.store_causal_edge({
                "decision_class": dclass,
                "variable_name": var_name,
                "variable_value_band": value_band,
                "outcome_direction": direction,
                "correlation_strength": r,
                "sample_count": len(pairs),
                "causal_confidence": confidence,
            })

    # Sort by absolute correlation strength
    edges.sort(key=lambda e: abs(e.correlation_strength), reverse=True)
    return edges


def get_top_causal_drivers(
    graph: list[CausalEdge],
    decision_class: str = None,
    top_n: int = 5,
) -> list[CausalEdge]:
    """Filter by decision_class if provided, return top N by |correlation_strength|."""
    filtered = [e for e in graph if decision_class is None or e.decision_class == decision_class]
    filtered.sort(key=lambda e: abs(e.correlation_strength), reverse=True)
    return filtered[:top_n]


def build_causal_narrative(graph: list[CausalEdge]) -> str:
    """Human-readable description of the causal graph."""
    if not graph:
        return "No causal data available yet. Accumulate more outcomes to build the causal graph."

    lines = ["CAUSAL VARIABLE ANALYSIS", "─" * 50]
    by_class: dict[str, list[CausalEdge]] = {}
    for e in graph:
        by_class.setdefault(e.decision_class, []).append(e)

    for dclass, edges in by_class.items():
        lines.append(f"\n  {dclass} decisions:")
        top = sorted(edges, key=lambda e: abs(e.correlation_strength), reverse=True)[:5]
        for e in top:
            sign = "+" if e.correlation_strength > 0 else ""
            lines.append(
                f"    {e.variable_name:45s} r={sign}{e.correlation_strength:.3f}  "
                f"[{e.causal_confidence} confidence, n={e.sample_count}]"
            )

    return "\n".join(lines)
