"""Value Leakage Detector.

Implements automated leakage detection from DECISION_ENGINE_FRAMEWORK.md and
DATA_VALUE_MATRIX_SCHEMA.md.

Annual_Value_Loss = Sum(AOV × System_Weight × (1 - Dimension_Score) × Days/365 × Cascade_Multiplier)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .ovs_engine import OVSResult


class EscalationLevel(int, Enum):
    LEVEL_1_AUTOMATED = 1   # real-time, <24h
    LEVEL_2_DEPARTMENT = 2  # 48h response
    LEVEL_3_EXECUTIVE = 3   # 72h response


class LeakageRuleType(str, Enum):
    SINGLE_DIMENSION = "single_dimension"
    MULTI_CASCADE = "multi_cascade"
    TREND_EARLY_WARNING = "trend_early_warning"
    BOTTLENECK = "bottleneck"


CASCADE_MULTIPLIERS = {
    1: 1.0,
    2: 1.3,
    3: 1.7,
    4: 2.2,
}

SYSTEM_WEIGHTS = {
    "People": 0.30,
    "Process": 0.25,
    "Technology": 0.25,
    "Learning": 0.20,
}

# Dependency chains: system A enables system B
DEPENDENCY_CHAIN = {
    "People": ("Process", 0.8),
    "Process": ("Technology", 0.7),
    "Technology": ("Learning", 0.6),
    "Learning": ("People", 0.75),
}


@dataclass
class LeakageAlert:
    rule_type: LeakageRuleType
    system_name: str
    dimension: str
    estimated_annual_loss: float
    cascade_multiplier: float
    escalation_level: EscalationLevel
    description: str
    severity: str  # critical / warning / info


@dataclass
class LeakageReport:
    total_estimated_annual_loss: float
    alerts: list[LeakageAlert] = field(default_factory=list)
    systems_in_leakage: int = 0
    cascade_multiplier_applied: float = 1.0


class ValueLeakageDetector:
    """Detect value leakage across organizational systems."""

    def __init__(
        self,
        annual_org_value: float = 1_000_000.0,
        single_dim_threshold: float = 0.5,
        system_threshold: float = 0.6,
        trend_decline_threshold: float = -0.05,
    ) -> None:
        self.annual_org_value = annual_org_value
        self.single_dim_threshold = single_dim_threshold
        self.system_threshold = system_threshold
        self.trend_decline_threshold = trend_decline_threshold

    def detect(self, ovs: OVSResult) -> LeakageReport:
        alerts: list[LeakageAlert] = []
        scores = {
            "People": ovs.people_score,
            "Process": ovs.process_score,
            "Technology": ovs.technology_score,
            "Learning": ovs.learning_score,
        }

        # Count systems in leakage
        leaking_systems = [
            name for name, s in scores.items() if s.score < self.system_threshold
        ]
        n_leaking = len(leaking_systems)
        cascade_mult = CASCADE_MULTIPLIERS.get(n_leaking, CASCADE_MULTIPLIERS[4])

        # Rule 1: Single-dimension leakage
        for name, sys_score in scores.items():
            for dim_name, dim_val in sys_score.dimensions.items():
                if dim_val < self.single_dim_threshold:
                    loss = (
                        self.annual_org_value
                        * SYSTEM_WEIGHTS[name]
                        * (1 - dim_val)
                        * cascade_mult
                    )
                    alerts.append(LeakageAlert(
                        rule_type=LeakageRuleType.SINGLE_DIMENSION,
                        system_name=name,
                        dimension=dim_name,
                        estimated_annual_loss=round(loss, 2),
                        cascade_multiplier=cascade_mult,
                        escalation_level=EscalationLevel.LEVEL_1_AUTOMATED,
                        description=f"{name}.{dim_name} at {dim_val:.2f} (< {self.single_dim_threshold})",
                        severity="critical" if dim_val < 0.3 else "warning",
                    ))

        # Rule 2: Multi-system cascade
        if n_leaking >= 2:
            total_cascade_loss = sum(
                self.annual_org_value * SYSTEM_WEIGHTS[name] * (1 - scores[name].score) * cascade_mult
                for name in leaking_systems
            )
            alerts.append(LeakageAlert(
                rule_type=LeakageRuleType.MULTI_CASCADE,
                system_name=", ".join(leaking_systems),
                dimension="system_level",
                estimated_annual_loss=round(total_cascade_loss, 2),
                cascade_multiplier=cascade_mult,
                escalation_level=EscalationLevel.LEVEL_2_DEPARTMENT,
                description=f"{n_leaking} systems in cascade leakage: {', '.join(leaking_systems)}",
                severity="critical",
            ))

        # Rule 3: Trend-based early warning
        for name, sys_score in scores.items():
            if sys_score.trend is not None and sys_score.trend < self.trend_decline_threshold:
                projected_loss = (
                    self.annual_org_value
                    * SYSTEM_WEIGHTS[name]
                    * abs(sys_score.trend)
                    * 4  # annualize weekly trend
                )
                alerts.append(LeakageAlert(
                    rule_type=LeakageRuleType.TREND_EARLY_WARNING,
                    system_name=name,
                    dimension="trend",
                    estimated_annual_loss=round(projected_loss, 2),
                    cascade_multiplier=1.0,
                    escalation_level=EscalationLevel.LEVEL_1_AUTOMATED,
                    description=f"{name} declining {sys_score.trend:.1%} WoW",
                    severity="warning",
                ))

        # Rule 4: Bottleneck detection
        for primary, (dependent, dep_weight) in DEPENDENCY_CHAIN.items():
            p_score = scores[primary]
            d_score = scores[dependent]
            if p_score.score >= 0.6 and d_score.score < 0.5:
                bottleneck_loss = (
                    self.annual_org_value
                    * SYSTEM_WEIGHTS[dependent]
                    * (1 - d_score.score)
                    * dep_weight
                )
                alerts.append(LeakageAlert(
                    rule_type=LeakageRuleType.BOTTLENECK,
                    system_name=dependent,
                    dimension=f"blocked_by_{primary}",
                    estimated_annual_loss=round(bottleneck_loss, 2),
                    cascade_multiplier=dep_weight,
                    escalation_level=EscalationLevel.LEVEL_2_DEPARTMENT,
                    description=f"{primary} healthy but {dependent} degrading — dependency bottleneck",
                    severity="warning",
                ))

        total_loss = sum(a.estimated_annual_loss for a in alerts)

        return LeakageReport(
            total_estimated_annual_loss=round(total_loss, 2),
            alerts=alerts,
            systems_in_leakage=n_leaking,
            cascade_multiplier_applied=cascade_mult,
        )
