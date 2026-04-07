"""Causal Chain Mapping System.

Implements the 4-layer propagation model from CAUSAL_CHAIN_MAPPING_SYSTEM.md.

Layer 1 (Days 0-7):   Primary system impacts
Layer 2 (Days 7-30):  Secondary cascading effects
Layer 3 (Days 30-90): Tertiary cultural/structural effects
Layer 4 (90+ days):   Compound strategic advantage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4


class CausalLayer(int, Enum):
    PRIMARY = 1      # Days 0-7
    SECONDARY = 2    # Days 7-30
    TERTIARY = 3     # Days 30-90
    COMPOUND = 4     # 90+ days


LAYER_DAY_RANGES = {
    CausalLayer.PRIMARY: (0, 7),
    CausalLayer.SECONDARY: (7, 30),
    CausalLayer.TERTIARY: (30, 90),
    CausalLayer.COMPOUND: (90, 365),
}


class CausalStrength(str, Enum):
    PRIMARY = "primary"        # 100% attribution
    SECONDARY = "secondary"    # 60-80% attribution (default 70%)
    TERTIARY = "tertiary"      # 20-40% attribution (default 35%)
    NONE = "none"              # 0%


ATTRIBUTION_WEIGHTS = {
    CausalStrength.PRIMARY: 1.00,
    CausalStrength.SECONDARY: 0.70,
    CausalStrength.TERTIARY: 0.35,
    CausalStrength.NONE: 0.00,
}


class FailureCategory(str, Enum):
    EXECUTION = "execution"      # Implementation design flaws
    ASSUMPTION = "assumption"    # Predicted behavior not occurring
    EMERGENCE = "emergence"      # Unintended organizational consequences


class PrecursorType(str, Enum):
    MISALIGNMENT = "misalignment"    # Capability gap, behavior resistance
    BOTTLENECK = "bottleneck"        # Technology constraint, process dependency
    CASCADE_FAILURE = "cascade_failure"  # Secondary impact creates unexpected consequence


class CausalMaturity(int, Enum):
    BASIC_TRACKING = 1       # 60% prediction accuracy
    CASCADE_INTELLIGENCE = 2  # 75% prediction accuracy
    ADAPTIVE_STRATEGY = 3    # 85% prediction accuracy
    LEARNING_INTEGRATION = 4  # 90%+ prediction accuracy


# ── Core data structures ──────────────────────────────────────────────


@dataclass
class CausalLink:
    link_id: str = field(default_factory=lambda: str(uuid4()))
    decision_id: str = ""
    source_system: str = ""
    target_system: str = ""
    layer: CausalLayer = CausalLayer.PRIMARY
    strength: CausalStrength = CausalStrength.PRIMARY
    description: str = ""
    predicted_outcome: str = ""
    actual_outcome: Optional[str] = None
    predicted_value: float = 0.0
    actual_value: Optional[float] = None


@dataclass
class CausalChain:
    chain_id: str = field(default_factory=lambda: str(uuid4()))
    decision_id: str = ""
    decision_name: str = ""
    links: list[CausalLink] = field(default_factory=list)
    total_predicted_value: float = 0.0
    total_actual_value: Optional[float] = None

    def links_at_layer(self, layer: CausalLayer) -> list[CausalLink]:
        return [lnk for lnk in self.links if lnk.layer == layer]


@dataclass
class Attribution:
    outcome_name: str
    outcome_value: float
    attributions: dict[str, float] = field(default_factory=dict)  # decision_id -> attributed value

    @property
    def total_attributed(self) -> float:
        return sum(self.attributions.values())


@dataclass
class FailureMode:
    failure_id: str = field(default_factory=lambda: str(uuid4()))
    category: FailureCategory = FailureCategory.EXECUTION
    precursor: PrecursorType = PrecursorType.MISALIGNMENT
    affected_layer: CausalLayer = CausalLayer.PRIMARY
    description: str = ""
    mitigation: str = ""
    detected: bool = False


@dataclass
class PredictionAccuracy:
    layer: CausalLayer
    predicted: float
    actual: float

    @property
    def accuracy(self) -> float:
        if self.predicted == 0:
            return 0.0
        return self.actual / self.predicted

    @property
    def confidence_adjustment(self) -> float:
        acc = self.accuracy
        if acc > 0.7:
            return 1.1  # increase confidence
        if acc < 0.5:
            return 0.8  # decrease confidence
        return 1.0


@dataclass
class CausalMapResult:
    chain: CausalChain
    attributions: list[Attribution] = field(default_factory=list)
    failure_modes: list[FailureMode] = field(default_factory=list)
    prediction_accuracies: list[PredictionAccuracy] = field(default_factory=list)
    maturity: CausalMaturity = CausalMaturity.BASIC_TRACKING


# ── Engine ─────────────────────────────────────────────────────────────


class CausalMapper:
    """Build and evaluate causal chains from decisions to outcomes."""

    def __init__(self) -> None:
        self._chains: dict[str, CausalChain] = {}

    def create_chain(
        self,
        decision_id: str,
        decision_name: str,
        links: list[CausalLink],
    ) -> CausalChain:
        for link in links:
            link.decision_id = decision_id

        chain = CausalChain(
            decision_id=decision_id,
            decision_name=decision_name,
            links=links,
            total_predicted_value=sum(lnk.predicted_value for lnk in links),
        )
        self._chains[chain.chain_id] = chain
        return chain

    def record_outcome(
        self,
        chain_id: str,
        link_id: str,
        actual_outcome: str,
        actual_value: float,
    ) -> CausalLink:
        chain = self._chains.get(chain_id)
        if not chain:
            raise ValueError(f"Chain {chain_id} not found")
        link = next((lnk for lnk in chain.links if lnk.link_id == link_id), None)
        if not link:
            raise ValueError(f"Link {link_id} not found in chain {chain_id}")
        link.actual_outcome = actual_outcome
        link.actual_value = actual_value
        # Recalculate chain total
        measured = [lnk for lnk in chain.links if lnk.actual_value is not None]
        if measured:
            chain.total_actual_value = sum(lnk.actual_value for lnk in measured)
        return link

    def calculate_attribution(
        self,
        outcome_name: str,
        outcome_value: float,
        contributing_decisions: list[tuple[str, CausalStrength]],
    ) -> Attribution:
        """Attribute outcome value across decisions by causal strength."""
        attributions: dict[str, float] = {}
        total_weight = sum(ATTRIBUTION_WEIGHTS[s] for _, s in contributing_decisions)
        if total_weight == 0:
            return Attribution(outcome_name=outcome_name, outcome_value=outcome_value)

        for decision_id, strength in contributing_decisions:
            weight = ATTRIBUTION_WEIGHTS[strength]
            attributed = outcome_value * (weight / total_weight)
            attributions[decision_id] = round(attributed, 2)

        return Attribution(
            outcome_name=outcome_name,
            outcome_value=outcome_value,
            attributions=attributions,
        )

    def detect_failure_modes(self, chain: CausalChain) -> list[FailureMode]:
        """Scan chain for precursor signals of failure."""
        modes: list[FailureMode] = []

        for link in chain.links:
            if link.actual_value is None:
                continue

            accuracy = link.actual_value / link.predicted_value if link.predicted_value else 0

            # Execution failure: actual < 50% of predicted
            if accuracy < 0.5:
                modes.append(FailureMode(
                    category=FailureCategory.EXECUTION,
                    precursor=PrecursorType.MISALIGNMENT,
                    affected_layer=link.layer,
                    description=f"Link {link.source_system}->{link.target_system}: "
                                f"actual ({link.actual_value}) < 50% of predicted ({link.predicted_value})",
                    mitigation="Investigate implementation design, resource adequacy",
                    detected=True,
                ))

            # Assumption failure: outcome present but wrong direction
            if link.actual_value < 0 and link.predicted_value > 0:
                modes.append(FailureMode(
                    category=FailureCategory.ASSUMPTION,
                    precursor=PrecursorType.BOTTLENECK,
                    affected_layer=link.layer,
                    description=f"Negative outcome where positive expected: {link.description}",
                    mitigation="Re-evaluate behavioral assumptions and environmental constraints",
                    detected=True,
                ))

        # Emergence failure: Layer 3+ outcomes significantly different from prediction
        l3_links = chain.links_at_layer(CausalLayer.TERTIARY)
        for link in l3_links:
            if link.actual_value is not None and link.predicted_value > 0:
                deviation = abs(link.actual_value - link.predicted_value) / link.predicted_value
                if deviation > 0.5:
                    modes.append(FailureMode(
                        category=FailureCategory.EMERGENCE,
                        precursor=PrecursorType.CASCADE_FAILURE,
                        affected_layer=CausalLayer.TERTIARY,
                        description=f"Layer 3 deviation {deviation:.0%}: {link.description}",
                        mitigation="Trigger failure mode cascade analysis",
                        detected=True,
                    ))

        return modes

    def evaluate_predictions(self, chain: CausalChain) -> list[PredictionAccuracy]:
        """Calculate prediction accuracy per layer."""
        accuracies: list[PredictionAccuracy] = []
        for layer in CausalLayer:
            links = chain.links_at_layer(layer)
            measured = [lnk for lnk in links if lnk.actual_value is not None]
            if not measured:
                continue
            total_predicted = sum(lnk.predicted_value for lnk in measured)
            total_actual = sum(lnk.actual_value for lnk in measured)  # type: ignore
            accuracies.append(PredictionAccuracy(
                layer=layer,
                predicted=total_predicted,
                actual=total_actual,
            ))
        return accuracies

    def assess_maturity(self, accuracies: list[PredictionAccuracy]) -> CausalMaturity:
        if not accuracies:
            return CausalMaturity.BASIC_TRACKING
        avg_accuracy = sum(a.accuracy for a in accuracies) / len(accuracies)
        if avg_accuracy >= 0.90:
            return CausalMaturity.LEARNING_INTEGRATION
        if avg_accuracy >= 0.85:
            return CausalMaturity.ADAPTIVE_STRATEGY
        if avg_accuracy >= 0.75:
            return CausalMaturity.CASCADE_INTELLIGENCE
        return CausalMaturity.BASIC_TRACKING

    def full_analysis(self, chain_id: str) -> CausalMapResult:
        chain = self._chains.get(chain_id)
        if not chain:
            raise ValueError(f"Chain {chain_id} not found")

        failure_modes = self.detect_failure_modes(chain)
        accuracies = self.evaluate_predictions(chain)
        maturity = self.assess_maturity(accuracies)

        return CausalMapResult(
            chain=chain,
            failure_modes=failure_modes,
            prediction_accuracies=accuracies,
            maturity=maturity,
        )
