"""
loaders/sales_os_backlog.py
===========================
Converts the Sales Operating System implementation backlog into DecisionObjects,
runs each through the intelligence pipeline, and outputs a priority-ranked report.

Usage:
    python intelligence-engine/loaders/sales_os_backlog.py

Output:
    intelligence-engine/data/generated/sales_os_priority_report.md
"""

import sys
import os
from pathlib import Path
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks,
)
from orchestrator.orchestrator import IntelligenceOrchestrator

DB_PATH      = os.path.join(ROOT, "data", "intelligence.db")
ENGINE_YAML  = os.path.join(ROOT, "engine.yaml")
GENERATED    = os.path.join(ROOT, "data", "generated")


# ─────────────────────────────────────────────────────────────────────────────
# BACKLOG DEFINITIONS
# Each item maps directly from 08_IMPLEMENTATION_BACKLOG.md.
# Scoring rationale is annotated inline.
# ─────────────────────────────────────────────────────────────────────────────

BACKLOG = [

    # ── SPRINT 1 ─────────────────────────────────────────────────────────────

    {
        "title": "Monorepo scaffold",
        "sprint": 1,
        "description": "Initialize Python/React/SQLite monorepo with FastAPI, Vite, Tailwind, shared tooling.",
        "rationale": (
            "Zero-value on its own but unblocks everything. "
            "High reversibility — scaffold can be restructured cheaply early. "
            "No revenue until paired with working features."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.IMMEDIATE,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=1, cost_efficiency=4, time_leverage=5,
            strategic_alignment=3, customer_human_benefit=1,
            knowledge_asset_creation=2, compounding_potential=4,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=5,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Monorepo scaffold is prerequisite to all Sprint 1-6 delivery.",
            source="Architecture spec 02_SYSTEM_ARCHITECTURE.md",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=6, independence=8,
                              explainability=10, replicability=10, adversarial_robustness=8, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "SQLite schema",
        "sprint": 1,
        "description": "Implement full data model: Product, Service, Bundle, NeedState, Client, Opportunity, Recommendation, WorkflowRun, AgentTemplate, PromptProfile.",
        "rationale": (
            "Foundational — every feature reads/writes this schema. "
            "Bad schema now = expensive migration later. "
            "High compounding: gets reused by every sprint."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.IMMEDIATE,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=2, cost_efficiency=4, time_leverage=5,
            strategic_alignment=4, customer_human_benefit=2,
            knowledge_asset_creation=4, compounding_potential=5,
            reversibility=3,
            downside_risk=2, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=4, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.85,
        ),
        "rtql": RTQLInput(
            claim="Schema derived directly from PRD key entities and data model spec.",
            source="01_PRODUCT_REQUIREMENTS.md, 03_DATA_MODEL_SQLITE_GOOGLE.md",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=6, independence=8,
                              explainability=9, replicability=9, adversarial_robustness=7, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Seed data import from spreadsheet",
        "sprint": 1,
        "description": "Parse existing sales catalog spreadsheet and load into SQLite — products, services, bundles, pricing metadata, scoring attributes.",
        "rationale": (
            "Unlocks real data for every downstream feature. "
            "Without it, catalog CRUD and recommendation engine are hollow. "
            "Spreadsheet is the source of truth today — capturing it is step 1."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.IMMEDIATE,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=3, cost_efficiency=3, time_leverage=4,
            strategic_alignment=4, customer_human_benefit=3,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=4, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Spreadsheet exists today and is the operational catalog — import is a known transformation.",
            source="PRD FR-1 Master Catalog, Definition of Done item 1",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=5, independence=7,
                              explainability=9, replicability=9, adversarial_robustness=8, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Catalog CRUD",
        "sprint": 1,
        "description": "API + React UI to create, read, update, delete products, services, assets, bundles, channels, deliverables.",
        "rationale": (
            "The operational heart of the system. "
            "Sales team can't use any output if the catalog can't be maintained. "
            "Straightforward to build once schema exists."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.IMMEDIATE,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=3, cost_efficiency=3, time_leverage=3,
            strategic_alignment=4, customer_human_benefit=4,
            knowledge_asset_creation=3, compounding_potential=4,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=5,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="CRUD is table stakes for any data platform — low uncertainty, high precedent.",
            source="PRD FR-1, standard web app pattern",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=8, independence=9,
                              explainability=10, replicability=10, adversarial_robustness=9, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Bundles CRUD",
        "sprint": 1,
        "description": "API + React UI to create and manage product/service bundles with dependency rules, pricing metadata, and scoring attributes.",
        "rationale": (
            "Bundles are the primary revenue mechanism — upsell/cross-sell logic depends on them. "
            "Closely related to catalog CRUD but distinct entity with dependency rules. "
            "Needed before recommendation engine can produce meaningful output."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.IMMEDIATE,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=4, cost_efficiency=3, time_leverage=3,
            strategic_alignment=5, customer_human_benefit=4,
            knowledge_asset_creation=3, compounding_potential=5,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.95, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Bundles are the core revenue product structure — required by FR-2 and FR-3.",
            source="PRD FR-2 Client Need Mapping, FR-3 Recommendation Engine",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=7, independence=8,
                              explainability=9, replicability=9, adversarial_robustness=8, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    # ── SPRINT 2 ─────────────────────────────────────────────────────────────

    {
        "title": "Opportunities and clients",
        "sprint": 2,
        "description": "Client and Opportunity entities with CRUD, relationship mapping, status tracking, and basic pipeline view.",
        "rationale": (
            "The demand side of the system. "
            "Without clients and opportunities, recommendation engine has no context to work against. "
            "Required before need-state mapping is meaningful."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=4, cost_efficiency=3, time_leverage=4,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=3, compounding_potential=5,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=5,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Client + opportunity data is the input to the recommendation engine — required by PRD FR-2.",
            source="PRD FR-2 Client Need Mapping, key entity list",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=7, independence=8,
                              explainability=9, replicability=9, adversarial_robustness=8, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Need-state mapping",
        "sprint": 2,
        "description": "Map client symptoms and stated needs to NeedState entities. Build the symptom → product/bundle routing logic.",
        "rationale": (
            "The intelligence layer for demand. "
            "This is what separates a catalog from a sales engine. "
            "High compounding — every recommendation downstream uses this mapping."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=4, cost_efficiency=3, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=3,
            downside_risk=2, execution_drag=2, uncertainty=3, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=5, stakeholder_clarity=4, risk_containment=4, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.9, first_principles_alignment=0.85,
        ),
        "rtql": RTQLInput(
            claim="Need-state mapping is the core IP of the Sales OS — differentiates it from simple CRUD.",
            source="PRD FR-2, success metric: 90% of client records have recommended next action",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=5, independence=6,
                              explainability=7, replicability=6, adversarial_robustness=6, novelty_yield=4),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Recommendation engine",
        "sprint": 2,
        "description": "Rules-based engine that generates ranked upsell/cross-sell/bundle recommendations from client opportunity context and need-state mappings.",
        "rationale": (
            "The primary value generator. "
            "Success metric: 80% reduction in time to produce upsell path. "
            "Rules-based first — avoids premature ML complexity. "
            "Directly tied to revenue outcomes."
        ),
        "decision_class": DecisionClass.D3_FINANCIAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=5, cost_efficiency=4, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=4, compounding_potential=5,
            reversibility=3,
            downside_risk=2, execution_drag=2, uncertainty=3, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=5, stakeholder_clarity=4, risk_containment=4, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Rules-based recommendation engine directly drives 80% upsell time reduction success metric.",
            source="PRD FR-3, success metrics section",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=6, independence=7,
                              explainability=8, replicability=7, adversarial_robustness=7, novelty_yield=3),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Dashboard summaries",
        "sprint": 2,
        "description": "React dashboard with pipeline overview, recommendation queue, client health, and key metrics.",
        "rationale": (
            "Operationalizes everything built so far. "
            "Without visibility, users can't act on recommendations. "
            "Important but derivative — value depends on Sprint 1 and upstream Sprint 2 items."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=3, cost_efficiency=2, time_leverage=3,
            strategic_alignment=3, customer_human_benefit=4,
            knowledge_asset_creation=2, compounding_potential=3,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=4,
            context_fit=4, stakeholder_clarity=4, risk_containment=5, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.8, ethos_alignment=0.8, first_principles_alignment=0.75,
        ),
        "rtql": RTQLInput(
            claim="Dashboard is user-facing layer required for the system to be operationally useful.",
            source="PRD primary users, MVP scope",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=6, independence=7,
                              explainability=9, replicability=8, adversarial_robustness=7, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=False, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    # ── SPRINT 3 ─────────────────────────────────────────────────────────────

    {
        "title": "Google OAuth",
        "sprint": 3,
        "description": "Implement Google OAuth 2.0 — user authentication, token refresh, credential storage.",
        "rationale": (
            "Gate for all Google integrations. "
            "Without OAuth, Sheets/Docs/Gmail are unavailable. "
            "Well-documented, low uncertainty. "
            "Required before any G-Suite workflow is valuable to users."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=2, cost_efficiency=3, time_leverage=4,
            strategic_alignment=4, customer_human_benefit=3,
            knowledge_asset_creation=2, compounding_potential=4,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=5,
            context_fit=5, stakeholder_clarity=5, risk_containment=4, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.9, first_principles_alignment=0.85,
        ),
        "rtql": RTQLInput(
            claim="Google OAuth is a well-understood integration pattern with published SDKs.",
            source="PRD FR-6, google-auth library",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=8, independence=9,
                              explainability=10, replicability=10, adversarial_robustness=9, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Sheets import/export",
        "sprint": 3,
        "description": "Bidirectional Google Sheets sync — read catalog/client data from Sheets, write recommendations and reports back.",
        "rationale": (
            "Primary integration request in PRD. "
            "Enables non-technical users to operate the system through familiar interfaces. "
            "Depends on OAuth. Moderate complexity."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=3, cost_efficiency=4, time_leverage=4,
            strategic_alignment=4, customer_human_benefit=5,
            knowledge_asset_creation=3, compounding_potential=4,
            reversibility=4,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=4, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=4, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.9, first_principles_alignment=0.8,
        ),
        "rtql": RTQLInput(
            claim="Sheets sync is an explicit PRD requirement and key to user adoption.",
            source="PRD FR-6, Definition of Done item 4",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=6, independence=7,
                              explainability=8, replicability=8, adversarial_robustness=7, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Docs artifact generation",
        "sprint": 3,
        "description": "Generate Google Docs outputs — proposals, scopes, checklists, content calendars — from Jinja2 templates.",
        "rationale": (
            "Directly drives 70% proposal time reduction success metric. "
            "High user-visible value. "
            "Depends on catalog + recommendations data being clean."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.NEAR_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=4, cost_efficiency=5, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=4, compounding_potential=4,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Proposal generation directly achieves the 70% time reduction success metric in PRD.",
            source="PRD success metrics, FR-4 Workflow Execution",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=5, independence=6,
                              explainability=8, replicability=8, adversarial_robustness=7, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Gmail draft support",
        "sprint": 3,
        "description": "Generate Gmail drafts for follow-ups, outreach, and nurture sequences from templates.",
        "rationale": (
            "Useful but not on the critical path to MVP definition of done. "
            "Depends on OAuth and artifact generation being stable. "
            "Lower urgency than Docs — email is more asynchronous."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=2, cost_efficiency=3, time_leverage=3,
            strategic_alignment=3, customer_human_benefit=3,
            knowledge_asset_creation=2, compounding_potential=3,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=4,
            context_fit=3, stakeholder_clarity=3, risk_containment=4, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.7, ethos_alignment=0.8, first_principles_alignment=0.7,
        ),
        "rtql": RTQLInput(
            claim="Gmail drafts are a convenience feature — value is real but not MVP-critical.",
            source="PRD FR-6 Google Services (optional), FR-4 follow-up builder",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=5, independence=6,
                              explainability=8, replicability=8, adversarial_robustness=7, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=False, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=False),
        ),
    },

    # ── SPRINT 4 ─────────────────────────────────────────────────────────────

    {
        "title": "Agent runtime",
        "sprint": 4,
        "description": "Python-based agent orchestration layer — spawn, manage, and monitor task-specific agents (proposal, deck, outreach, qualification, CRM sync).",
        "rationale": (
            "Definition of Done requires 3 deployed agent templates. "
            "High strategic leverage — once runtime exists, agents are additive. "
            "More complex than Sprint 1-3 items; higher execution drag."
        ),
        "decision_class": DecisionClass.D3_FINANCIAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=4, cost_efficiency=4, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=4,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=3,
            downside_risk=2, execution_drag=4, uncertainty=3, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=5, stakeholder_clarity=4, risk_containment=3, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.85, first_principles_alignment=0.85,
        ),
        "rtql": RTQLInput(
            claim="Agent runtime is a structural requirement per PRD FR-5 and Definition of Done.",
            source="PRD FR-5 Agent Runtime, Definition of Done item 3",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=4, independence=5,
                              explainability=7, replicability=6, adversarial_robustness=6, novelty_yield=4),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Agent template management",
        "sprint": 4,
        "description": "UI and API for creating, versioning, and managing agent templates — prompt profiles, tool policies, retrieval packs.",
        "rationale": (
            "Makes the runtime useful by operators rather than just developers. "
            "Depends on agent runtime existing. "
            "High compounding: each new template multiplies agent capability."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=3, cost_efficiency=3, time_leverage=4,
            strategic_alignment=4, customer_human_benefit=3,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=3,
            downside_risk=2, execution_drag=3, uncertainty=3, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=4, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.85, first_principles_alignment=0.8,
        ),
        "rtql": RTQLInput(
            claim="Template management enables operator-level agent customization per PRD FR-7.",
            source="PRD FR-7 Small Model Pipeline, FR-5",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=4, independence=5,
                              explainability=7, replicability=6, adversarial_robustness=6, novelty_yield=3),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Workflow runner",
        "sprint": 4,
        "description": "Execute multi-step workflows — build proposal, build deck, launch nurture, generate follow-up — as orchestrated sequences of agent calls and artifact outputs.",
        "rationale": (
            "Ties agents + artifacts + client data into end-to-end execution. "
            "This is the operational leverage the PRD is built around. "
            "High execution drag — requires runtime and template management to be stable first."
        ),
        "decision_class": DecisionClass.D3_FINANCIAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=5, cost_efficiency=5, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=4, compounding_potential=5,
            reversibility=3,
            downside_risk=3, execution_drag=4, uncertainty=3, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=5, stakeholder_clarity=4, risk_containment=3, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Workflow runner delivers the 70% proposal + 80% upsell time reduction success metrics.",
            source="PRD FR-4 Workflow Execution, success metrics",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=4, independence=5,
                              explainability=8, replicability=6, adversarial_robustness=6, novelty_yield=3),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Execution history",
        "sprint": 4,
        "description": "Log all workflow runs, agent calls, artifact outputs, and recommendations with timestamps, inputs, outputs, and status.",
        "rationale": (
            "Required for audit, debugging, and model evaluation. "
            "Also enables the SLM evaluation pipeline in Sprint 6. "
            "Low risk, high future leverage."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=1, cost_efficiency=3, time_leverage=2,
            strategic_alignment=4, customer_human_benefit=2,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=5,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Execution logging is required by PRD non-functional requirements and Definition of Done item 5.",
            source="PRD non-functional requirements, Definition of Done",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=7, independence=8,
                              explainability=10, replicability=10, adversarial_robustness=9, novelty_yield=1),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    # ── SPRINT 5 ─────────────────────────────────────────────────────────────

    {
        "title": "Proposal builder",
        "sprint": 5,
        "description": "Dedicated agent + UI for generating fully formatted client proposals from opportunity context, catalog items, and recommended bundles.",
        "rationale": (
            "Most visible user-facing output. "
            "Directly tied to 70% time reduction success metric. "
            "Depends on workflow runner and artifact generation being stable."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=5, cost_efficiency=5, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=3, compounding_potential=4,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Proposal builder is the primary revenue-generating output of the system.",
            source="PRD success metric: 70% proposal time reduction, FR-4",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=6, independence=7,
                              explainability=9, replicability=8, adversarial_robustness=8, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Deck builder",
        "sprint": 5,
        "description": "Generate sales deck slides/outlines from proposal content and product positioning data.",
        "rationale": (
            "High user value — decks are a core sales deliverable. "
            "Can be partially built as Docs export initially. "
            "Lower urgency than proposal builder."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=3, cost_efficiency=4, time_leverage=4,
            strategic_alignment=4, customer_human_benefit=4,
            knowledge_asset_creation=3, compounding_potential=3,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=5, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.8, ethos_alignment=0.85, first_principles_alignment=0.8,
        ),
        "rtql": RTQLInput(
            claim="Deck builder is a secondary deliverable type after proposals.",
            source="PRD FR-4 Workflow Execution",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=5, independence=6,
                              explainability=8, replicability=7, adversarial_robustness=7, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=False, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Follow-up builder",
        "sprint": 5,
        "description": "Auto-generate client follow-up summaries, next-step emails, and action item lists from workflow run data.",
        "rationale": (
            "Reduces repetitive post-meeting work. "
            "Meaningful time leverage for account managers. "
            "Lower strategic weight than proposal or deck."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=2, cost_efficiency=4, time_leverage=4,
            strategic_alignment=3, customer_human_benefit=4,
            knowledge_asset_creation=2, compounding_potential=3,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=5, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.8, ethos_alignment=0.85, first_principles_alignment=0.75,
        ),
        "rtql": RTQLInput(
            claim="Follow-up automation reduces repetitive work per PRD FR-4.",
            source="PRD FR-4 generate follow-up summary",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=5, independence=6,
                              explainability=8, replicability=8, adversarial_robustness=7, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=False, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Bundle recommendation UI",
        "sprint": 5,
        "description": "Dedicated UI surface for reviewing and acting on bundle recommendations — comparison view, one-click proposal generation, acceptance tracking.",
        "rationale": (
            "Makes the recommendation engine actionable in the UI. "
            "Recommendation acceptance rate is a success metric. "
            "Depends on recommendation engine and proposal builder."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=4, cost_efficiency=3, time_leverage=4,
            strategic_alignment=5, customer_human_benefit=5,
            knowledge_asset_creation=3, compounding_potential=4,
            reversibility=5,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=5, stakeholder_clarity=4, risk_containment=5, auditability=4,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.9, first_principles_alignment=0.85,
        ),
        "rtql": RTQLInput(
            claim="Bundle recommendation UI drives acceptance rate metric — the revenue conversion surface.",
            source="PRD success metric: recommendation acceptance rate, FR-3",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=5, independence=6,
                              explainability=8, replicability=7, adversarial_robustness=7, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    # ── SPRINT 6 ─────────────────────────────────────────────────────────────

    {
        "title": "Evaluation logging",
        "sprint": 6,
        "description": "Capture task evaluation traces — inputs, outputs, scores, human ratings — for every agent call and recommendation.",
        "rationale": (
            "Enables the SLM fine-tune pipeline. "
            "Builds the dataset that makes agents better over time. "
            "High compounding but delayed payoff — value increases with volume."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=2, cost_efficiency=3, time_leverage=2,
            strategic_alignment=5, customer_human_benefit=2,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=5, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Evaluation logging is required to build the SLM fine-tune dataset per PRD FR-7.",
            source="PRD FR-7 Small Model Pipeline, post-MVP evaluation system",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=9, exposure_count=4, independence=6,
                              explainability=8, replicability=8, adversarial_robustness=7, novelty_yield=3),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Dataset export",
        "sprint": 6,
        "description": "Export evaluation traces and operational logs as structured datasets for fine-tuning or analysis.",
        "rationale": (
            "Enables the distillation pipeline. "
            "Low effort once evaluation logging is in place. "
            "High strategic value for long-term model specialization."
        ),
        "decision_class": DecisionClass.D1_REVERSIBLE_TACTICAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R1_EASILY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=1, cost_efficiency=3, time_leverage=2,
            strategic_alignment=5, customer_human_benefit=1,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.9, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Dataset export unlocks fine-tune pipeline — strategic but not MVP-critical.",
            source="PRD post-MVP scope: lightweight fine-tune pipeline",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=4, independence=6,
                              explainability=8, replicability=8, adversarial_robustness=7, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Prompt profile versioning",
        "sprint": 6,
        "description": "Version control for prompt profiles — track changes, compare performance, roll back to prior versions.",
        "rationale": (
            "Required for systematic agent improvement. "
            "Without versioning, prompt changes are unaudited and irreversible in practice. "
            "Moderate complexity. High long-term leverage."
        ),
        "decision_class": DecisionClass.D2_OPERATIONAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=1, cost_efficiency=3, time_leverage=3,
            strategic_alignment=4, customer_human_benefit=2,
            knowledge_asset_creation=5, compounding_potential=5,
            reversibility=4,
            downside_risk=1, execution_drag=2, uncertainty=2, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=4, logic_integrity=5, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=4, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.85, ethos_alignment=0.9, first_principles_alignment=0.85,
        ),
        "rtql": RTQLInput(
            claim="Prompt versioning is required for auditable agent behavior per PRD non-functional requirements.",
            source="PRD non-functional: clear auditability, FR-7",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=8, exposure_count=4, independence=6,
                              explainability=8, replicability=7, adversarial_robustness=7, novelty_yield=3),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=False,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },

    {
        "title": "Approval system hardening",
        "sprint": 6,
        "description": "Role-based access control, human-in-the-loop approval gates for agent actions, execution guardrails.",
        "rationale": (
            "Risk management for agent autonomy. "
            "PRD explicitly flags over-automation without review as a top risk. "
            "Must be in place before increasing agent autonomy. "
            "Not glamorous but critical for production safety."
        ),
        "decision_class": DecisionClass.D3_FINANCIAL,
        "time_horizon": TimeHorizon.MID_TERM,
        "reversibility": ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        "value": ValueScores(
            revenue_impact=1, cost_efficiency=2, time_leverage=2,
            strategic_alignment=5, customer_human_benefit=3,
            knowledge_asset_creation=3, compounding_potential=4,
            reversibility=3,
            downside_risk=1, execution_drag=2, uncertainty=1, ethical_misalignment=0,
        ),
        "trust": TrustScores(
            evidence_quality=5, logic_integrity=5, outcome_history=4,
            context_fit=5, stakeholder_clarity=5, risk_containment=5, auditability=5,
        ),
        "alignment": AlignmentScores(
            doctrine_alignment=0.9, ethos_alignment=0.95, first_principles_alignment=0.9,
        ),
        "rtql": RTQLInput(
            claim="Approval hardening mitigates PRD's top-listed risk: over-automation without review.",
            source="PRD risks section, non-functional: role-based access control",
            is_identifiable=True, has_provenance=True,
            scores=RTQLScores(source_integrity=10, exposure_count=5, independence=7,
                              explainability=9, replicability=8, adversarial_robustness=9, novelty_yield=2),
            causal_checks=CausalChecks(reveals_causal_mechanism=True, is_irreducible=True,
                                       survives_authority_removal=True, survives_context_shift=True),
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def build_decision(item: dict) -> DecisionObject:
    return DecisionObject(
        title=item["title"],
        decision_class=item["decision_class"],
        owner="ti_solutions_build_team",
        time_horizon=item["time_horizon"],
        reversibility=item["reversibility"],
        problem_statement=item["rationale"],
        requested_action=item["description"],
        context_summary=f"Sales OS Sprint {item['sprint']} — Ti Solutions build backlog.",
        stakeholders=["sales_strategist", "revops", "founder"],
        constraints=["MVP scope", "SQLite-first", "minimal ops burden"],
        evidence_refs=[
            f"sales-operating-system/01_PRODUCT_REQUIREMENTS.md",
            f"sales-operating-system/08_IMPLEMENTATION_BACKLOG.md",
            f"sales-operating-system/02_SYSTEM_ARCHITECTURE.md",
        ],
        assumptions=["PRD scope is final for MVP", "SQLite-first architecture confirmed"],
        unknowns=["Exact spreadsheet import format", "User adoption timeline"],
        execution_plan=f"Deliver within Sprint {item['sprint']}.",
        monitoring_metric="feature_complete AND tests_passing AND integration_verified",
        rollback_trigger="blocking_dependency_unresolved OR scope_creep_detected",
        review_date="2026-04-30",
        current_state="trust_certified",
        actor_role="AI_Domain_Agent",
        value_scores=item["value"],
        trust_scores=item["trust"],
        alignment_scores=item["alignment"],
        rtql_input=item["rtql"],
    )


def run_backlog_prioritization():
    print("\n" + "═" * 68)
    print("  SALES OS — BACKLOG PRIORITY ANALYSIS")
    print("  Intelligence Engine — Causal Decision Pipeline")
    print("═" * 68)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    orch = IntelligenceOrchestrator(
        engine_yaml_path=ENGINE_YAML,
        db_path=DB_PATH,
        generated_dir=GENERATED,
        claude_api_key=api_key,
        cycle_threshold=999,       # don't auto-trigger cycle mid-run
        dry_run_weights=True,
    )

    ranked = []
    errors = []

    print(f"\n  Processing {len(BACKLOG)} backlog items...\n")

    for item in BACKLOG:
        decision = build_decision(item)
        try:
            result = orch.run_decision(decision)
            ranked.append({
                "title":        item["title"],
                "sprint":       item["sprint"],
                "decision_id":  result.decision_id,
                "priority":     result.priority_score,
                "net_value":    result.net_value_score,
                "verdict":      result.verdict,
                "trust_tier":   result.trust_tier,
                "class":        item["decision_class"].value,
                "rationale":    item["rationale"],
            })
        except Exception as e:
            errors.append({"title": item["title"], "error": str(e)})

    ranked.sort(key=lambda x: x["priority"], reverse=True)
    orch.close()

    _print_report(ranked, errors)
    report_path = _save_report(ranked, errors)
    print(f"\n  Report saved: {report_path}\n")
    return ranked


def _print_report(ranked: list, errors: list):
    print("\n" + "═" * 68)
    print("  PRIORITY RANKING — ALL BACKLOG ITEMS")
    print("═" * 68)
    print(f"  {'#':<3}  {'Sprint':<7}  {'Priority':<9}  {'Value':<6}  {'Tier':<4}  {'Verdict':<18}  Title")
    print(f"  {'─'*3}  {'─'*7}  {'─'*9}  {'─'*6}  {'─'*4}  {'─'*18}  {'─'*35}")

    for i, item in enumerate(ranked, 1):
        flag = "★ " if i <= 5 else "  "
        print(
            f"  {flag}{i:<3} "
            f"  S{item['sprint']:<5} "
            f"  {item['priority']:<9.3f} "
            f"  {item['net_value']:<6.1f} "
            f"  {item['trust_tier']:<4} "
            f"  {item['verdict']:<18} "
            f"  {item['title']}"
        )

    print(f"\n  ★ = Top 5 immediate build candidates")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors:
            print(f"    ✗ {e['title']}: {e['error']}")


def _save_report(ranked: list, errors: list) -> str:
    Path(GENERATED).mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(GENERATED, f"sales_os_priority_{ts}.md")

    lines = [
        "# Sales OS — Backlog Priority Report",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by Intelligence Engine*",
        "",
        "> All 22 backlog items scored through the 9-stage decision pipeline.",
        "> Priority score = weighted value × trust × RTQL multiplier × alignment.",
        "> Verdict governs authorization: `auto_execute` = proceed immediately.",
        "",
        "---",
        "",
        "## Priority Ranking",
        "",
        "| # | Sprint | Priority | Net Value | Trust | Verdict | Item |",
        "|---|--------|----------|-----------|-------|---------|------|",
    ]

    for i, item in enumerate(ranked, 1):
        star = "★ " if i <= 5 else ""
        lines.append(
            f"| {star}{i} | S{item['sprint']} | {item['priority']:.3f} "
            f"| {item['net_value']:.1f} | {item['trust_tier']} "
            f"| `{item['verdict']}` | **{item['title']}** |"
        )

    lines += [
        "",
        "---",
        "",
        "## Top 5 — Build Immediately",
        "",
    ]

    for i, item in enumerate(ranked[:5], 1):
        lines += [
            f"### {i}. {item['title']} (Sprint {item['sprint']})",
            "",
            f"- **Priority score**: {item['priority']:.3f}",
            f"- **Net value**: {item['net_value']:.1f}",
            f"- **Verdict**: `{item['verdict']}`",
            f"- **Trust tier**: {item['trust_tier']}",
            f"- **Rationale**: {item['rationale'][:200]}",
            "",
        ]

    lines += [
        "---",
        "",
        "## Defer / Sequence After Dependencies",
        "",
        "Items ranked 6–22 should be sequenced after their upstream dependencies are stable.",
        "",
    ]

    for i, item in enumerate(ranked[5:], 6):
        lines.append(
            f"- **{i}. {item['title']}** (S{item['sprint']}) — "
            f"priority {item['priority']:.3f}, verdict `{item['verdict']}`"
        )

    lines += [
        "",
        "---",
        "",
        "## Scoring Methodology",
        "",
        "Each item was processed through the full 9-stage pipeline:",
        "1. **RTQL pre-filter** — trust-qualifies the evidence claim behind each item",
        "2. **Value assessment** — scores 8 value dimensions + 4 penalty dimensions",
        "3. **Trust assessment** — scores 7 trust inputs → trust tier T0–T4",
        "4. **Authority check** — validates owner has authority for decision class",
        "5. **Alignment check** — doctrine + ethos + first-principles composite",
        "6. **Certificate chain** — QC → VC → TC → EC issuance",
        "7. **7-Gate authorization** — Doctrine, Trust, Value, Reversibility, Risk, Approval, Monitoring",
        "8. **State machine** — final state transition",
        "9. **Audit trail** — full evidence chain recorded to SQLite",
        "",
        f"*{len(ranked)} items processed, {len(errors)} errors*",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines))

    return path


if __name__ == "__main__":
    run_backlog_prioritization()
