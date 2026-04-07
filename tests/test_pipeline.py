"""
Pipeline Integration Tests

Validates the full decision processing pipeline with key scenarios.
Run: python -m pytest tests/test_pipeline.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    ExecutionVerdict,
)
from engine.config import EngineConfig
from engine.pipeline import process_decision


def _make_d1_auto_execute():
    return DecisionObject(
        title="Deploy updated onboarding email template",
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        owner="marketing_ops",
        time_horizon=TimeHorizon.IMMEDIATE,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        problem_statement="Current onboarding email has 12% open rate",
        requested_action="Replace template with A/B tested winner",
        context_summary="A/B test showed 22% open rate",
        stakeholders=["marketing_ops", "customer_success"],
        evidence_refs=["ab_test_results.csv", "compliance_checklist.md"],
        execution_plan="Swap template, monitor 7 days",
        monitoring_metric="email_open_rate >= 18%",
        rollback_trigger="open_rate < 15% over 48hrs",
        review_date="2026-03-31",
        current_state="trust_certified",
        actor_role="AI_Domain_Agent",
        value_scores=ValueScores(
            revenue_impact=2, cost_efficiency=3, time_leverage=4,
            strategic_alignment=3, customer_human_benefit=3,
            knowledge_asset_creation=2, compounding_potential=2, reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=4, auditability=4,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.8, ethos_alignment=0.9,
            first_principles_alignment=0.7,
        ),
    )


def _make_d6_blocked():
    return DecisionObject(
        title="Acquire competitor for $2M",
        decision_class=DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST,
        owner="ceo",
        time_horizon=TimeHorizon.MID_TERM,
        reversibility=ReversibilityTag.R4_EFFECTIVELY_IRREVERSIBLE,
        problem_statement="Competitor has IP to accelerate roadmap",
        requested_action="Proceed with acquisition",
        context_summary="Preliminary DD, unaudited financials",
        stakeholders=["ceo", "cfo", "board"],
        evidence_refs=["preliminary_dd_report.pdf"],
        assumptions=["IP is defensible"],
        unknowns=["Full audit pending"],
        required_approvals=["ceo", "cfo", "board"],
        execution_plan="Complete DD, negotiate, board vote",
        monitoring_metric="integration_milestones",
        rollback_trigger="deal_breaker_in_dd",
        current_state="draft",
        actor_role="Human_CEO",
        value_scores=ValueScores(
            revenue_impact=4, cost_efficiency=2, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=3,
            knowledge_asset_creation=4, compounding_potential=5, reversibility=0,
            downside_risk=5, execution_drag=4, uncertainty=5, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=2, logic_integrity=3, outcome_history=1,
            context_fit=3, stakeholder_clarity=3, risk_containment=1, auditability=2,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.7, ethos_alignment=0.6,
            first_principles_alignment=0.5,
        ),
    )


def _make_needs_data():
    return DecisionObject(
        title="Automate weekly client-status digest",
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        owner="ops_manager",
        problem_statement="Manual weekly digest takes 4hrs",
        requested_action="Deploy automated digest pipeline",
        stakeholders=["ops_manager"],
        evidence_refs=["pilot_results_v1.csv"],
        monitoring_metric="digest_delivery_rate >= 99%",
        rollback_trigger="delivery_failures > 3 in 24hrs",
        current_state="draft",
        actor_role="AI_Domain_Agent",
        has_missing_data=True,
        value_scores=ValueScores(
            revenue_impact=2, cost_efficiency=4, time_leverage=5,
            strategic_alignment=4, customer_human_benefit=3,
            knowledge_asset_creation=3, compounding_potential=4, reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=4, auditability=5,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.9,
            first_principles_alignment=0.8,
        ),
    )


def test_d1_auto_execute():
    config = EngineConfig()
    decision = _make_d1_auto_execute()
    result = process_decision(decision, config)
    assert result.success
    assert result.execution_packet is not None
    assert result.execution_packet.verdict == ExecutionVerdict.AUTO_EXECUTE


def test_d6_blocked():
    config = EngineConfig()
    decision = _make_d6_blocked()
    result = process_decision(decision, config)
    assert result.success
    assert result.execution_packet is not None
    assert result.execution_packet.verdict == ExecutionVerdict.BLOCK


def test_needs_data():
    config = EngineConfig()
    decision = _make_needs_data()
    result = process_decision(decision, config)
    assert result.success
    assert result.execution_packet is not None
    assert result.execution_packet.verdict == ExecutionVerdict.NEEDS_DATA


def test_pipeline_produces_audit_trail():
    config = EngineConfig()
    decision = _make_d1_auto_execute()
    result = process_decision(decision, config)
    assert len(result.audit_trail) > 0


def test_pipeline_produces_executive_summary():
    config = EngineConfig()
    decision = _make_d1_auto_execute()
    result = process_decision(decision, config)
    assert result.executive_summary
    assert "VERDICT" in result.executive_summary


def test_certificate_chain_for_auto_execute():
    config = EngineConfig()
    decision = _make_d1_auto_execute()
    result = process_decision(decision, config)
    assert result.certificate_chain is not None
    assert result.certificate_chain.chain_complete()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
