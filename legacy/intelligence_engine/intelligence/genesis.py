"""
intelligence/genesis.py
Generates new decision templates, RTQL rules, and intelligence briefs
from confirmed patterns and causal graphs.

This is the self-amplification layer — the system creates new intelligence
artifacts that feed back into future decision cycles.

Outputs land in data/generated/templates/, data/generated/rules/, and
data/generated/ (briefs).
"""

import sys
import os
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.pattern_detector import Pattern
from intelligence.causal_engine import CausalEdge
from persistence.db import DatabaseManager


@dataclass
class DecisionTemplate:
    """Pre-filled DecisionObject skeleton generated from a pattern."""
    template_id: str
    source_pattern_id: str
    decision_class: str
    description: str
    recommended_value_score_ranges: dict    # {"revenue_impact": [min, max], ...}
    recommended_trust_score_ranges: dict
    suggested_title_prefix: str
    notes: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class RTQLRule:
    """A generated RTQL threshold rule derived from a causal edge."""
    rule_id: str
    source_description: str
    condition: str          # Human-readable: "evidence_quality < 3 in D3 decisions"
    effect: str             # What the rule does
    variable_affected: str
    adjustment_direction: str   # "raise" | "lower"
    confidence: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _ensure_dirs(base_dir: str):
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(base_dir, "templates")).mkdir(exist_ok=True)
    Path(os.path.join(base_dir, "rules")).mkdir(exist_ok=True)


def generate_decision_template(
    pattern: Pattern,
    db: DatabaseManager,
    generated_dir: str,
) -> DecisionTemplate:
    """
    For a confirmed verdict_cluster pattern, generate a pre-filled
    DecisionObject skeleton with recommended score ranges derived from
    historical decisions of this class.
    """
    _ensure_dirs(generated_dir)
    decisions = db.get_decisions_by_class(pattern.decision_class)

    # Derive recommended score ranges from historical data
    value_scores = [d["net_value_score"] for d in decisions if d["net_value_score"] is not None]
    trust_totals = [d["trust_total"] for d in decisions if d["trust_total"] is not None]

    if value_scores:
        v_min = min(value_scores)
        v_max = max(value_scores)
        v_median = sorted(value_scores)[len(value_scores) // 2]
    else:
        v_min, v_max, v_median = 0, 20, 10

    if trust_totals:
        t_min = min(trust_totals)
        t_max = max(trust_totals)
    else:
        t_min, t_max = 14, 28

    template = DecisionTemplate(
        template_id=str(uuid.uuid4())[:8],
        source_pattern_id=pattern.pattern_id,
        decision_class=pattern.decision_class,
        description=(
            f"Auto-generated template for {pattern.decision_class} decisions. "
            f"Based on {pattern.occurrence_count} historical instances. "
            f"Pattern: {pattern.description[:100]}"
        ),
        recommended_value_score_ranges={
            "net_value_score": [round(v_min, 1), round(v_max, 1)],
            "target_net_value": round(v_median, 1),
        },
        recommended_trust_score_ranges={
            "trust_total": [round(t_min, 1), round(t_max, 1)],
        },
        suggested_title_prefix=f"[{pattern.decision_class}] ",
        notes=(
            f"Confidence: {pattern.confidence_score:.2f}. "
            f"This template reflects {pattern.occurrence_count} decisions "
            f"that produced verdict pattern: '{pattern.pattern_type}'. "
            f"Review and adjust score ranges before using as a decision baseline."
        ),
    )

    # Save to disk
    output_path = os.path.join(generated_dir, "templates", f"template_{template.template_id}.json")
    with open(output_path, "w") as f:
        json.dump({
            "template_id": template.template_id,
            "source_pattern_id": template.source_pattern_id,
            "decision_class": template.decision_class,
            "description": template.description,
            "recommended_value_score_ranges": template.recommended_value_score_ranges,
            "recommended_trust_score_ranges": template.recommended_trust_score_ranges,
            "suggested_title_prefix": template.suggested_title_prefix,
            "notes": template.notes,
            "created_at": template.created_at,
        }, f, indent=2)

    return template


def generate_rtql_rule(
    edge: CausalEdge,
    generated_dir: str,
) -> RTQLRule:
    """
    Convert a high-confidence causal edge into a tunable RTQL rule.
    Rules are generated when correlation is strong enough to inform threshold changes.
    """
    _ensure_dirs(generated_dir)

    # Determine adjustment direction from correlation + outcome direction
    if edge.outcome_direction == "negative" and edge.correlation_strength < -0.3:
        direction = "raise"
        effect = (
            f"Raise minimum RTQL qualification threshold for {edge.variable_name} "
            f"in {edge.decision_class} decisions to reduce negative outcome exposure."
        )
        condition = (
            f"{edge.variable_name} is in '{edge.variable_value_band}' band "
            f"for {edge.decision_class} decisions "
            f"(correlation with negative outcomes: {edge.correlation_strength:.3f})"
        )
    elif edge.outcome_direction == "positive" and edge.correlation_strength > 0.3:
        direction = "lower"
        effect = (
            f"Lower RTQL barrier for {edge.variable_name} in {edge.decision_class} decisions "
            f"to increase throughput of positively correlated inputs."
        )
        condition = (
            f"{edge.variable_name} is in '{edge.variable_value_band}' band "
            f"for {edge.decision_class} decisions "
            f"(correlation with positive outcomes: {edge.correlation_strength:.3f})"
        )
    else:
        direction = "monitor"
        effect = f"Monitor {edge.variable_name} for {edge.decision_class} decisions — signal unclear."
        condition = f"{edge.variable_name} shows weak causal signal (r={edge.correlation_strength:.3f})"

    rule = RTQLRule(
        rule_id=str(uuid.uuid4())[:8],
        source_description=f"Causal edge: {edge.variable_name} → {edge.outcome_direction} outcomes",
        condition=condition,
        effect=effect,
        variable_affected=edge.variable_name,
        adjustment_direction=direction,
        confidence=edge.causal_confidence,
    )

    output_path = os.path.join(generated_dir, "rules", f"rule_{rule.rule_id}.json")
    with open(output_path, "w") as f:
        json.dump({
            "rule_id": rule.rule_id,
            "source_description": rule.source_description,
            "condition": rule.condition,
            "effect": rule.effect,
            "variable_affected": rule.variable_affected,
            "adjustment_direction": rule.adjustment_direction,
            "confidence": rule.confidence,
            "created_at": rule.created_at,
        }, f, indent=2)

    return rule


def generate_intelligence_brief(
    patterns: list[Pattern],
    causal_graph: list[CausalEdge],
    weight_history: list[dict],
    weight_update_result: dict,
    claude_narrative: str,
    generated_dir: str,
    db: DatabaseManager,
) -> str:
    """
    Assemble the full intelligence brief combining all system outputs.
    Returns the file path of the saved brief.
    """
    _ensure_dirs(generated_dir)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"intelligence_brief_{ts}.md"
    output_path = os.path.join(generated_dir, filename)

    variance = db.get_variance_summary()

    lines = [
        f"# Intelligence Brief — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "> Auto-generated by the Intelligence Engine. "
        "This brief summarizes learned patterns, causal drivers, "
        "weight evolution, and recommended next actions.",
        "",
        "---",
        "",
        "## 1. Pattern Summary",
        "",
        f"**{len(patterns)} patterns detected** across decision history.",
        "",
    ]

    if patterns:
        for p in patterns[:10]:
            lines.append(f"- **[{p.pattern_type}]** `{p.decision_class}` — {p.description}")
            lines.append(f"  *(confidence: {p.confidence_score:.2f}, n={p.occurrence_count})*")
    else:
        lines.append("- No patterns detected yet. Accumulate more decisions.")

    lines += [
        "",
        "---",
        "",
        "## 2. Causal Analysis",
        "",
        f"**{len(causal_graph)} causal edges** identified from outcome data.",
        "",
    ]

    if causal_graph:
        top_edges = sorted(causal_graph, key=lambda e: abs(e.correlation_strength), reverse=True)[:8]
        lines.append("| Variable | Class | Direction | r | Confidence | n |")
        lines.append("|---|---|---|---|---|---|")
        for e in top_edges:
            lines.append(
                f"| `{e.variable_name}` | {e.decision_class} | {e.outcome_direction} "
                f"| {e.correlation_strength:+.3f} | {e.causal_confidence} | {e.sample_count} |"
            )
    else:
        lines.append("- No causal data yet. Record outcomes to build the causal graph.")

    lines += [
        "",
        "---",
        "",
        "## 3. Weight Evolution",
        "",
    ]

    applied = weight_update_result.get("applied", [])
    if applied:
        lines.append(f"**{len(applied)} weight adjustments** proposed this cycle:")
        lines.append("")
        for adj in applied:
            prefix = "(DRY RUN) " if weight_update_result.get("dry_run") else ""
            sign = "+" if adj["delta"] > 0 else ""
            lines.append(
                f"- {prefix}`{adj['key']}`: {adj['old']:.3f} → {adj['new']:.3f} "
                f"({sign}{adj['delta']:.4f}) — *{adj['reason'][:80]}*"
            )
    else:
        lines.append("- No weight adjustments warranted this cycle.")

    if weight_history:
        lines.append("")
        lines.append(f"**Historical weight changes:** {len(weight_history)} total recorded.")

    lines += [
        "",
        "---",
        "",
        "## 4. Claude Intelligence Layer Assessment",
        "",
        claude_narrative,
        "",
        "---",
        "",
        "## 5. Outcome Variance Summary",
        "",
    ]

    if variance["total_outcomes"] > 0:
        lines += [
            f"- Total outcomes recorded: **{variance['total_outcomes']}**",
            f"- Mean variance score: **{variance['mean_variance']:+.3f}**",
            f"- Positive outcomes: {variance['positive_outcomes']}",
            f"- Negative outcomes: {variance['negative_outcomes']}",
            f"- Risk surprise rate: **{variance['risk_surprise_rate']:.0%}**",
        ]
    else:
        lines.append("- No outcomes recorded yet.")

    lines += [
        "",
        "---",
        "",
        "## 6. Recommended Next Actions",
        "",
        "1. **Record outcomes** for all executed decisions to build the causal graph.",
        "2. **Review proposed weight adjustments** and apply when confidence is 'high'.",
        "3. **Inspect generated templates** in `data/generated/templates/` for reuse.",
        "4. **Feed certified human variables** through the intake pipeline for higher-trust inputs.",
        "5. **Run next intelligence cycle** after accumulating 5 additional decisions.",
        "",
        "---",
        "",
        f"*Generated by Intelligence Engine v1.0 — {datetime.utcnow().isoformat()}*",
    ]

    brief_content = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(brief_content)

    return output_path
