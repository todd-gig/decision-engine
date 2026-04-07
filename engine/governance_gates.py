"""Governance Gate Engine.

Implements 30/60/90-day gate assessment from LAYER_TRACKING_IMPLEMENTATION_PLAYBOOKS.md,
PHASE_5_3_OUTCOME_ANALYSIS_REPORT_TEMPLATES.md, and PHASE_5_3_1_90_DAY_GATE_TEMPLATE.md.

Three gates with PASS / AT_RISK / FAIL classification.
No subjective assessments — all thresholds are quantified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GateNumber(int, Enum):
    GATE_1 = 1   # Day 30: Layer 1 Primary Impact
    GATE_2 = 2   # Day 60: Layer 2 Secondary Impact
    GATE_3 = 3   # Day 90: Layer 3 Tertiary Impact


class CriterionStatus(str, Enum):
    PASS = "pass"
    AT_RISK = "at_risk"
    FAIL = "fail"


class GateDecision(str, Enum):
    # Gate 1
    PROCEED = "proceed"
    CONTINUE_WITH_EXTENSIONS = "continue_with_extensions"
    PAUSE_FOR_REMEDIATION = "pause_for_remediation"
    ROLLBACK = "rollback"
    # Gate 2
    FULL_INVESTMENT = "full_layer3_investment"
    PHASED_INVESTMENT = "phased_layer3_investment"
    EXTEND_LAYER2 = "extend_layer2_with_modifications"
    MONITORING_ONLY = "minimal_layer3_monitoring_only"
    REMEDIATE = "remediate"
    # Gate 3
    FINALIZE = "finalize"
    CONTINUE = "continue"
    # REMEDIATE and ROLLBACK reused


class EscalationLevel(int, Enum):
    LEVEL_1_TEAM_LEAD = 1     # 24h response
    LEVEL_2_DEPARTMENT = 2    # 48h response
    LEVEL_3_EXECUTIVE = 3     # 72h response


class AuthorityLevel(str, Enum):
    TEAM_LEAD = "team_lead"
    DEPARTMENT_HEAD = "department_head"
    EXECUTIVE = "executive"
    BOARD = "board"


# ── Data structures ───────────────────────────────────────────────────


@dataclass
class CriterionResult:
    name: str
    measured_value: float
    pass_threshold: float
    at_risk_threshold: float  # 80% of pass_threshold
    status: CriterionStatus = CriterionStatus.PASS

    def evaluate(self) -> CriterionStatus:
        if self.measured_value >= self.pass_threshold:
            self.status = CriterionStatus.PASS
        elif self.measured_value >= self.at_risk_threshold:
            self.status = CriterionStatus.AT_RISK
        else:
            self.status = CriterionStatus.FAIL
        return self.status


@dataclass
class EscalationTrigger:
    metric: str
    threshold: float
    actual: float
    escalation_level: EscalationLevel
    response_owner: str
    timeline_hours: int
    triggered: bool = False


@dataclass
class GateAssessment:
    gate: GateNumber
    criteria: list[CriterionResult] = field(default_factory=list)
    escalations: list[EscalationTrigger] = field(default_factory=list)
    decision: Optional[GateDecision] = None
    decision_authority: AuthorityLevel = AuthorityLevel.TEAM_LEAD
    ovs_composite: Optional[float] = None
    notes: str = ""

    @property
    def all_pass(self) -> bool:
        return all(c.status == CriterionStatus.PASS for c in self.criteria)

    @property
    def any_fail(self) -> bool:
        return any(c.status == CriterionStatus.FAIL for c in self.criteria)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.criteria if c.status == CriterionStatus.FAIL)


# ── Gate input structures ─────────────────────────────────────────────


@dataclass
class Gate1Inputs:
    adoption_rate: float = 0.0         # 0–1
    critical_failure_rate: float = 0.0  # 0–1
    schedule_slip_rate: float = 0.0     # 0–1 (0 = on schedule)
    resource_deployment_rate: float = 0.0  # 0–1


@dataclass
class Gate2Inputs:
    efficiency_gain: float = 0.0          # 0–1
    behavioral_alignment: float = 0.0      # 0–1
    new_critical_failures_per_week: float = 0.0
    cascade_materialization_rate: float = 0.0  # 0–1


@dataclass
class Gate3Inputs:
    behavioral_alignment_sustained: float = 0.0  # 0–1
    structural_adaptation_complete: bool = False
    compound_value_improvement: float = 0.0       # 0–1
    ovs_composite: float = 0.0                     # 0–100


# ── Engine ─────────────────────────────────────────────────────────────


class GovernanceGateEngine:
    """Evaluate 30/60/90-day governance gates with quantified thresholds."""

    def evaluate_gate1(self, inputs: Gate1Inputs) -> GateAssessment:
        criteria = [
            CriterionResult("adoption_rate", inputs.adoption_rate, 0.60, 0.48),
            CriterionResult("critical_failures", 1 - inputs.critical_failure_rate, 0.95, 0.92),
            CriterionResult("execution_velocity", 1 - inputs.schedule_slip_rate, 0.80, 0.64),
            CriterionResult("resource_alignment", inputs.resource_deployment_rate, 0.80, 0.60),
        ]
        for c in criteria:
            c.evaluate()

        escalations = self._gate1_escalations(inputs)
        assessment = GateAssessment(gate=GateNumber.GATE_1, criteria=criteria, escalations=escalations)
        assessment.decision = self._decide_gate1(assessment)
        assessment.decision_authority = (
            AuthorityLevel.DEPARTMENT_HEAD if assessment.any_fail
            else AuthorityLevel.TEAM_LEAD
        )
        return assessment

    def evaluate_gate2(self, inputs: Gate2Inputs) -> GateAssessment:
        criteria = [
            CriterionResult("efficiency_gains", inputs.efficiency_gain, 0.15, 0.12),
            CriterionResult("behavioral_alignment", inputs.behavioral_alignment, 0.70, 0.56),
            CriterionResult("system_stability", max(0, 1 - inputs.new_critical_failures_per_week / 3), 1.0, 0.67),
            CriterionResult("cascade_materialization", inputs.cascade_materialization_rate, 0.75, 0.60),
        ]
        for c in criteria:
            c.evaluate()

        escalations = self._gate2_escalations(inputs)
        assessment = GateAssessment(gate=GateNumber.GATE_2, criteria=criteria, escalations=escalations)
        assessment.decision = self._decide_gate2(assessment)
        assessment.decision_authority = (
            AuthorityLevel.EXECUTIVE if assessment.fail_count >= 2
            else AuthorityLevel.DEPARTMENT_HEAD
        )
        return assessment

    def evaluate_gate3(self, inputs: Gate3Inputs) -> GateAssessment:
        structural_score = 1.0 if inputs.structural_adaptation_complete else 0.4
        criteria = [
            CriterionResult("behavioral_alignment_sustained", inputs.behavioral_alignment_sustained, 0.75, 0.60),
            CriterionResult("structural_adaptation", structural_score, 0.90, 0.72),
            CriterionResult("compound_value_creation", inputs.compound_value_improvement, 0.25, 0.20),
        ]
        for c in criteria:
            c.evaluate()

        escalations = self._gate3_escalations(inputs)
        assessment = GateAssessment(
            gate=GateNumber.GATE_3,
            criteria=criteria,
            escalations=escalations,
            ovs_composite=inputs.ovs_composite,
        )
        assessment.decision = self._decide_gate3(assessment, inputs)
        assessment.decision_authority = AuthorityLevel.EXECUTIVE
        return assessment

    # ── Decision logic ─────────────────────────────────────────────────

    @staticmethod
    def _decide_gate1(assessment: GateAssessment) -> GateDecision:
        if assessment.all_pass:
            return GateDecision.PROCEED
        if assessment.fail_count == 1:
            return GateDecision.CONTINUE_WITH_EXTENSIONS
        if assessment.fail_count >= 2:
            # Check if adoption or critical failures are the ones failing
            critical_fails = [c for c in assessment.criteria if c.status == CriterionStatus.FAIL]
            fail_names = {c.name for c in critical_fails}
            if "adoption_rate" in fail_names and "critical_failures" in fail_names:
                return GateDecision.ROLLBACK
            return GateDecision.PAUSE_FOR_REMEDIATION
        return GateDecision.CONTINUE_WITH_EXTENSIONS

    @staticmethod
    def _decide_gate2(assessment: GateAssessment) -> GateDecision:
        if assessment.all_pass:
            return GateDecision.FULL_INVESTMENT
        statuses = {c.name: c.status for c in assessment.criteria}
        if statuses.get("behavioral_alignment") == CriterionStatus.AT_RISK:
            return GateDecision.PHASED_INVESTMENT
        if assessment.fail_count == 1:
            return GateDecision.EXTEND_LAYER2
        if assessment.fail_count >= 2:
            return GateDecision.REMEDIATE
        return GateDecision.MONITORING_ONLY

    @staticmethod
    def _decide_gate3(assessment: GateAssessment, inputs: Gate3Inputs) -> GateDecision:
        if assessment.all_pass and inputs.ovs_composite >= 75:
            return GateDecision.FINALIZE
        if inputs.ovs_composite >= 55 and assessment.fail_count == 0:
            return GateDecision.CONTINUE
        if assessment.fail_count <= 1 and inputs.behavioral_alignment_sustained >= 0.60:
            return GateDecision.REMEDIATE
        return GateDecision.ROLLBACK

    # ── Escalation triggers ────────────────────────────────────────────

    @staticmethod
    def _gate1_escalations(inputs: Gate1Inputs) -> list[EscalationTrigger]:
        triggers: list[EscalationTrigger] = []
        if inputs.adoption_rate < 0.50:
            triggers.append(EscalationTrigger(
                "adoption_rate", 0.50, inputs.adoption_rate,
                EscalationLevel.LEVEL_1_TEAM_LEAD, "Team Lead", 24, triggered=True,
            ))
        if inputs.critical_failure_rate > 0.08:
            triggers.append(EscalationTrigger(
                "critical_failures", 0.08, inputs.critical_failure_rate,
                EscalationLevel.LEVEL_2_DEPARTMENT, "Department Head", 48, triggered=True,
            ))
        if inputs.schedule_slip_rate > 0.15:
            triggers.append(EscalationTrigger(
                "schedule_slip", 0.15, inputs.schedule_slip_rate,
                EscalationLevel.LEVEL_2_DEPARTMENT, "PM + Director", 48, triggered=True,
            ))
        if inputs.resource_deployment_rate < 0.50:
            triggers.append(EscalationTrigger(
                "resource_deployment", 0.50, inputs.resource_deployment_rate,
                EscalationLevel.LEVEL_1_TEAM_LEAD, "Team Lead", 24, triggered=True,
            ))
        return triggers

    @staticmethod
    def _gate2_escalations(inputs: Gate2Inputs) -> list[EscalationTrigger]:
        triggers: list[EscalationTrigger] = []
        if inputs.efficiency_gain < 0.10:
            triggers.append(EscalationTrigger(
                "efficiency_gains", 0.10, inputs.efficiency_gain,
                EscalationLevel.LEVEL_1_TEAM_LEAD, "Ops Lead", 24, triggered=True,
            ))
        if inputs.new_critical_failures_per_week > 2:
            triggers.append(EscalationTrigger(
                "critical_failures_weekly", 2.0, inputs.new_critical_failures_per_week,
                EscalationLevel.LEVEL_2_DEPARTMENT, "CTO", 48, triggered=True,
            ))
        if inputs.behavioral_alignment < 0.65:
            triggers.append(EscalationTrigger(
                "behavioral_alignment", 0.65, inputs.behavioral_alignment,
                EscalationLevel.LEVEL_2_DEPARTMENT, "HR Lead", 48, triggered=True,
            ))
        return triggers

    @staticmethod
    def _gate3_escalations(inputs: Gate3Inputs) -> list[EscalationTrigger]:
        triggers: list[EscalationTrigger] = []
        if inputs.behavioral_alignment_sustained < 0.70:
            triggers.append(EscalationTrigger(
                "behavioral_alignment_sustained", 0.70, inputs.behavioral_alignment_sustained,
                EscalationLevel.LEVEL_2_DEPARTMENT, "HR Lead", 48, triggered=True,
            ))
        if inputs.compound_value_improvement < 0.20:
            triggers.append(EscalationTrigger(
                "compound_value", 0.20, inputs.compound_value_improvement,
                EscalationLevel.LEVEL_3_EXECUTIVE, "Executive", 72, triggered=True,
            ))
        if inputs.ovs_composite < 45:
            triggers.append(EscalationTrigger(
                "ovs_composite", 45.0, inputs.ovs_composite,
                EscalationLevel.LEVEL_3_EXECUTIVE, "Executive + Board", 72, triggered=True,
            ))
        return triggers
