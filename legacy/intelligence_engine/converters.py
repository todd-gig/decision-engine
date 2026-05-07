"""
Converters for flat JSON payload ↔ engine dataclass conversion

Handles bidirectional conversion between:
- Flat JSON payloads (CLI input format)
- DecisionObject and related engine dataclasses
- PipelineResult → JSON-serializable dict
"""

import json
from typing import Any, Dict, Optional
from datetime import datetime

from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks,
    PipelineResult, RTQLResult, CertificateChain
)
from engine.audit import serialize_pipeline_result


# ─────────────────────────────────────────────
# ENUM MAPPINGS
# ─────────────────────────────────────────────

DECISION_CLASS_MAP = {
    "D0": DecisionClass.D0_INFORMATIONAL,
    "D1": DecisionClass.D1_REVERSIBLE_TACTICAL,
    "D2": DecisionClass.D2_OPERATIONAL,
    "D3": DecisionClass.D3_FINANCIAL,
    "D4": DecisionClass.D4_STRATEGIC,
    "D5": DecisionClass.D5_LEGAL_ETHICAL,
    "D6": DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST,
}

REVERSIBILITY_MAP = {
    "R1": ReversibilityTag.R1_EASILY_REVERSIBLE,
    "R2": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
    "R3": ReversibilityTag.R3_COSTLY_TO_REVERSE,
    "R4": ReversibilityTag.R4_EFFECTIVELY_IRREVERSIBLE,
}

TIME_HORIZON_MAP = {
    "immediate": TimeHorizon.IMMEDIATE,
    "near_term": TimeHorizon.NEAR_TERM,
    "mid_term": TimeHorizon.MID_TERM,
    "long_term": TimeHorizon.LONG_TERM,
}

# Reverse maps for serialization
DECISION_CLASS_REVERSE = {v: k for k, v in DECISION_CLASS_MAP.items()}
REVERSIBILITY_REVERSE = {v: k for k, v in REVERSIBILITY_MAP.items()}
TIME_HORIZON_REVERSE = {v: k for k, v in TIME_HORIZON_MAP.items()}


# ─────────────────────────────────────────────
# PAYLOAD → DECISION OBJECT CONVERSION
# ─────────────────────────────────────────────

def payload_to_decision(payload: Dict[str, Any]) -> tuple[DecisionObject, list[str]]:
    """
    Convert flat JSON payload to DecisionObject.

    Returns: (DecisionObject, validation_errors)
    validation_errors will be empty list if conversion successful.
    """
    errors = []

    try:
        decision_data = payload.get("decision", {})

        # Extract basic fields
        decision_id = decision_data.get("decision_id", "")
        title = decision_data.get("title", "")
        owner = decision_data.get("owner", "")
        problem_statement = decision_data.get("problem_statement", "")
        requested_action = decision_data.get("requested_action", "")
        context_summary = decision_data.get("context_summary", "")

        # Enum conversions with defaults
        decision_class_str = decision_data.get("decision_class", "D1")
        decision_class = DECISION_CLASS_MAP.get(
            decision_class_str,
            DecisionClass.D1_REVERSIBLE_TACTICAL
        )

        reversibility_str = decision_data.get("reversibility", "R1")
        reversibility = REVERSIBILITY_MAP.get(
            reversibility_str,
            ReversibilityTag.R1_EASILY_REVERSIBLE
        )

        time_horizon_str = decision_data.get("time_horizon", "immediate")
        time_horizon = TIME_HORIZON_MAP.get(
            time_horizon_str,
            TimeHorizon.IMMEDIATE
        )

        # Lists
        stakeholders = decision_data.get("stakeholders", [])
        constraints = decision_data.get("constraints", [])
        evidence_refs = decision_data.get("evidence_refs", [])
        assumptions = decision_data.get("assumptions", [])
        unknowns = decision_data.get("unknowns", [])
        required_approvals = decision_data.get("required_approvals", [])

        # Execution fields
        execution_plan = decision_data.get("execution_plan", "")
        monitoring_metric = decision_data.get("monitoring_metric", "")
        rollback_trigger = decision_data.get("rollback_trigger", "")
        review_date = decision_data.get("review_date")

        # State machine fields
        current_state = decision_data.get("current_state", "draft")
        actor_role = decision_data.get("actor_role", "AI_Domain_Agent")
        has_missing_data = decision_data.get("has_missing_data", False)
        ethical_conflict = decision_data.get("ethical_conflict", False)

        # Parse ValueScores
        value_scores_data = decision_data.get("value_scores", {})
        try:
            value_scores = ValueScores(
                revenue_impact=value_scores_data.get("revenue_impact", 0),
                cost_efficiency=value_scores_data.get("cost_efficiency", 0),
                time_leverage=value_scores_data.get("time_leverage", 0),
                strategic_alignment=value_scores_data.get("strategic_alignment", 0),
                customer_human_benefit=value_scores_data.get("customer_human_benefit", 0),
                knowledge_asset_creation=value_scores_data.get("knowledge_asset_creation", 0),
                compounding_potential=value_scores_data.get("compounding_potential", 0),
                reversibility=value_scores_data.get("reversibility", 0),
                downside_risk=value_scores_data.get("downside_risk", 0),
                execution_drag=value_scores_data.get("execution_drag", 0),
                uncertainty=value_scores_data.get("uncertainty", 0),
                ethical_misalignment=value_scores_data.get("ethical_misalignment", 0),
            )
            errors.extend(value_scores.validate())
        except Exception as e:
            errors.append(f"Invalid value_scores: {str(e)}")
            value_scores = ValueScores()

        # Parse TrustScores
        trust_scores_data = decision_data.get("trust_scores", {})
        try:
            trust_scores = TrustScores(
                evidence_quality=trust_scores_data.get("evidence_quality", 0),
                logic_integrity=trust_scores_data.get("logic_integrity", 0),
                outcome_history=trust_scores_data.get("outcome_history", 0),
                context_fit=trust_scores_data.get("context_fit", 0),
                stakeholder_clarity=trust_scores_data.get("stakeholder_clarity", 0),
                risk_containment=trust_scores_data.get("risk_containment", 0),
                auditability=trust_scores_data.get("auditability", 0),
            )
            errors.extend(trust_scores.validate())
        except Exception as e:
            errors.append(f"Invalid trust_scores: {str(e)}")
            trust_scores = TrustScores()

        # Parse AlignmentScores
        alignment_scores_data = decision_data.get("alignment_scores", {})
        try:
            alignment_scores = AlignmentScores(
                doctrine_alignment=alignment_scores_data.get("doctrine_alignment", 0.0),
                ethos_alignment=alignment_scores_data.get("ethos_alignment", 0.0),
                first_principles_alignment=alignment_scores_data.get("first_principles_alignment", 0.0),
                anti_pattern_flags=alignment_scores_data.get("anti_pattern_flags", []),
                applied_principles=alignment_scores_data.get("applied_principles", []),
            )
        except Exception as e:
            errors.append(f"Invalid alignment_scores: {str(e)}")
            alignment_scores = AlignmentScores()

        # Parse RTQLInput (optional)
        rtql_data = decision_data.get("rtql_input")
        rtql_input = None
        if rtql_data:
            try:
                rtql_scores_data = rtql_data.get("scores", {})
                rtql_scores = RTQLScores(
                    source_integrity=rtql_scores_data.get("source_integrity", 0),
                    exposure_count=rtql_scores_data.get("exposure_count", 0),
                    independence=rtql_scores_data.get("independence", 0),
                    explainability=rtql_scores_data.get("explainability", 0),
                    replicability=rtql_scores_data.get("replicability", 0),
                    adversarial_robustness=rtql_scores_data.get("adversarial_robustness", 0),
                    novelty_yield=rtql_scores_data.get("novelty_yield", 0),
                )

                causal_checks_data = rtql_data.get("causal_checks", {})
                causal_checks = CausalChecks(
                    reveals_causal_mechanism=causal_checks_data.get("reveals_causal_mechanism", False),
                    is_irreducible=causal_checks_data.get("is_irreducible", False),
                    survives_authority_removal=causal_checks_data.get("survives_authority_removal", False),
                    survives_context_shift=causal_checks_data.get("survives_context_shift", False),
                )

                rtql_input = RTQLInput(
                    claim=rtql_data.get("claim", ""),
                    source=rtql_data.get("source", ""),
                    is_identifiable=rtql_data.get("is_identifiable", False),
                    has_provenance=rtql_data.get("has_provenance", False),
                    scores=rtql_scores,
                    causal_checks=causal_checks,
                )
            except Exception as e:
                errors.append(f"Invalid rtql_input: {str(e)}")

        # Build DecisionObject
        decision = DecisionObject(
            decision_id=decision_id,
            title=title,
            decision_class=decision_class,
            owner=owner,
            time_horizon=time_horizon,
            reversibility=reversibility,
            problem_statement=problem_statement,
            requested_action=requested_action,
            context_summary=context_summary,
            stakeholders=stakeholders,
            constraints=constraints,
            value_scores=value_scores,
            trust_scores=trust_scores,
            alignment_scores=alignment_scores,
            rtql_input=rtql_input,
            evidence_refs=evidence_refs,
            assumptions=assumptions,
            unknowns=unknowns,
            required_approvals=required_approvals,
            execution_plan=execution_plan,
            monitoring_metric=monitoring_metric,
            rollback_trigger=rollback_trigger,
            review_date=review_date,
            current_state=current_state,
            actor_role=actor_role,
            has_missing_data=has_missing_data,
            ethical_conflict=ethical_conflict,
        )

        return decision, errors

    except Exception as e:
        return DecisionObject(), [f"Fatal conversion error: {str(e)}"]


# ─────────────────────────────────────────────
# DECISION OBJECT → PAYLOAD CONVERSION
# ─────────────────────────────────────────────

def decision_to_payload(decision: DecisionObject) -> Dict[str, Any]:
    """Convert DecisionObject back to flat JSON payload format."""
    return {
        "decision": {
            "decision_id": decision.decision_id,
            "title": decision.title,
            "decision_class": DECISION_CLASS_REVERSE[decision.decision_class],
            "owner": decision.owner,
            "time_horizon": TIME_HORIZON_REVERSE[decision.time_horizon],
            "reversibility": REVERSIBILITY_REVERSE[decision.reversibility],
            "problem_statement": decision.problem_statement,
            "requested_action": decision.requested_action,
            "context_summary": decision.context_summary,
            "stakeholders": decision.stakeholders,
            "constraints": decision.constraints,
            "value_scores": {
                "revenue_impact": decision.value_scores.revenue_impact,
                "cost_efficiency": decision.value_scores.cost_efficiency,
                "time_leverage": decision.value_scores.time_leverage,
                "strategic_alignment": decision.value_scores.strategic_alignment,
                "customer_human_benefit": decision.value_scores.customer_human_benefit,
                "knowledge_asset_creation": decision.value_scores.knowledge_asset_creation,
                "compounding_potential": decision.value_scores.compounding_potential,
                "reversibility": decision.value_scores.reversibility,
                "downside_risk": decision.value_scores.downside_risk,
                "execution_drag": decision.value_scores.execution_drag,
                "uncertainty": decision.value_scores.uncertainty,
                "ethical_misalignment": decision.value_scores.ethical_misalignment,
            },
            "trust_scores": {
                "evidence_quality": decision.trust_scores.evidence_quality,
                "logic_integrity": decision.trust_scores.logic_integrity,
                "outcome_history": decision.trust_scores.outcome_history,
                "context_fit": decision.trust_scores.context_fit,
                "stakeholder_clarity": decision.trust_scores.stakeholder_clarity,
                "risk_containment": decision.trust_scores.risk_containment,
                "auditability": decision.trust_scores.auditability,
            },
            "alignment_scores": {
                "doctrine_alignment": decision.alignment_scores.doctrine_alignment,
                "ethos_alignment": decision.alignment_scores.ethos_alignment,
                "first_principles_alignment": decision.alignment_scores.first_principles_alignment,
                "anti_pattern_flags": decision.alignment_scores.anti_pattern_flags,
                "applied_principles": decision.alignment_scores.applied_principles,
            },
            "evidence_refs": decision.evidence_refs,
            "assumptions": decision.assumptions,
            "unknowns": decision.unknowns,
            "required_approvals": decision.required_approvals,
            "execution_plan": decision.execution_plan,
            "monitoring_metric": decision.monitoring_metric,
            "rollback_trigger": decision.rollback_trigger,
            "review_date": decision.review_date,
            "current_state": decision.current_state,
            "actor_role": decision.actor_role,
            "has_missing_data": decision.has_missing_data,
            "ethical_conflict": decision.ethical_conflict,
        }
    }


# ─────────────────────────────────────────────
# PIPELINE RESULT → JSON CONVERSION
# ─────────────────────────────────────────────

def result_to_dict(result: PipelineResult) -> Dict[str, Any]:
    """Convert PipelineResult to JSON-serializable dict."""
    return serialize_pipeline_result(result)


def result_to_json(result: PipelineResult, indent: int = 2) -> str:
    """Serialize PipelineResult to formatted JSON string."""
    return json.dumps(result_to_dict(result), indent=indent)


# ─────────────────────────────────────────────
# FILE I/O HELPERS
# ─────────────────────────────────────────────

def load_payload_from_file(filepath: str) -> tuple[Dict[str, Any], Optional[str]]:
    """
    Load a JSON payload from file.

    Returns: (payload_dict, error_message)
    error_message is None if successful.
    """
    try:
        with open(filepath, 'r') as f:
            payload = json.load(f)
        return payload, None
    except json.JSONDecodeError as e:
        return {}, f"Invalid JSON: {str(e)}"
    except FileNotFoundError:
        return {}, f"File not found: {filepath}"
    except Exception as e:
        return {}, f"Error reading file: {str(e)}"


def save_payload_to_file(filepath: str, payload: Dict[str, Any]) -> Optional[str]:
    """
    Save a payload dict to JSON file.

    Returns: error_message (None if successful)
    """
    try:
        with open(filepath, 'w') as f:
            json.dump(payload, f, indent=2)
        return None
    except Exception as e:
        return f"Error writing file: {str(e)}"


def save_result_to_file(filepath: str, result: PipelineResult) -> Optional[str]:
    """
    Save a PipelineResult to JSON file.

    Returns: error_message (None if successful)
    """
    try:
        with open(filepath, 'w') as f:
            f.write(result_to_json(result, indent=2))
        return None
    except Exception as e:
        return f"Error writing file: {str(e)}"
