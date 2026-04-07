"""ROI Calculation Engine.

Implements the ROI framework from DECISION_ENGINE_FRAMEWORK.md.

ROI_Score = (Impact_Value / Total_Cost) × (1 + Leverage_Factor) × (1 - Risk_Factor)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LeverageScope(str, Enum):
    SINGLE_SYSTEM = "single_system"      # 0.1
    TWO_SYSTEMS = "two_systems"          # 0.3
    THREE_SYSTEMS = "three_systems"      # 0.6


LEVERAGE_FACTORS = {
    LeverageScope.SINGLE_SYSTEM: 0.1,
    LeverageScope.TWO_SYSTEMS: 0.3,
    LeverageScope.THREE_SYSTEMS: 0.6,
}


@dataclass
class ImplementationCost:
    personnel_cost: float = 0.0
    capital_cost: float = 0.0
    coordination_cost: float = 0.0
    opportunity_cost: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.personnel_cost
            + self.capital_cost
            + self.coordination_cost
            + self.opportunity_cost
        )


@dataclass
class ROIInput:
    name: str
    annual_leakage_loss: float
    expected_performance_after: float  # 0–1 (new performance level)
    implementation_cost: ImplementationCost
    leverage_scope: LeverageScope = LeverageScope.SINGLE_SYSTEM
    confidence: float = 0.8          # 0–1
    complexity_score: float = 0.5    # 0–1
    org_readiness_gap: float = 0.2   # 0–1
    required_hours: float = 100.0
    strategic_urgency: float = 0.5   # 0–1 (for ranking)
    is_dependency_blocker: bool = False


@dataclass
class ROIResult:
    name: str
    impact_value: float
    total_cost: float
    roi_score: float
    leverage_factor: float
    risk_factor: float
    value_per_hour: float
    passes_threshold: bool  # ROI >= 1.5
    rank: int = 0


@dataclass
class ROIPortfolio:
    results: list[ROIResult] = field(default_factory=list)
    total_impact: float = 0.0
    total_cost: float = 0.0
    portfolio_roi: float = 0.0


class ROIEngine:
    """Calculate and rank ROI for improvement initiatives."""

    def __init__(self, min_roi_threshold: float = 1.5) -> None:
        self.min_roi_threshold = min_roi_threshold

    def calculate(self, inp: ROIInput) -> ROIResult:
        impact_value = inp.annual_leakage_loss * (1 - inp.expected_performance_after)

        total_cost = inp.implementation_cost.total
        if total_cost <= 0:
            total_cost = 1.0  # prevent division by zero

        leverage_factor = LEVERAGE_FACTORS[inp.leverage_scope]

        confidence_inverse = 1 - inp.confidence
        risk_factor = (
            confidence_inverse * 0.3
            + inp.complexity_score * 0.4
            + inp.org_readiness_gap * 0.3
        )

        roi_score = (impact_value / total_cost) * (1 + leverage_factor) * (1 - risk_factor)

        value_per_hour = impact_value / max(inp.required_hours, 1)

        return ROIResult(
            name=inp.name,
            impact_value=round(impact_value, 2),
            total_cost=round(total_cost, 2),
            roi_score=round(roi_score, 4),
            leverage_factor=leverage_factor,
            risk_factor=round(risk_factor, 4),
            value_per_hour=round(value_per_hour, 2),
            passes_threshold=roi_score >= self.min_roi_threshold,
        )

    def rank_portfolio(self, inputs: list[ROIInput]) -> ROIPortfolio:
        """Calculate ROI for all inputs, filter, and rank."""
        results = [self.calculate(inp) for inp in inputs]

        # Multi-key sort: dependency blockers first, then ROI, urgency, value_per_hour
        input_map = {inp.name: inp for inp in inputs}
        results.sort(
            key=lambda r: (
                input_map[r.name].is_dependency_blocker,  # blockers first
                r.roi_score,
                input_map[r.name].strategic_urgency,
                r.value_per_hour,
            ),
            reverse=True,
        )

        for i, r in enumerate(results):
            r.rank = i + 1

        passing = [r for r in results if r.passes_threshold]
        total_impact = sum(r.impact_value for r in passing)
        total_cost = sum(r.total_cost for r in passing)
        portfolio_roi = total_impact / total_cost if total_cost > 0 else 0.0

        return ROIPortfolio(
            results=results,
            total_impact=round(total_impact, 2),
            total_cost=round(total_cost, 2),
            portfolio_roi=round(portfolio_roi, 4),
        )

    def allocate_resources(
        self,
        portfolio: ROIPortfolio,
        available_hours: float,
    ) -> list[ROIResult]:
        """Greedy allocation by value_per_hour within available capacity."""
        allocated: list[ROIResult] = []
        remaining = available_hours

        # Already ranked by priority — allocate in order
        for r in portfolio.results:
            if not r.passes_threshold:
                continue
            # Estimate hours from total_cost (rough proxy)
            est_hours = r.total_cost / max(r.value_per_hour, 1) if r.value_per_hour > 0 else remaining + 1
            if est_hours <= remaining:
                allocated.append(r)
                remaining -= est_hours

        return allocated
