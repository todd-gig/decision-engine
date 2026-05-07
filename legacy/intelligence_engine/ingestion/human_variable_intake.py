"""
ingestion/human_variable_intake.py
Accepts raw human-weighted inputs, normalizes to RTQL dimensions,
classifies through the trust pipeline, and returns trust-qualified variables
ready for DecisionObject construction.

Human variables flow through RTQL before entering any decision — this is
architecturally non-negotiable per the RTQL doctrine.
"""

import sys
import os
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import RTQLInput, RTQLScores, CausalChecks, RTQLResult, RTQLStage
from engine.rtql_filter import classify_rtql


# ─── RTQL SCORE MAPPING FROM HUMAN CONFIDENCE ─────────────────────────────────
# Maps human "how_confident" (1-5) to approximate RTQL dimension scores.
# All values come from RTQLScores.ALLOWED_SCORES = {0,1,2,3,4,5,6,8,10,12}

CONFIDENCE_TO_RTQL = {
    5: dict(source_integrity=10, exposure_count=6, independence=8,
            explainability=8,  replicability=6, adversarial_robustness=6, novelty_yield=3),
    4: dict(source_integrity=8,  exposure_count=5, independence=6,
            explainability=6,  replicability=6, adversarial_robustness=5, novelty_yield=2),
    3: dict(source_integrity=5,  exposure_count=3, independence=4,
            explainability=5,  replicability=4, adversarial_robustness=4, novelty_yield=1),
    2: dict(source_integrity=3,  exposure_count=2, independence=2,
            explainability=3,  replicability=2, adversarial_robustness=2, novelty_yield=0),
    1: dict(source_integrity=1,  exposure_count=1, independence=1,
            explainability=1,  replicability=1, adversarial_robustness=1, novelty_yield=0),
}


@dataclass
class HumanVariable:
    """A single human-weighted input before trust classification."""
    variable_name: str
    claimed_value: float
    source: str
    how_confident: int          # 1-5 scale (human-friendly)
    evidence_description: str = ""
    category: str = ""          # optional: maps to one of the 15 survey categories


@dataclass
class ClassifiedVariable:
    """A human variable after RTQL trust classification."""
    raw: HumanVariable
    rtql_result: RTQLResult
    trust_qualified: bool       # True if stage not in {NOISE, WEAK_SIGNAL}
    effective_value: float      # claimed_value × trust_multiplier
    stage_label: str
    trust_multiplier: float


@dataclass
class HumanVariableSet:
    """Complete output of the human variable ingestion pipeline."""
    raw_inputs: list[HumanVariable]
    classified: list[ClassifiedVariable]
    noise: list[ClassifiedVariable]
    weak_signal: list[ClassifiedVariable]
    qualified: list[ClassifiedVariable]
    certified: list[ClassifiedVariable]
    first_principles: list[ClassifiedVariable]
    overall_trust_quality: str      # "insufficient" | "marginal" | "adequate" | "strong"
    rtql_summary: dict


def normalize_human_input(var: HumanVariable) -> RTQLInput:
    """
    Convert human-friendly HumanVariable to RTQLInput.
    Maps confidence rating (1-5) to RTQL dimension scores.
    Sets provenance flags based on whether source/evidence are provided.
    """
    confidence = max(1, min(5, var.how_confident))
    scores_map = CONFIDENCE_TO_RTQL[confidence]

    return RTQLInput(
        claim=f"{var.variable_name} = {var.claimed_value} ({var.source})",
        source=var.source,
        is_identifiable=bool(var.source and var.source.strip()),
        has_provenance=bool(var.evidence_description and var.evidence_description.strip()),
        scores=RTQLScores(
            source_integrity=scores_map["source_integrity"],
            exposure_count=scores_map["exposure_count"],
            independence=scores_map["independence"],
            explainability=scores_map["explainability"],
            replicability=scores_map["replicability"],
            adversarial_robustness=scores_map["adversarial_robustness"],
            novelty_yield=scores_map["novelty_yield"],
        ),
        causal_checks=CausalChecks(
            reveals_causal_mechanism=confidence >= 4,
            is_irreducible=confidence == 5,
            survives_authority_removal=confidence >= 3,
            survives_context_shift=confidence >= 4,
        ),
    )


def _stage_label(result: RTQLResult) -> str:
    return result.stage.value if hasattr(result.stage, "value") else str(result.stage)


def classify_human_variables(raw_variables: list[HumanVariable]) -> HumanVariableSet:
    """
    Run normalize_human_input + classify_rtql on each variable.
    Group results by RTQL stage.
    """
    classified: list[ClassifiedVariable] = []

    for var in raw_variables:
        rtql_input = normalize_human_input(var)
        rtql_result = classify_rtql(rtql_input)
        stage = _stage_label(rtql_result)
        trust_qualified = stage not in ("noise", "weak_signal")
        effective_value = var.claimed_value * rtql_result.trust_multiplier

        classified.append(ClassifiedVariable(
            raw=var,
            rtql_result=rtql_result,
            trust_qualified=trust_qualified,
            effective_value=effective_value,
            stage_label=stage,
            trust_multiplier=rtql_result.trust_multiplier,
        ))

    noise       = [c for c in classified if c.stage_label == "noise"]
    weak_signal = [c for c in classified if c.stage_label == "weak_signal"]
    echo_signal = [c for c in classified if c.stage_label == "echo_signal"]
    q           = [c for c in classified if c.stage_label in ("qualified", "echo_signal")]
    cert        = [c for c in classified if c.stage_label in ("certified", "certification_gap")]
    fp          = [c for c in classified if c.stage_label in
                   ("research_grade", "first_principles_candidate", "axiom_candidate")]

    # Determine overall trust quality
    total = len(classified)
    if total == 0:
        quality = "insufficient"
    else:
        qualified_frac = len(q) / total
        cert_frac      = (len(cert) + len(fp)) / total
        if cert_frac >= 0.5:
            quality = "strong"
        elif qualified_frac + cert_frac >= 0.6:
            quality = "adequate"
        elif qualified_frac + cert_frac >= 0.3:
            quality = "marginal"
        else:
            quality = "insufficient"

    rtql_summary = {
        "total": total,
        "noise": len(noise),
        "weak_signal": len(weak_signal),
        "echo_signal": len(echo_signal),
        "qualified": len(q),
        "certified": len(cert),
        "first_principles": len(fp),
        "trust_qualified_count": sum(1 for c in classified if c.trust_qualified),
        "mean_trust_multiplier": (
            sum(c.trust_multiplier for c in classified) / total if total else 0.0
        ),
    }

    return HumanVariableSet(
        raw_inputs=raw_variables,
        classified=classified,
        noise=noise,
        weak_signal=weak_signal,
        qualified=q,
        certified=cert,
        first_principles=fp,
        overall_trust_quality=quality,
        rtql_summary=rtql_summary,
    )


def variables_to_decision_scores(variable_set: HumanVariableSet) -> dict:
    """
    Map trust-qualified variables to DecisionObject score field hints.
    Only certified+ variables contribute to trust_scores.
    Qualified variables contribute with their RTQL multiplier applied.
    Returns a partial field dict for the Claude bridge to complete.
    """
    hints: dict = {
        "trust_score_hints": {},
        "value_score_hints": {},
        "qualified_variable_names": [],
        "certified_variable_names": [],
        "noise_variable_names": [],
        "effective_values": {},
    }

    for cv in variable_set.classified:
        name = cv.raw.variable_name
        hints["effective_values"][name] = cv.effective_value

        if cv.stage_label in ("noise", "weak_signal"):
            hints["noise_variable_names"].append(name)
            continue

        hints["qualified_variable_names"].append(name)

        # Map variable names to known scoring dimensions (heuristic)
        lower = name.lower()
        if any(k in lower for k in ("revenue", "income", "sales", "conversion")):
            hints["value_score_hints"]["revenue_impact"] = min(5, cv.effective_value * 5)
        elif any(k in lower for k in ("cost", "expense", "efficiency")):
            hints["value_score_hints"]["cost_efficiency"] = min(5, cv.effective_value * 5)
        elif any(k in lower for k in ("trust", "credibility", "reputation")):
            hints["trust_score_hints"]["evidence_quality"] = min(5, cv.effective_value * 5)
        elif any(k in lower for k in ("evidence", "data", "research")):
            hints["trust_score_hints"]["evidence_quality"] = min(5, cv.effective_value * 5)
        elif any(k in lower for k in ("risk", "downside", "threat")):
            hints["value_score_hints"]["downside_risk"] = min(5, cv.effective_value * 5)

        if cv.stage_label in ("certified", "certification_gap", "research_grade",
                               "first_principles_candidate", "axiom_candidate"):
            hints["certified_variable_names"].append(name)

    return hints


def print_intake_report(variable_set: HumanVariableSet):
    """Print a human-readable RTQL classification report."""
    s = variable_set.rtql_summary
    print("\n" + "═" * 60)
    print("  HUMAN VARIABLE INTAKE — RTQL CLASSIFICATION REPORT")
    print("═" * 60)
    print(f"  Total variables received : {s['total']}")
    print(f"  Trust qualified          : {s['trust_qualified_count']} / {s['total']}")
    print(f"  Overall trust quality    : {variable_set.overall_trust_quality.upper()}")
    print(f"  Mean trust multiplier    : {s['mean_trust_multiplier']:.2f}x")
    print()
    for cv in variable_set.classified:
        icon = "✓" if cv.trust_qualified else "✗"
        print(f"  {icon} [{cv.stage_label:30s}] {cv.raw.variable_name}")
        print(f"      Raw: {cv.raw.claimed_value:.3f}  →  Effective: {cv.effective_value:.3f}  "
              f"(×{cv.trust_multiplier:.2f})  Confidence: {cv.raw.how_confident}/5")
    print("═" * 60 + "\n")
