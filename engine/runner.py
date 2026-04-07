"""
Engine Runner — End-to-End Pipeline Test Suite

Demonstrates the full decision processing pipeline with 5 test scenarios:

1. D1 Auto-Execute: Low-risk tactical decision → auto-execute
2. D3 Financial Escalation: Financial decision → escalate tier 2
3. D6 Blocked: High-blast-radius with weak trust → block
4. RTQL-Degraded: Decision with low RTQL trust → degraded processing
5. Needs-Data: Decision with missing data flag → needs_data verdict

Run: python -m engine.runner
"""

import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks,
)
from engine.config import EngineConfig
from engine.pipeline import process_decision
from engine.audit import result_to_json


def separator(title: str):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}\n")


# ─────────────────────────────────────────────
# SCENARIO 1: D1 Auto-Execute
# ─────────────────────────────────────────────

def scenario_1_d1_auto_execute(config):
    separator("SCENARIO 1: D1 Reversible Tactical → Auto-Execute")

    decision = DecisionObject(
        title="Deploy updated onboarding email template",
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        owner="marketing_ops",
        time_horizon=TimeHorizon.IMMEDIATE,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        problem_statement="Current onboarding email has 12% open rate, below 18% benchmark",
        requested_action="Replace current template with A/B tested winner",
        context_summary="A/B test over 2 weeks showed new template at 22% open rate",
        stakeholders=["marketing_ops", "customer_success"],
        constraints=["Must maintain CAN-SPAM compliance"],
        evidence_refs=["ab_test_results_q1_2026.csv", "email_compliance_checklist.md"],
        assumptions=["Open rate improvement will sustain post-deployment"],
        unknowns=["Long-term click-through impact unclear"],
        execution_plan="Swap template in email platform, monitor for 7 days",
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
            applied_principles=["Speed matters when opportunity decays",
                                "Evidence quality determines decision quality ceiling"],
        ),
        rtql_input=RTQLInput(
            claim="New email template outperforms current by 83%",
            source="Internal A/B test platform",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(
                source_integrity=8, exposure_count=5, independence=6,
                explainability=8, replicability=6, adversarial_robustness=6,
                novelty_yield=3,
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=False, is_irreducible=False,
                survives_authority_removal=True, survives_context_shift=False,
            ),
        ),
    )

    result = process_decision(decision, config)
    print(result.executive_summary)
    print("\n--- Full JSON Output ---")
    print(result_to_json(result))
    return result


# ─────────────────────────────────────────────
# SCENARIO 2: D3 Financial Escalation
# ─────────────────────────────────────────────

def scenario_2_d3_financial_escalate(config):
    separator("SCENARIO 2: D3 Financial → Escalate Tier 2")

    decision = DecisionObject(
        title="Increase SaaS platform annual spend by $50K for AI tooling",
        decision_class=DecisionClass.D3_FINANCIAL,
        owner="vp_engineering",
        time_horizon=TimeHorizon.NEAR_TERM,
        reversibility=ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        problem_statement="Engineering team losing 15hrs/week to manual tasks automatable by AI",
        requested_action="Approve $50K annual spend for AI coding assistant licenses",
        context_summary="Pilot with 5 engineers showed 30% productivity gain over 4 weeks",
        stakeholders=["vp_engineering", "cfo", "engineering_team"],
        constraints=["Annual budget cap of $200K remaining", "SOC2 compliance required"],
        evidence_refs=["pilot_results_2026q1.pdf", "vendor_soc2_cert.pdf", "engineering_time_audit.xlsx"],
        assumptions=["Pilot productivity gains extrapolate to full team", "Vendor maintains SOC2 compliance"],
        unknowns=["Actual ROI at scale vs pilot"],
        required_approvals=["cfo", "vp_engineering"],
        execution_plan="Sign 1-year agreement, roll out in 2 phases over 30 days",
        monitoring_metric="engineering_velocity_improvement >= 20%",
        rollback_trigger="velocity_improvement < 10% after 60 days",
        review_date="2026-05-24",
        current_state="value_confirmed",
        actor_role="Domain_Owner",
        value_scores=ValueScores(
            revenue_impact=3, cost_efficiency=4, time_leverage=4,
            strategic_alignment=4, customer_human_benefit=2,
            knowledge_asset_creation=3, compounding_potential=4, reversibility=3,
            downside_risk=2, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=3, auditability=4,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.85,
            first_principles_alignment=0.8,
            applied_principles=["All resources are finite",
                                "Compounding dominates isolated wins",
                                "Trust is earned through repeated validated outcomes"],
        ),
    )

    result = process_decision(decision, config)
    print(result.executive_summary)
    print("\n--- Full JSON Output ---")
    print(result_to_json(result))
    return result


# ─────────────────────────────────────────────
# SCENARIO 3: D6 Blocked
# ─────────────────────────────────────────────

def scenario_3_d6_blocked(config):
    separator("SCENARIO 3: D6 Irreversible/High Blast → Block")

    decision = DecisionObject(
        title="Acquire competitor startup for $2M",
        decision_class=DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST,
        owner="ceo",
        time_horizon=TimeHorizon.MID_TERM,
        reversibility=ReversibilityTag.R4_EFFECTIVELY_IRREVERSIBLE,
        problem_statement="Competitor has IP that would accelerate product roadmap by 18 months",
        requested_action="Proceed with acquisition at $2M valuation",
        context_summary="Initial due diligence shows promising tech stack but unaudited financials",
        stakeholders=["ceo", "cfo", "board", "legal"],
        constraints=["Cash reserves limited to $5M", "Board approval required"],
        evidence_refs=["preliminary_dd_report.pdf"],
        assumptions=["Competitor IP is defensible", "Key talent will retain post-acquisition"],
        unknowns=["Full financial audit pending", "Retention risk of key engineers", "IP encumbrance status"],
        required_approvals=["ceo", "cfo", "board"],
        execution_plan="Complete due diligence, negotiate terms, board vote",
        monitoring_metric="integration_milestones_on_track",
        rollback_trigger="deal_breaker_in_due_diligence",
        review_date="2026-06-30",
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
            applied_principles=["Risk is asymmetrical", "The map is not the territory",
                                "Evidence quality determines decision quality ceiling"],
        ),
    )

    result = process_decision(decision, config)
    print(result.executive_summary)
    print("\n--- Full JSON Output ---")
    print(result_to_json(result))
    return result


# ─────────────────────────────────────────────
# SCENARIO 4: RTQL-Degraded Processing
# ─────────────────────────────────────────────

def scenario_4_rtql_degraded(config):
    separator("SCENARIO 4: RTQL Weak Signal → Degraded Processing")

    decision = DecisionObject(
        title="Pivot marketing strategy to TikTok-first based on trend report",
        decision_class=DecisionClass.D2_OPERATIONAL,
        owner="head_of_marketing",
        time_horizon=TimeHorizon.NEAR_TERM,
        reversibility=ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        problem_statement="Industry report suggests audience migrating to TikTok",
        requested_action="Reallocate 40% of social budget from LinkedIn to TikTok",
        context_summary="Single analyst report with no internal validation",
        stakeholders=["head_of_marketing", "cmo", "social_team"],
        constraints=["Quarterly budget already committed"],
        evidence_refs=["analyst_report_tiktok_2026.pdf"],
        assumptions=["Report accurately reflects our ICP behavior"],
        unknowns=["Whether our B2B audience is actually on TikTok"],
        execution_plan="Pilot 2-week TikTok campaign with 10% of budget first",
        monitoring_metric="tiktok_engagement_rate >= linkedin_baseline",
        rollback_trigger="engagement_rate < 50% of linkedin_baseline after 14 days",
        review_date="2026-04-07",
        current_state="draft",
        actor_role="Domain_Owner",
        value_scores=ValueScores(
            revenue_impact=3, cost_efficiency=2, time_leverage=3,
            strategic_alignment=3, customer_human_benefit=2,
            knowledge_asset_creation=2, compounding_potential=3, reversibility=3,
            downside_risk=2, execution_drag=2, uncertainty=4, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=2, logic_integrity=3, outcome_history=1,
            context_fit=2, stakeholder_clarity=3, risk_containment=3, auditability=3,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.6, ethos_alignment=0.7,
            first_principles_alignment=0.5,
            applied_principles=["Reality before preference", "The map is not the territory"],
        ),
        rtql_input=RTQLInput(
            claim="B2B audiences are migrating to TikTok",
            source="External analyst report (single source)",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(
                source_integrity=3, exposure_count=1, independence=2,
                explainability=4, replicability=2, adversarial_robustness=2,
                novelty_yield=4,
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=False, is_irreducible=False,
                survives_authority_removal=False, survives_context_shift=False,
            ),
        ),
    )

    result = process_decision(decision, config)
    print(result.executive_summary)
    print("\n--- Full JSON Output ---")
    print(result_to_json(result))
    return result


# ─────────────────────────────────────────────
# SCENARIO 5: Needs Data
# ─────────────────────────────────────────────

def scenario_5_needs_data(config):
    separator("SCENARIO 5: Missing Data → Needs Data")

    decision = DecisionObject(
        title="Automate weekly client-status digest",
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        owner="ops_manager",
        time_horizon=TimeHorizon.IMMEDIATE,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        problem_statement="Manual weekly digest takes 4hrs and is error-prone",
        requested_action="Deploy automated digest pipeline",
        context_summary="Pilot showed 90% time savings but ROI data incomplete",
        stakeholders=["ops_manager", "client_success"],
        constraints=["Must integrate with existing CRM"],
        evidence_refs=["pilot_results_v1.csv"],
        assumptions=["Pilot results extrapolate"],
        unknowns=["Integration complexity unknown", "Client satisfaction impact unknown"],
        execution_plan="Deploy to staging, validate, promote to production",
        monitoring_metric="digest_delivery_rate >= 99%",
        rollback_trigger="delivery_failures > 3 in 24hrs",
        review_date="2026-04-01",
        current_state="draft",
        actor_role="AI_Domain_Agent",
        has_missing_data=True,  # Key flag
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

    result = process_decision(decision, config)
    print(result.executive_summary)
    print("\n--- Full JSON Output ---")
    print(result_to_json(result))
    return result


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  EXECUTIVE DECISION ENGINE — Core Processing Pipeline Test Suite")
    print("  Version 1.0.0")
    print("=" * 72)

    config = EngineConfig()  # Use defaults (or load_config() for YAML)

    results = {}

    r1 = scenario_1_d1_auto_execute(config)
    results["scenario_1_d1_auto"] = r1.execution_packet.verdict.value if r1.execution_packet else "N/A"

    r2 = scenario_2_d3_financial_escalate(config)
    results["scenario_2_d3_escalate"] = r2.execution_packet.verdict.value if r2.execution_packet else "N/A"

    r3 = scenario_3_d6_blocked(config)
    results["scenario_3_d6_blocked"] = r3.execution_packet.verdict.value if r3.execution_packet else "N/A"

    r4 = scenario_4_rtql_degraded(config)
    results["scenario_4_rtql_degraded"] = r4.execution_packet.verdict.value if r4.execution_packet else "N/A"

    r5 = scenario_5_needs_data(config)
    results["scenario_5_needs_data"] = r5.execution_packet.verdict.value if r5.execution_packet else "N/A"

    separator("RESULTS SUMMARY")
    for name, verdict in results.items():
        print(f"  {name}: {verdict}")

    print(f"\n{'─'*40}")
    print("  EXPECTED vs ACTUAL")
    print(f"{'─'*40}")

    expectations = {
        "scenario_1_d1_auto": "auto_execute",
        "scenario_2_d3_escalate": "escalate_tier_2",
        "scenario_3_d6_blocked": "block",
        "scenario_4_rtql_degraded": "escalate_tier_1",
        "scenario_5_needs_data": "needs_data",
    }

    all_pass = True
    for name, expected in expectations.items():
        actual = results[name]
        status = "PASS" if actual == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status}: {name} — expected '{expected}', got '{actual}'")

    print(f"\n  {'ALL SCENARIOS PASSED' if all_pass else 'SOME SCENARIOS FAILED'}")
    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
