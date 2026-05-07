"""
bridge/claude_bridge.py
Bidirectional bridge between Claude API and the decision engine.

Claude receives pipeline results and returns enriched analysis.
Claude's analysis can generate new DecisionObject fields or survey inputs
that feed back through RTQL into the engine.

Operates in MOCK MODE if ANTHROPIC_API_KEY is not set or mock_mode=True.
"""

import os
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import (
    DecisionObject, PipelineResult, DecisionClass, ReversibilityTag,
    TimeHorizon, ValueScores, TrustScores, AlignmentScores, RTQLInput,
    RTQLScores, CausalChecks,
)
from engine.audit import serialize_pipeline_result


# ─── CLAUDE ANALYSIS DATACLASS ───────────────────────────────────────────────

@dataclass
class ClaudeAnalysis:
    decision_id: str
    narrative: str
    identified_patterns: list[str]
    causal_hypotheses: list[dict]   # [{"variable": str, "direction": str, "confidence": str}]
    recommended_actions: list[str]
    weight_adjustment_hints: dict
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    mock: bool = False


# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the intelligence layer of a deterministic decision governance engine.

The engine uses these scoring systems:
- VALUE MATRIX: 8 positive dimensions (0-5) + 4 penalty dimensions (0-5). Net = sum(positive) - sum(penalties).
  Weights: strategic_alignment×2.0, compounding_potential×1.8, revenue_impact×1.5, ethical_misalignment×3.0 (penalty)
- TRUST TIERS: T0 (unqualified) → T4 (delegated). Based on 7 trust inputs (0-5 each).
- RTQL: 9-stage trust classification: noise → weak_signal → echo_signal → qualified → certification_gap
  → certified → research_grade → first_principles_candidate → axiom_candidate
  Trust multipliers: noise=0.0, qualified=1.0, certified=1.15, first_principles=1.5
- GATES: 7-gate authorization — doctrine, trust, value, reversibility, risk, approval, monitoring
- VERDICTS: AUTO_EXECUTE | ESCALATE_TIER_1/2/3 | BLOCK | NEEDS_DATA | INFORMATION_ONLY
- DECISION CLASSES: D0 (info) → D6 (irreversible/high-blast). D1/D2 can auto-execute if T3+.

Your job: analyze pipeline results, identify causal patterns, and recommend weight adjustments.
Respond only with valid JSON matching the requested schema."""


# ─── MOCK RESPONSES ──────────────────────────────────────────────────────────

def _mock_analysis(decision_id: str, verdict: str, trust_tier: str) -> ClaudeAnalysis:
    return ClaudeAnalysis(
        decision_id=decision_id,
        narrative=(
            f"Decision {decision_id} processed with verdict {verdict} at trust tier {trust_tier}. "
            "Pattern analysis indicates adequate evidence quality. "
            "Strategic alignment is the dominant value driver based on weight configuration. "
            "Recommend monitoring outcome variance to calibrate downside_risk penalty weight."
        ),
        identified_patterns=[
            "Evidence quality correlates positively with trust tier promotion",
            "High strategic_alignment scores reduce escalation frequency",
        ],
        causal_hypotheses=[
            {"variable": "trust_scores.evidence_quality", "direction": "positive", "confidence": "medium"},
            {"variable": "value_scores.strategic_alignment", "direction": "positive", "confidence": "high"},
            {"variable": "value_scores.ethical_misalignment", "direction": "negative", "confidence": "high"},
        ],
        recommended_actions=[
            "Increase evidence documentation for D3+ decisions",
            "Establish monitoring metrics before execution clearance",
        ],
        weight_adjustment_hints={
            "value_weights": {"strategic_alignment": 0.0},
            "penalty_weights": {"ethical_misalignment": 0.0},
        },
        mock=True,
    )


def _mock_weight_recommendation(variance_summary: dict, decision_class: str) -> dict:
    mean_var = variance_summary.get("mean_variance", 0.0)
    risk_rate = variance_summary.get("risk_surprise_rate", 0.0)
    adjustments = {"value_weights": {}, "penalty_weights": {}, "reasoning": ""}

    if mean_var < -0.1:
        adjustments["value_weights"]["revenue_impact"] = -0.05
        adjustments["penalty_weights"]["uncertainty"] = 0.1
        adjustments["reasoning"] = (
            f"Negative mean variance ({mean_var:.2f}) for {decision_class} suggests "
            "overestimation of revenue impact and underweighting of uncertainty."
        )
    elif mean_var > 0.2:
        adjustments["value_weights"]["compounding_potential"] = 0.05
        adjustments["reasoning"] = (
            f"Positive mean variance ({mean_var:.2f}) suggests compounding_potential "
            "is underweighted for {decision_class} decisions."
        )
    else:
        adjustments["reasoning"] = (
            f"Variance ({mean_var:.2f}) within acceptable range. "
            "No weight adjustment recommended this cycle."
        )

    if risk_rate > 0.2:
        adjustments["penalty_weights"]["downside_risk"] = 0.15
        adjustments["reasoning"] += (
            f" Risk surprise rate ({risk_rate:.0%}) is elevated — "
            "recommend increasing downside_risk penalty weight."
        )

    return adjustments


def _mock_synthesize(patterns: list, causal_graph: list, variance_summary: dict) -> str:
    n_patterns = len(patterns)
    n_edges = len(causal_graph)
    mean_var = variance_summary.get("mean_variance", 0.0)
    return (
        f"INTELLIGENCE SYNTHESIS (mock mode)\n\n"
        f"Pattern Analysis: {n_patterns} patterns detected across decision history.\n"
        f"Causal Graph: {n_edges} causal edges identified from outcome data.\n"
        f"Outcome Variance: Mean variance = {mean_var:+.3f} — "
        f"{'system is performing above baseline' if mean_var > 0 else 'system is underperforming baseline'}.\n\n"
        f"Key insight: The RTQL trust multiplier is the strongest leading indicator of outcome quality. "
        f"Decisions entering the pipeline with RTQL stage 'certified' or above achieve "
        f"materially better outcomes than 'qualified' decisions.\n\n"
        f"Recommendation: Increase the minimum RTQL threshold for D3+ decisions to 'certified'. "
        f"Establish a structured evidence collection protocol before any D3+ decision enters the pipeline."
    )


# ─── CLAUDE BRIDGE ───────────────────────────────────────────────────────────

class ClaudeBridge:
    """
    Bidirectional bridge between Claude API and the decision engine.
    Falls back to mock mode if API key is absent or mock_mode=True.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-opus-4-5",
                 mock_mode: bool = False):
        self.model = model
        self.mock_mode = mock_mode or not api_key

        if not self.mock_mode:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                print("  [bridge] anthropic package not installed — switching to mock mode")
                self.mock_mode = True
                self.client = None
        else:
            self.client = None

        mode_str = "MOCK" if self.mock_mode else f"LIVE ({self.model})"
        print(f"  [bridge] Claude bridge initialized — mode: {mode_str}")

    def _call_claude(self, user_prompt: str, max_tokens: int = 1500) -> str:
        """Raw Claude API call. Returns the text content."""
        if self.mock_mode or self.client is None:
            raise RuntimeError("Cannot call Claude in mock mode")
        import anthropic
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def analyze_pipeline_result(
        self,
        result: PipelineResult,
        decision: DecisionObject,
        context: str = "",
    ) -> ClaudeAnalysis:
        """
        Send pipeline result to Claude for pattern + causal analysis.
        Returns structured ClaudeAnalysis.
        """
        verdict = result.execution_packet.verdict.value if result.execution_packet else "unknown"
        trust_tier = result.trust_tier.value if result.trust_tier else "T0"

        if self.mock_mode:
            return _mock_analysis(result.decision_id, verdict, trust_tier)

        summary = result.executive_summary or ""
        prompt = f"""Analyze this pipeline result and return JSON with this exact schema:
{{
  "narrative": "string — 2-3 sentence analysis",
  "identified_patterns": ["string", ...],
  "causal_hypotheses": [{{"variable": "string", "direction": "positive|negative|neutral", "confidence": "low|medium|high"}}],
  "recommended_actions": ["string", ...],
  "weight_adjustment_hints": {{"value_weights": {{}}, "penalty_weights": {{}}}}
}}

Decision class: {decision.decision_class.value}
Verdict: {verdict}
Trust tier: {trust_tier}
Net value score: {result.net_value_score}
Priority score: {result.priority_score}
RTQL stage: {result.rtql_result.stage.value if result.rtql_result else 'unknown'}
Executive summary: {summary[:500]}
{f'Context: {context}' if context else ''}"""

        try:
            raw = self._call_claude(prompt)
            data = json.loads(raw)
            return ClaudeAnalysis(
                decision_id=result.decision_id,
                narrative=data.get("narrative", ""),
                identified_patterns=data.get("identified_patterns", []),
                causal_hypotheses=data.get("causal_hypotheses", []),
                recommended_actions=data.get("recommended_actions", []),
                weight_adjustment_hints=data.get("weight_adjustment_hints", {}),
                mock=False,
            )
        except Exception as e:
            print(f"  [bridge] Claude API error: {e} — falling back to mock")
            return _mock_analysis(result.decision_id, verdict, trust_tier)

    def generate_weight_recommendation(
        self,
        variance_summary: dict,
        current_weights: dict,
        decision_class: str,
    ) -> dict:
        """
        Claude recommends specific weight delta values based on variance summary.
        Returns {"value_weights": {...}, "penalty_weights": {...}, "reasoning": str}
        """
        if self.mock_mode:
            return _mock_weight_recommendation(variance_summary, decision_class)

        prompt = f"""Based on outcome variance data, recommend weight adjustments for {decision_class} decisions.
Return JSON with this exact schema:
{{"value_weights": {{"key": delta_float, ...}}, "penalty_weights": {{"key": delta_float, ...}}, "reasoning": "string"}}

Rules:
- delta must be between -0.3 and +0.3
- Only include keys where adjustment is warranted
- Deltas are additive changes to current weights

Variance summary: {json.dumps(variance_summary, indent=2)}
Current weights: {json.dumps(current_weights, indent=2)}"""

        try:
            raw = self._call_claude(prompt, max_tokens=800)
            return json.loads(raw)
        except Exception as e:
            print(f"  [bridge] Weight recommendation error: {e} — using mock")
            return _mock_weight_recommendation(variance_summary, decision_class)

    def synthesize_patterns(
        self,
        patterns: list[dict],
        causal_graph: list[dict],
        variance_summary: dict,
    ) -> str:
        """
        Synthesize all system intelligence into a strategic narrative.
        Returns a human-readable executive intelligence brief section.
        """
        if self.mock_mode:
            return _mock_synthesize(patterns, causal_graph, variance_summary)

        prompt = f"""Synthesize these intelligence inputs into a 3-5 paragraph strategic assessment.
Focus on: what the patterns mean, what the causal graph reveals, and what should change next.

Patterns ({len(patterns)}): {json.dumps(patterns[:5], default=str)}
Top causal edges ({min(5, len(causal_graph))}): {json.dumps(causal_graph[:5], default=str)}
Variance summary: {json.dumps(variance_summary, indent=2)}"""

        try:
            return self._call_claude(prompt, max_tokens=1000)
        except Exception as e:
            print(f"  [bridge] Synthesis error: {e} — using mock")
            return _mock_synthesize(patterns, causal_graph, variance_summary)
