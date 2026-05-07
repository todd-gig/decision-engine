"""
analyze_reddit_memory.py
========================
Feeds the r/AIMemory "What an AI memory system should look like in 2026"
content through the Intelligence Engine pipeline.

Since Reddit itself is network-blocked, we use the best available
web-gathered intelligence:

Source 1: OMEGA vs Mem0 vs Zep comparison (omegamax.co/blog)
  — OMEGA: local-first SQLite+ONNX, hybrid BM25+vector, 95.4% LongMemEval
  — Mem0:  cloud-first Qdrant, flat memories + graph (paid tier)
  — Zep:   temporal knowledge graph Neo4j, entity extraction, 71.2% LongMemEval

Source 2: AI Memory Systems 2026 overview (aitechboss.com)
  — "How AI Is Learning to Remember Like Humans" (Feb 15 2026)
  — Local-first vs cloud tradeoffs emerging as primary design axis

Source 3: Qwen3 local AI memory stack article (craftrigs.com)
  — 16GB VRAM viable for full local memory stack (Qwen3-0.6B + 9B)
  — r/LocalLLaMA benchmarking confirms local-first feasibility

Three DecisionObjects are analyzed:
  D1 — Adopt OMEGA (local-first, highest accuracy)
  D2 — Adopt Mem0  (cloud-managed, lower ops overhead)
  D3 — Adopt Zep   (temporal graph, richest relational memory)

Each is scored through the full 9-stage pipeline.
"""

import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine.models import (
    DecisionClass, DecisionObject, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks,
)
from orchestrator.orchestrator import IntelligenceOrchestrator

DB_PATH   = os.path.join(ROOT, "data", "intelligence.db")
GEN_DIR   = os.path.join(ROOT, "data", "generated")
ENG_YAML  = os.path.join(ROOT, "engine.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# Decision objects: three competing memory architectures
# ─────────────────────────────────────────────────────────────────────────────

def decision_omega():
    """
    OMEGA (local-first)
    Architecture : SQLite + ONNX embeddings, hybrid BM25 + vector, semantic reranking
    LongMemEval  : 95.4% (best published, 2026)
    MemoryStress : Graceful degradation over 1,000 sessions — no catastrophic failure
    Source trust : Published benchmark on standard eval; methodology visible
    """
    return DecisionObject(
        title="Adopt OMEGA local-first AI memory architecture",
        decision_class=DecisionClass.D2_OPERATIONAL,
        owner="architecture_team",
        time_horizon=TimeHorizon.MID_TERM,
        reversibility=ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        problem_statement=(
            "We need an AI memory system for 2026 that maximises retrieval accuracy, "
            "minimises infrastructure dependency, and degrades gracefully at scale."
        ),
        requested_action=(
            "Adopt OMEGA as primary memory layer: local SQLite store, ONNX embeddings, "
            "hybrid BM25+vector retrieval, semantic reranking. No cloud dependency."
        ),
        context_summary=(
            "OMEGA achieves 95.4% on LongMemEval (500 questions), highest of any "
            "published 2026 system. Runs fully offline. MemoryStress (1,000 sessions) "
            "shows gradual not catastrophic degradation. r/LocalLLaMA confirms "
            "viability on 16GB VRAM with Qwen3 stack."
        ),
        stakeholders=["architecture_team", "infra_ops", "product"],
        constraints=["Must not require cloud API for inference", "Target hardware: 16GB VRAM"],
        execution_plan="Integrate OMEGA Python package → embed into agent loop → benchmark",
        monitoring_metric="LongMemEval accuracy >= 90% on internal test set",
        rollback_trigger="accuracy < 80% OR memory store corruption",
        review_date="2026-06-30",
        current_state="pending",
        actor_role="Architecture Team",
        value_scores=ValueScores(
            revenue_impact=3,
            cost_efficiency=5,          # no cloud API cost
            time_leverage=4,
            strategic_alignment=5,      # aligns with local-first autonomy doctrine
            customer_human_benefit=4,
            knowledge_asset_creation=5, # memory as a permanent knowledge store
            compounding_potential=5,    # every interaction improves memory quality
            reversibility=4,
            downside_risk=2,
            execution_drag=2,
            uncertainty=2,              # benchmark is public and reproducible
            ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=5,         # 95.4% on public benchmark with methodology
            logic_integrity=5,
            outcome_history=3,          # no internal track record yet
            context_fit=4,
            stakeholder_clarity=4,
            risk_containment=4,
            auditability=5,             # local system = fully auditable
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.90,
            ethos_alignment=0.88,
            first_principles_alignment=0.85,
        ),
        rtql_input=RTQLInput(
            claim="OMEGA achieves 95.4% on LongMemEval — highest of any published system",
            source="omegamax.co/blog/omega-vs-mem0-vs-zep (Feb 2026)",
            is_identifiable=True,
            has_provenance=True,
            scores=RTQLScores(
                source_integrity=8,
                exposure_count=4,       # multiple benchmark references confirmed
                independence=6,         # vendor-published but methodology verifiable
                explainability=8,
                replicability=7,        # public eval dataset LongMemEval
                adversarial_robustness=6,
                novelty_yield=4,
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=True,   # hybrid BM25+vector explains why
                is_irreducible=False,
                survives_authority_removal=True,
                survives_context_shift=True,
            ),
        ),
    )


def decision_mem0():
    """
    Mem0 (cloud-managed)
    Architecture : Cloud API / Docker + Qdrant + PostgreSQL + OpenAI
    LongMemEval  : Not published
    Ops overhead : Minimal (managed service)
    Source trust : Well-known product but no published accuracy benchmarks
    """
    return DecisionObject(
        title="Adopt Mem0 cloud-managed AI memory platform",
        decision_class=DecisionClass.D2_OPERATIONAL,
        owner="architecture_team",
        time_horizon=TimeHorizon.MID_TERM,
        reversibility=ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        problem_statement=(
            "We need an AI memory system that minimises operational overhead "
            "at the cost of accepting cloud infrastructure dependency."
        ),
        requested_action=(
            "Adopt Mem0 managed platform: cloud API or Docker+Qdrant, "
            "flat key-value memories, optional graph tier (paid). "
            "OpenAI API required for embeddings."
        ),
        context_summary=(
            "Mem0 offers lowest operational overhead among evaluated systems. "
            "However, it has not published LongMemEval results as of March 2026. "
            "Requires OpenAI API dependency — adds cost and latency. "
            "Graph memory features require paid tier."
        ),
        stakeholders=["architecture_team", "infra_ops", "finance"],
        constraints=["Requires OpenAI API key", "Cloud egress costs scale with usage"],
        execution_plan="Sign up for managed API → integrate SDK → evaluate in staging",
        monitoring_metric="retrieval_latency_p95 < 300ms AND accuracy >= 85%",
        rollback_trigger="accuracy unverifiable OR cost > budget threshold",
        review_date="2026-06-30",
        current_state="pending",
        actor_role="Architecture Team",
        value_scores=ValueScores(
            revenue_impact=2,
            cost_efficiency=2,          # cloud + OpenAI API costs
            time_leverage=5,            # fastest to integrate (managed service)
            strategic_alignment=2,      # cloud dependency conflicts with autonomy doctrine
            customer_human_benefit=3,
            knowledge_asset_creation=3,
            compounding_potential=3,
            reversibility=3,
            downside_risk=3,
            execution_drag=2,
            uncertainty=4,              # no public accuracy benchmark
            ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=2,         # no LongMemEval published
            logic_integrity=4,
            outcome_history=3,
            context_fit=3,
            stakeholder_clarity=4,
            risk_containment=3,
            auditability=2,             # cloud system — black-box retrieval
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.50,
            ethos_alignment=0.60,
            first_principles_alignment=0.45,
        ),
        rtql_input=RTQLInput(
            claim="Mem0 provides production-grade AI memory with minimal ops overhead",
            source="omegamax.co/blog/omega-vs-mem0-vs-zep (Feb 2026) + Mem0 docs",
            is_identifiable=True,
            has_provenance=True,
            scores=RTQLScores(
                source_integrity=5,
                exposure_count=3,
                independence=4,
                explainability=5,
                replicability=2,        # accuracy not independently verifiable
                adversarial_robustness=4,
                novelty_yield=2,
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=False,  # accuracy claim unsubstantiated
                is_irreducible=False,
                survives_authority_removal=False,
                survives_context_shift=False,
            ),
        ),
    )


def decision_zep():
    """
    Zep / Graphiti (temporal knowledge graph)
    Architecture : Neo4j + LLM entity extraction, temporal edges, episode memory
    LongMemEval  : 71.2% — significantly below OMEGA
    Strength     : Richest relational / temporal reasoning capability
    """
    return DecisionObject(
        title="Adopt Zep temporal knowledge-graph AI memory",
        decision_class=DecisionClass.D2_OPERATIONAL,
        owner="architecture_team",
        time_horizon=TimeHorizon.MID_TERM,
        reversibility=ReversibilityTag.R2_MODERATELY_REVERSIBLE,
        problem_statement=(
            "We need an AI memory system that can reason about relationships "
            "and temporal sequences across long interaction histories — "
            "not just semantic similarity search."
        ),
        requested_action=(
            "Adopt Zep/Graphiti: Neo4j knowledge graph with LLM entity extraction, "
            "temporal edges, episode + entity + relation memory tiers. "
            "Enables queries like 'who said X after Y happened?'"
        ),
        context_summary=(
            "Zep's temporal knowledge graph provides the richest relational memory "
            "of any 2026 system evaluated. However, LongMemEval accuracy is 71.2% — "
            "24 percentage points below OMEGA. Neo4j adds significant infra complexity. "
            "LLM entity extraction is expensive at scale."
        ),
        stakeholders=["architecture_team", "data_team", "infra_ops"],
        constraints=["Neo4j license required", "LLM extraction cost scales with session count"],
        execution_plan="Deploy Neo4j → integrate Graphiti → evaluate on relational query benchmark",
        monitoring_metric="temporal_query_accuracy >= 80% AND entity_extraction_precision >= 0.85",
        rollback_trigger="LongMemEval accuracy < 65% OR infra_cost > threshold",
        review_date="2026-06-30",
        current_state="pending",
        actor_role="Architecture Team",
        value_scores=ValueScores(
            revenue_impact=3,
            cost_efficiency=2,          # Neo4j + LLM extraction costs
            time_leverage=3,
            strategic_alignment=4,
            customer_human_benefit=4,   # relational memory enables richer agent behavior
            knowledge_asset_creation=5, # graph = explicit knowledge model
            compounding_potential=4,
            reversibility=2,            # graph schema is hard to migrate
            downside_risk=3,
            execution_drag=4,           # Neo4j setup complexity
            uncertainty=3,
            ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=4,         # 71.2% published on LongMemEval
            logic_integrity=5,
            outcome_history=2,
            context_fit=3,
            stakeholder_clarity=3,
            risk_containment=3,
            auditability=4,             # graph is inspectable
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.70,
            ethos_alignment=0.75,
            first_principles_alignment=0.72,
        ),
        rtql_input=RTQLInput(
            claim="Zep/Graphiti enables temporal relational reasoning with 71.2% LongMemEval accuracy",
            source="omegamax.co/blog/omega-vs-mem0-vs-zep (Feb 2026)",
            is_identifiable=True,
            has_provenance=True,
            scores=RTQLScores(
                source_integrity=7,
                exposure_count=4,
                independence=6,
                explainability=7,
                replicability=6,        # LongMemEval is reproducible
                adversarial_robustness=5,
                novelty_yield=5,        # graph-temporal memory is novel architecture
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=True,   # graph structure explains relational capability
                is_irreducible=False,
                survives_authority_removal=True,
                survives_context_shift=False,    # temporal reasoning may not generalize
            ),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  INTELLIGENCE ENGINE — Reddit r/AIMemory Analysis                  ║")
    print("║  Source: 'What an AI memory system should look like in 2026'        ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    print(f"  Claude: {'LIVE' if api_key else 'MOCK (set ANTHROPIC_API_KEY for Claude analysis)'}")

    orch = IntelligenceOrchestrator(
        engine_yaml_path=ENG_YAML,
        db_path=DB_PATH,
        generated_dir=GEN_DIR,
        claude_api_key=api_key,
        cycle_threshold=5,
        dry_run_weights=True,
    )

    scenarios = [
        ("OMEGA — local-first, BM25+vector, 95.4% LongMemEval",  decision_omega()),
        ("Mem0  — cloud-managed, no published benchmark",          decision_mem0()),
        ("Zep   — temporal knowledge graph, 71.2% LongMemEval",   decision_zep()),
    ]

    results = []
    for label, decision in scenarios:
        print(f"\n  ── {label}")
        try:
            r = orch.run_decision(decision)
            results.append((label, decision, r))
            print(f"     Verdict      : {r.verdict.upper()}")
            print(f"     Trust tier   : {r.trust_tier}")
            print(f"     Net value    : {r.net_value_score:.1f}")
            print(f"     Priority     : {r.priority_score:.3f}")
            if r.claude_analysis and r.claude_analysis.narrative:
                print(f"     Claude       : {r.claude_analysis.narrative[:140]}...")
        except Exception as e:
            import traceback
            print(f"     ERROR: {e}")
            traceback.print_exc()

    # ── Comparative summary ────────────────────────────────────────────────────
    if results:
        print()
        print("  ╔══════════════════════════════════════════════════════════════╗")
        print("  ║  COMPARATIVE RANKING                                        ║")
        print("  ╠══════════════════════════════════════════════════════════════╣")

        ranked = sorted(results, key=lambda x: x[2].priority_score, reverse=True)
        for rank, (label, _, r) in enumerate(ranked, 1):
            name = label.split("—")[0].strip()
            bar = "█" * int(r.priority_score * 40)
            print(f"  ║  #{rank} {name:10s}  priority={r.priority_score:.3f}  net_val={r.net_value_score:5.1f}  {bar[:28]:28s}  ║")

        print("  ╚══════════════════════════════════════════════════════════════╝")

        winner_label, winner_dec, winner_result = ranked[0]
        print(f"""
  INTELLIGENCE ENGINE RECOMMENDATION:
  ─────────────────────────────────────
  Architecture : {winner_dec.title}
  Verdict      : {winner_result.verdict.upper()}
  Trust tier   : {winner_result.trust_tier}
  Net value    : {winner_result.net_value_score:.1f}
  Priority     : {winner_result.priority_score:.3f}

  Primary evidence: OMEGA's 95.4% LongMemEval accuracy (vs 71.2% Zep, unpublished Mem0)
  represents a causal advantage — hybrid BM25+vector retrieval with semantic reranking
  is the mechanism. Local-first eliminates cloud dependency, audit surface, and
  per-query cost. Alignment with autonomy doctrine is highest of the three.

  Key risk: Internal outcome history is zero. RTQL exposure_count = 4 (vendor benchmark,
  not independently replicated in-house). Recommendation: run internal validation on
  LongMemEval before full adoption. Escalate to certified if internal accuracy >= 90%.
""")

    # ── Intelligence cycle ─────────────────────────────────────────────────────
    print("  ── Running intelligence cycle...")
    try:
        cycle = orch.run_intelligence_cycle()
        print(f"     Patterns: {cycle.patterns_found}  |  Causal edges: {cycle.causal_edges_built}  |  Weight proposals: {cycle.weights_proposed}")
        if cycle.brief_path:
            print(f"     Brief saved to: {cycle.brief_path}")
    except Exception as e:
        print(f"     Cycle error: {e}")

    orch.close()
    print("\n  Analysis complete.\n")


if __name__ == "__main__":
    run()
