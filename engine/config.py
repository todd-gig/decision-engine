"""
Engine Configuration — Configurable thresholds, weights, authority matrix, and state machine.

Loaded from engine.yaml or constructed programmatically.
All engine behavior that should be tunable lives here.
"""

from dataclasses import dataclass, field
from typing import Optional
import yaml
import os


@dataclass
class Thresholds:
    """Execution and escalation thresholds."""
    value_execute_min: float = 14.0
    value_escalate_min: float = 8.0
    trust_execute_min: float = 3.5
    trust_recommend_min: float = 2.2
    # Per-class value thresholds (override gate defaults)
    value_by_class: dict = field(default_factory=lambda: {
        "D0": 0, "D1": 8, "D2": 12, "D3": 16,
        "D4": 20, "D5": 20, "D6": 24,
    })


@dataclass
class ValueWeights:
    """Asymmetric weights for value dimensions.
    Raw score × weight = weighted contribution."""
    revenue_impact: float = 1.5
    cost_efficiency: float = 1.2
    time_leverage: float = 1.3
    strategic_alignment: float = 2.0
    customer_benefit: float = 1.4
    knowledge_creation: float = 1.1
    compounding_potential: float = 1.8
    reversibility: float = 1.0


@dataclass
class PenaltyWeights:
    """Asymmetric weights for penalty dimensions.
    Higher weights = harsher penalty."""
    downside_risk: float = 2.0
    execution_drag: float = 1.2
    uncertainty: float = 1.5
    ethical_misalignment: float = 3.0


@dataclass
class AuthorityRule:
    """Authority rule for a single decision class."""
    min_trust: str = "T3"
    executor: str = "AI_Domain_Agent"
    required_approval: str = "none"


@dataclass
class EngineConfig:
    """Master configuration for the decision engine."""
    thresholds: Thresholds = field(default_factory=Thresholds)
    value_weights: ValueWeights = field(default_factory=ValueWeights)
    penalty_weights: PenaltyWeights = field(default_factory=PenaltyWeights)

    # Trust tier multipliers (tier → multiplier)
    trust_multiplier: dict = field(default_factory=lambda: {
        "T0": 0.2, "T1": 0.5, "T2": 0.8, "T3": 1.0, "T4": 1.2,
    })

    # Authority matrix: decision_class → AuthorityRule
    authority_matrix: dict = field(default_factory=lambda: {
        "D1": AuthorityRule(min_trust="T3", executor="AI_Domain_Agent", required_approval="none"),
        "D2": AuthorityRule(min_trust="T3", executor="AI_Domain_Agent", required_approval="Domain_Owner"),
        "D3": AuthorityRule(min_trust="T2", executor="Domain_Owner", required_approval="Human_Executive"),
        "D4": AuthorityRule(min_trust="T2", executor="Human_Executive", required_approval="Human_CEO"),
        "D5": AuthorityRule(min_trust="T1", executor="Human_Executive", required_approval="Human_CEO"),
        "D6": AuthorityRule(min_trust="T1", executor="Human_CEO", required_approval="Human_CEO"),
    })

    # State machine: valid transitions
    valid_transitions: dict = field(default_factory=lambda: {
        "draft": ["qualified", "execution_cleared"],
        "qualified": ["value_confirmed", "draft"],
        "value_confirmed": ["trust_certified", "qualified"],
        "trust_certified": ["execution_cleared", "qualified"],
        "execution_cleared": ["executed", "trust_certified"],
        "executed": ["reviewed"],
        "reviewed": ["archived", "qualified"],
        "archived": [],
    })


def load_config(yaml_path: Optional[str] = None) -> EngineConfig:
    """
    Load engine config from YAML file, falling back to defaults.
    """
    if yaml_path is None:
        # Look for engine.yaml in project root
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yaml_path = os.path.join(root, "engine.yaml")

    config = EngineConfig()

    if os.path.exists(yaml_path):
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f) or {}

        # Thresholds
        if "thresholds" in data:
            t = data["thresholds"]
            config.thresholds.value_execute_min = t.get("value_execute_min", config.thresholds.value_execute_min)
            config.thresholds.value_escalate_min = t.get("value_escalate_min", config.thresholds.value_escalate_min)
            config.thresholds.trust_execute_min = t.get("trust_execute_min", config.thresholds.trust_execute_min)
            config.thresholds.trust_recommend_min = t.get("trust_recommend_min", config.thresholds.trust_recommend_min)

        # Value weights
        if "value_weights" in data:
            vw = data["value_weights"]
            for k, v in vw.items():
                if hasattr(config.value_weights, k):
                    setattr(config.value_weights, k, v)

        # Penalty weights
        if "penalty_weights" in data:
            pw = data["penalty_weights"]
            for k, v in pw.items():
                if hasattr(config.penalty_weights, k):
                    setattr(config.penalty_weights, k, v)

        # Trust multiplier
        if "trust_multiplier" in data:
            config.trust_multiplier = data["trust_multiplier"]

        # Authority matrix
        if "authority_matrix" in data:
            for dc, rule_data in data["authority_matrix"].items():
                config.authority_matrix[dc] = AuthorityRule(
                    min_trust=rule_data.get("min_trust", "T3"),
                    executor=rule_data.get("executor", "AI_Domain_Agent"),
                    required_approval=rule_data.get("required_approval", "none"),
                )

        # Valid transitions
        if "valid_transitions" in data:
            config.valid_transitions = data["valid_transitions"]

    return config
