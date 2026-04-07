"""Outcome Analysis Reporter.

Generates executive dashboard data and gate assessment reports from
PHASE_5_3_OUTCOME_ANALYSIS_REPORT_TEMPLATES.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .governance_gates import (
    CriterionStatus,
    GateAssessment,
    GateNumber,
)
from .ovs_engine import OVSResult, SystemScore


# ── Dashboard components ──────────────────────────────────────────────


@dataclass
class OVSTrendPoint:
    label: str  # "Baseline", "Day 30", "Day 60", "Day 90"
    composite_ovs: float
    people: float
    process: float
    technology: float
    learning: float
    confidence_interval: float = 3.0  # ± points


@dataclass
class DimensionPanel:
    system_name: str
    score: float
    gate_threshold: float
    status: CriterionStatus
    trend: str  # "improving", "stable", "declining"


@dataclass
class TrafficLightItem:
    criterion: str
    measured: float
    threshold: float
    status: CriterionStatus


@dataclass
class EscalationAlert:
    metric: str
    actual: float
    threshold: float
    owner: str
    timeline_hours: int
    active: bool


@dataclass
class GateSummary:
    gate: GateNumber
    status: str  # "PASS", "AT_RISK", "FAIL"
    decision: str
    days_until_next_gate: Optional[int]


@dataclass
class ExecutiveDashboard:
    generated_at: str = ""
    ovs_trend: list[OVSTrendPoint] = field(default_factory=list)
    dimension_panels: list[DimensionPanel] = field(default_factory=list)
    traffic_lights: list[TrafficLightItem] = field(default_factory=list)
    escalation_alerts: list[EscalationAlert] = field(default_factory=list)
    gate_summary: Optional[GateSummary] = None


# ── Gate assessment report ────────────────────────────────────────────


@dataclass
class GateAssessmentReport:
    gate: GateNumber
    criteria_results: list[dict] = field(default_factory=list)
    escalation_triggers: list[dict] = field(default_factory=list)
    recommended_decision: str = ""
    decision_authority: str = ""
    ovs_composite: Optional[float] = None
    pass_count: int = 0
    at_risk_count: int = 0
    fail_count: int = 0
    overall_status: str = ""


# ── Reporter ──────────────────────────────────────────────────────────


class OutcomeReporter:
    """Generate executive dashboards and gate assessment reports."""

    def build_dashboard(
        self,
        ovs_history: list[tuple[str, OVSResult]],  # (label, OVSResult) pairs
        current_gate: Optional[GateAssessment] = None,
        current_day: int = 0,
    ) -> ExecutiveDashboard:
        dashboard = ExecutiveDashboard()

        # OVS trend
        for label, ovs in ovs_history:
            dashboard.ovs_trend.append(OVSTrendPoint(
                label=label,
                composite_ovs=ovs.composite_ovs,
                people=ovs.people_score.score,
                process=ovs.process_score.score,
                technology=ovs.technology_score.score,
                learning=ovs.learning_score.score,
            ))

        # Dimension panels from latest OVS
        if ovs_history:
            _, latest = ovs_history[-1]
            for sys_score in [
                latest.people_score,
                latest.process_score,
                latest.technology_score,
                latest.learning_score,
            ]:
                trend = self._determine_trend(sys_score, ovs_history)
                threshold = self._gate_threshold_for_day(current_day)
                status = (
                    CriterionStatus.PASS if sys_score.score >= threshold
                    else CriterionStatus.AT_RISK if sys_score.score >= threshold * 0.8
                    else CriterionStatus.FAIL
                )
                dashboard.dimension_panels.append(DimensionPanel(
                    system_name=sys_score.name,
                    score=sys_score.score,
                    gate_threshold=threshold,
                    status=status,
                    trend=trend,
                ))

        # Traffic lights from gate criteria
        if current_gate:
            for c in current_gate.criteria:
                dashboard.traffic_lights.append(TrafficLightItem(
                    criterion=c.name,
                    measured=c.measured_value,
                    threshold=c.pass_threshold,
                    status=c.status,
                ))

            # Escalation alerts
            for e in current_gate.escalations:
                if e.triggered:
                    dashboard.escalation_alerts.append(EscalationAlert(
                        metric=e.metric,
                        actual=e.actual,
                        threshold=e.threshold,
                        owner=e.response_owner,
                        timeline_hours=e.timeline_hours,
                        active=True,
                    ))

            # Gate summary
            if current_gate.decision:
                next_gate_day = {
                    GateNumber.GATE_1: 60,
                    GateNumber.GATE_2: 90,
                    GateNumber.GATE_3: None,
                }.get(current_gate.gate)
                days_until = next_gate_day - current_day if next_gate_day else None

                overall = "PASS" if not current_gate.any_fail else "FAIL"
                if not current_gate.any_fail and any(
                    c.status == CriterionStatus.AT_RISK for c in current_gate.criteria
                ):
                    overall = "AT_RISK"

                dashboard.gate_summary = GateSummary(
                    gate=current_gate.gate,
                    status=overall,
                    decision=current_gate.decision.value,
                    days_until_next_gate=days_until,
                )

        return dashboard

    def generate_gate_report(self, assessment: GateAssessment) -> GateAssessmentReport:
        criteria_results = []
        pass_count = at_risk_count = fail_count = 0

        for c in assessment.criteria:
            criteria_results.append({
                "name": c.name,
                "measured": c.measured_value,
                "pass_threshold": c.pass_threshold,
                "at_risk_threshold": c.at_risk_threshold,
                "status": c.status.value,
            })
            if c.status == CriterionStatus.PASS:
                pass_count += 1
            elif c.status == CriterionStatus.AT_RISK:
                at_risk_count += 1
            else:
                fail_count += 1

        escalation_triggers = [
            {
                "metric": e.metric,
                "threshold": e.threshold,
                "actual": e.actual,
                "level": e.escalation_level.value,
                "owner": e.response_owner,
                "timeline_hours": e.timeline_hours,
                "triggered": e.triggered,
            }
            for e in assessment.escalations
        ]

        overall = "PASS"
        if fail_count > 0:
            overall = "FAIL"
        elif at_risk_count > 0:
            overall = "AT_RISK"

        return GateAssessmentReport(
            gate=assessment.gate,
            criteria_results=criteria_results,
            escalation_triggers=escalation_triggers,
            recommended_decision=assessment.decision.value if assessment.decision else "",
            decision_authority=assessment.decision_authority.value,
            ovs_composite=assessment.ovs_composite,
            pass_count=pass_count,
            at_risk_count=at_risk_count,
            fail_count=fail_count,
            overall_status=overall,
        )

    @staticmethod
    def _determine_trend(
        current: SystemScore,
        history: list[tuple[str, OVSResult]],
    ) -> str:
        if len(history) < 2:
            return "stable"
        # Compare current to previous
        prev_ovs = history[-2][1]
        prev_scores = {
            "People": prev_ovs.people_score.score,
            "Process": prev_ovs.process_score.score,
            "Technology": prev_ovs.technology_score.score,
            "Learning": prev_ovs.learning_score.score,
        }
        prev = prev_scores.get(current.name, current.score)
        delta = current.score - prev
        if delta > 0.02:
            return "improving"
        if delta < -0.02:
            return "declining"
        return "stable"

    @staticmethod
    def _gate_threshold_for_day(day: int) -> float:
        """OVS threshold on 0–1 scale for current gate."""
        if day <= 30:
            return 0.55  # Gate 1: OVS ≥ 55/100 → 0.55 on 0-1 raw
        if day <= 60:
            return 0.65
        return 0.75
