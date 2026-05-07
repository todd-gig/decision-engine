"""
orchestrator/orchestrator.py
Central nervous system — routes decisions through the full loop:
ingest → process → persist → learn → generate → evolve.

All state lives in SQLite. The orchestrator holds no state between cycles
and can restart without data loss.
"""

import sys
import os
import json
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import (
    DecisionObject, PipelineResult, DecisionClass, ReversibilityTag,
    TimeHorizon, TrustTier, ExecutionVerdict,
)
from engine.pipeline import process_decision
from engine.config import load_config, EngineConfig
from engine.learning_loop import (
    OutcomeRecord, calculate_variance,
)

from persistence.db import DatabaseManager
from bridge.claude_bridge import ClaudeBridge, ClaudeAnalysis
from intelligence.pattern_detector import detect_patterns, Pattern
from intelligence.causal_engine import build_causal_graph, CausalEdge, build_causal_narrative
from intelligence.weight_updater import compute_weight_adjustments, apply_weight_adjustments
from intelligence.genesis import (
    generate_decision_template, generate_rtql_rule,
    generate_intelligence_brief, DecisionTemplate, RTQLRule,
)


@dataclass
class OrchestratorResult:
    decision_id: str
    pipeline_result: PipelineResult
    claude_analysis: ClaudeAnalysis
    db_stored: bool
    cycle_triggered: bool
    verdict: str
    trust_tier: str
    net_value_score: float
    priority_score: float


@dataclass
class IntelligenceCycleReport:
    patterns_found: int
    causal_edges_built: int
    weights_proposed: int
    weights_applied: int
    templates_generated: int
    rules_generated: int
    claude_narrative: str
    weight_update_result: dict
    brief_path: str
    causal_narrative: str


class IntelligenceOrchestrator:
    """
    Central coordinator for the full intelligence loop.
    """

    def __init__(
        self,
        engine_yaml_path: str,
        db_path: str,
        generated_dir: str,
        claude_api_key: Optional[str] = None,
        claude_model: str = "claude-opus-4-5",
        cycle_threshold: int = 5,
        dry_run_weights: bool = True,
    ):
        self.engine_yaml_path = engine_yaml_path
        self.generated_dir = generated_dir
        self.cycle_threshold = cycle_threshold
        self.dry_run_weights = dry_run_weights

        # Initialize subsystems
        self.db = DatabaseManager(db_path)
        self.config = load_config(yaml_path=engine_yaml_path)
        self.bridge = ClaudeBridge(
            api_key=claude_api_key,
            model=claude_model,
        )

        print(f"  [orchestrator] Initialized")
        print(f"  [orchestrator] DB: {db_path}")
        print(f"  [orchestrator] Engine config: {engine_yaml_path}")
        print(f"  [orchestrator] Cycle threshold: {cycle_threshold} decisions")
        print(f"  [orchestrator] Weight updates: {'DRY RUN' if dry_run_weights else 'LIVE'}")

    def _reload_config(self):
        """Reload engine config after weight updates."""
        self.config = load_config(yaml_path=self.engine_yaml_path)

    def run_decision(
        self,
        decision: DecisionObject,
        outcome_data: Optional[dict] = None,
    ) -> OrchestratorResult:
        """
        Full single-decision processing loop:
        1. Process through engine pipeline
        2. Persist to SQLite
        3. Get Claude analysis
        4. Optionally record outcome
        5. Trigger intelligence cycle if threshold reached
        """
        # Stage 1: Engine pipeline
        result = process_decision(decision, self.config)

        # Stage 2: Persist
        self.db.store_decision(decision, result)
        db_stored = True

        # Stage 3: Claude analysis
        claude_analysis = self.bridge.analyze_pipeline_result(result, decision)

        # Stage 4: Record outcome if provided
        if outcome_data:
            self._record_outcome(result, outcome_data)

        # Stage 5: Check cycle trigger
        cycle_triggered = False
        count = self.db.decision_count()
        if count > 0 and count % self.cycle_threshold == 0:
            cycle_triggered = True

        verdict = result.execution_packet.verdict.value if result.execution_packet else "unknown"
        trust_tier = result.trust_tier.value if result.trust_tier else "T0"

        return OrchestratorResult(
            decision_id=result.decision_id,
            pipeline_result=result,
            claude_analysis=claude_analysis,
            db_stored=db_stored,
            cycle_triggered=cycle_triggered,
            verdict=verdict,
            trust_tier=trust_tier,
            net_value_score=result.net_value_score or 0.0,
            priority_score=result.priority_score or 0.0,
        )

    def _record_outcome(self, result: PipelineResult, outcome_data: dict):
        """Record a real-world outcome against a processed decision."""
        try:
            verdict = result.execution_packet.verdict if result.execution_packet else ExecutionVerdict.INFORMATION_ONLY
            dclass = DecisionClass(outcome_data.get("decision_class", "D1"))

            outcome = OutcomeRecord(
                decision_id=result.decision_id,
                decision_class=dclass,
                original_verdict=verdict,
                expected_value=float(outcome_data.get("expected_value", result.net_value_score or 0)),
                expected_timeline_days=int(outcome_data.get("expected_timeline_days", 30)),
                expected_risk_level=outcome_data.get("expected_risk_level", "low"),
                actual_value=float(outcome_data.get("actual_value", 0)),
                actual_timeline_days=int(outcome_data.get("actual_timeline_days", 30)),
                actual_risk_materialized=bool(outcome_data.get("actual_risk_materialized", False)),
                outcome_summary=outcome_data.get("outcome_summary", ""),
                lessons_learned=outcome_data.get("lessons_learned", ""),
                recorded_by=outcome_data.get("recorded_by", "orchestrator"),
            )

            variance = calculate_variance(outcome)
            self.db.store_outcome(outcome, variance)
            print(f"    [outcome] Recorded for {result.decision_id} — "
                  f"variance: {variance.value_variance_pct:+.1%} ({variance.direction.value})")
        except Exception as e:
            print(f"    [outcome] Warning — could not record outcome: {e}")

    def run_intelligence_cycle(self) -> IntelligenceCycleReport:
        """
        Full self-improvement cycle:
        1. Detect patterns from accumulated decisions
        2. Build causal graph from outcomes
        3. Compute weight adjustments
        4. Get Claude narrative synthesis
        5. Apply/propose weight updates
        6. Generate template + rule artifacts
        7. Generate intelligence brief
        8. Reload config if weights updated
        """
        print("\n" + "═" * 60)
        print("  INTELLIGENCE CYCLE RUNNING")
        print("═" * 60)

        # 1. Pattern detection
        patterns = detect_patterns(self.db, min_occurrences=2)
        print(f"  [cycle] Patterns detected: {len(patterns)}")

        # 2. Causal graph
        causal_graph = build_causal_graph(self.db)
        print(f"  [cycle] Causal edges built: {len(causal_graph)}")
        causal_narr = build_causal_narrative(causal_graph)

        # 3. Weight adjustments
        adjustments = compute_weight_adjustments(self.db, self.engine_yaml_path, min_samples=2)
        print(f"  [cycle] Weight adjustments proposed: {len(adjustments)}")

        # 4. Claude narrative + weight recommendation
        variance_summary = self.db.get_variance_summary()
        claude_narrative = self.bridge.synthesize_patterns(
            [p.__dict__ for p in patterns],
            [{"variable_name": e.variable_name,
              "decision_class": e.decision_class,
              "correlation_strength": e.correlation_strength,
              "causal_confidence": e.causal_confidence} for e in causal_graph[:5]],
            variance_summary,
        )

        # Claude weight recommendation (for primary decision class)
        all_decisions = self.db.get_all_decisions()
        primary_class = "D1"
        if all_decisions:
            from collections import Counter
            primary_class = Counter(d["decision_class"] for d in all_decisions).most_common(1)[0][0]

        from intelligence.weight_updater import load_current_weights
        current_weights = load_current_weights(self.engine_yaml_path)
        claude_recs = self.bridge.generate_weight_recommendation(
            variance_summary, current_weights, primary_class
        )

        # 5. Apply weight updates
        weight_result = apply_weight_adjustments(
            adjustments,
            self.engine_yaml_path,
            self.db,
            claude_recommendations=claude_recs,
            dry_run=self.dry_run_weights,
        )
        print(f"  [cycle] Weight changes: {len(weight_result['applied'])} "
              f"({'dry run' if self.dry_run_weights else 'applied'})")

        # 6. Generate artifacts
        templates_generated = 0
        rules_generated = 0

        if patterns:
            top_pattern = max(patterns, key=lambda p: p.confidence_score)
            try:
                tmpl = generate_decision_template(top_pattern, self.db, self.generated_dir)
                templates_generated = 1
                print(f"  [cycle] Template generated: {tmpl.template_id} ({top_pattern.decision_class})")
            except Exception as e:
                print(f"  [cycle] Template generation warning: {e}")

        if causal_graph:
            top_edge = max(causal_graph, key=lambda e: abs(e.correlation_strength))
            try:
                rule = generate_rtql_rule(top_edge, self.generated_dir)
                rules_generated = 1
                print(f"  [cycle] Rule generated: {rule.rule_id}")
            except Exception as e:
                print(f"  [cycle] Rule generation warning: {e}")

        # 7. Generate brief
        weight_history = self.db.get_weight_history()
        brief_path = generate_intelligence_brief(
            patterns=patterns,
            causal_graph=causal_graph,
            weight_history=weight_history,
            weight_update_result=weight_result,
            claude_narrative=claude_narrative,
            generated_dir=self.generated_dir,
            db=self.db,
        )
        print(f"  [cycle] Brief saved: {brief_path}")

        # 8. Reload config if weights actually updated
        if not self.dry_run_weights and weight_result["applied"]:
            self._reload_config()
            print("  [cycle] Engine config reloaded with updated weights")

        print("═" * 60)

        return IntelligenceCycleReport(
            patterns_found=len(patterns),
            causal_edges_built=len(causal_graph),
            weights_proposed=len(adjustments),
            weights_applied=len(weight_result["applied"]) if not self.dry_run_weights else 0,
            templates_generated=templates_generated,
            rules_generated=rules_generated,
            claude_narrative=claude_narrative,
            weight_update_result=weight_result,
            brief_path=brief_path,
            causal_narrative=causal_narr,
        )

    def ingest_human_variables(self, variables: list[dict], context: str = ""):
        """
        Accept raw human-weighted inputs, route through RTQL, return classified set.
        """
        from ingestion.human_variable_intake import (
            HumanVariable, classify_human_variables, print_intake_report,
        )
        hvars = [
            HumanVariable(
                variable_name=v["variable_name"],
                claimed_value=float(v.get("claimed_value", 0.5)),
                source=v.get("source", ""),
                how_confident=int(v.get("how_confident", 3)),
                evidence_description=v.get("evidence_description", ""),
                category=v.get("category", ""),
            )
            for v in variables
        ]
        result = classify_human_variables(hvars)
        print_intake_report(result)
        return result

    def close(self):
        self.db.close()
