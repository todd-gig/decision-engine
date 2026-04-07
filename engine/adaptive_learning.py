"""Adaptive Learning Loop Architecture.

Implements 4 learning engines from ADAPTIVE_LEARNING_LOOP_ARCHITECTURE.md:
1. Causal Model Calibration
2. OVS Projection Refinement
3. Decision Velocity Benchmarking
4. Authority Calibration

Plus Learning Value Index (LVI) progression and threshold calibration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LVIStage(int, Enum):
    DECISION_RECORDING = 1      # LVI 10-20
    PATTERN_IDENTIFICATION = 2   # LVI 20-35
    CAUSAL_TEMPLATE = 3          # LVI 35-55
    PREDICTIVE_REFINEMENT = 4    # LVI 55-75
    ORG_CAPABILITY = 5           # LVI 75-90


LVI_RANGES = {
    LVIStage.DECISION_RECORDING: (10, 20),
    LVIStage.PATTERN_IDENTIFICATION: (20, 35),
    LVIStage.CAUSAL_TEMPLATE: (35, 55),
    LVIStage.PREDICTIVE_REFINEMENT: (55, 75),
    LVIStage.ORG_CAPABILITY: (75, 90),
}

# Advancement criteria: (min_decisions, min_accuracy)
ADVANCEMENT_CRITERIA = {
    LVIStage.DECISION_RECORDING: (10, 0.0),
    LVIStage.PATTERN_IDENTIFICATION: (10, 0.70),
    LVIStage.CAUSAL_TEMPLATE: (20, 0.75),
    LVIStage.PREDICTIVE_REFINEMENT: (50, 0.85),
    LVIStage.ORG_CAPABILITY: (100, 0.90),
}


@dataclass
class AccuracyRecord:
    decision_type: str
    predicted: float
    actual: float

    @property
    def accuracy(self) -> float:
        return self.actual / self.predicted if self.predicted != 0 else 0.0


@dataclass
class LearningMetrics:
    total_decisions: int = 0
    decisions_with_outcomes: int = 0
    overall_accuracy: float = 0.0
    accuracy_by_type: dict[str, float] = field(default_factory=dict)
    pattern_library_usage: float = 0.0  # 0–1
    escalation_accuracy: float = 0.0    # 0–1
    false_alarm_rate: float = 0.0       # 0–1
    lvi_score: float = 10.0
    lvi_stage: LVIStage = LVIStage.DECISION_RECORDING


@dataclass
class CalibrationResult:
    engine_name: str
    adjustments: dict[str, float] = field(default_factory=dict)
    confidence_delta: float = 0.0
    recalibration_triggered: bool = False
    reason: str = ""


@dataclass
class ThresholdCalibration:
    threshold_name: str
    old_value: float
    new_value: float
    reason: str


# ── Learning Engines ──────────────────────────────────────────────────


class CausalModelCalibration:
    """Engine 1: Refine causal model weights based on outcome data."""

    def calibrate(
        self,
        records: list[AccuracyRecord],
        current_weights: dict[str, float],
    ) -> CalibrationResult:
        if not records:
            return CalibrationResult(engine_name="causal_model_calibration")

        adjustments: dict[str, float] = {}
        by_type: dict[str, list[AccuracyRecord]] = {}
        for r in records:
            by_type.setdefault(r.decision_type, []).append(r)

        for dtype, recs in by_type.items():
            avg_accuracy = sum(r.accuracy for r in recs) / len(recs)
            current_w = current_weights.get(dtype, 1.0)
            if avg_accuracy > 0.85:
                adjustments[dtype] = current_w * 1.05  # increase weight
            elif avg_accuracy < 0.60:
                adjustments[dtype] = current_w * 0.90  # decrease weight
            else:
                adjustments[dtype] = current_w  # no change

        overall_accuracy = sum(r.accuracy for r in records) / len(records)
        recalibrate = overall_accuracy < 0.70

        return CalibrationResult(
            engine_name="causal_model_calibration",
            adjustments=adjustments,
            confidence_delta=overall_accuracy - 0.80,
            recalibration_triggered=recalibrate,
            reason="Overall accuracy below 70%" if recalibrate else "Within acceptable range",
        )


class OVSProjectionRefinement:
    """Engine 2: Refine OVS projection accuracy from historical gate data."""

    def refine(
        self,
        gate_predictions: list[tuple[float, float]],  # (predicted_ovs, actual_ovs)
    ) -> CalibrationResult:
        if not gate_predictions:
            return CalibrationResult(engine_name="ovs_projection_refinement")

        errors = [(p - a) for p, a in gate_predictions]
        avg_bias = sum(errors) / len(errors)
        avg_abs_error = sum(abs(e) for e in errors) / len(errors)

        adjustments = {
            "bias_correction": -avg_bias,
            "avg_absolute_error": avg_abs_error,
            "prediction_count": float(len(gate_predictions)),
        }

        recalibrate = avg_abs_error > 5.0  # > 5 point average error

        return CalibrationResult(
            engine_name="ovs_projection_refinement",
            adjustments=adjustments,
            confidence_delta=-avg_abs_error / 100,
            recalibration_triggered=recalibrate,
            reason=f"Avg bias={avg_bias:.2f}, avg error={avg_abs_error:.2f}",
        )


class DecisionVelocityBenchmarking:
    """Engine 3: Benchmark and improve decision throughput and speed."""

    def benchmark(
        self,
        decision_times_hours: list[float],
        escalation_times_hours: list[float],
        target_decision_hours: float = 48.0,
        target_escalation_hours: float = 24.0,
    ) -> CalibrationResult:
        if not decision_times_hours:
            return CalibrationResult(engine_name="decision_velocity")

        avg_decision = sum(decision_times_hours) / len(decision_times_hours)
        avg_escalation = (
            sum(escalation_times_hours) / len(escalation_times_hours)
            if escalation_times_hours else 0
        )

        adjustments = {
            "avg_decision_hours": avg_decision,
            "avg_escalation_hours": avg_escalation,
            "decision_target_delta": avg_decision - target_decision_hours,
            "escalation_target_delta": avg_escalation - target_escalation_hours,
            "decisions_over_target": sum(1 for t in decision_times_hours if t > target_decision_hours),
        }

        recalibrate = avg_decision > target_decision_hours * 1.5

        return CalibrationResult(
            engine_name="decision_velocity",
            adjustments=adjustments,
            recalibration_triggered=recalibrate,
            reason=f"Avg decision time {avg_decision:.1f}h vs target {target_decision_hours}h",
        )


class AuthorityCalibration:
    """Engine 4: Calibrate escalation thresholds and authority assignments."""

    def calibrate(
        self,
        true_escalations: int,
        false_escalations: int,
        total_escalations: int,
        current_thresholds: dict[str, float],
        governance_level_weights: Optional[dict[str, float]] = None,
    ) -> CalibrationResult:
        if total_escalations == 0:
            return CalibrationResult(engine_name="authority_calibration")

        _ = governance_level_weights or {
            "level_1": 1.0, "level_2": 1.2, "level_3": 1.4
        }

        escalation_accuracy = true_escalations / total_escalations
        false_alarm_rate = false_escalations / total_escalations

        adjustments: dict[str, float] = {}
        recalibrate = False
        reasons: list[str] = []

        if escalation_accuracy < 0.85:
            recalibrate = True
            reasons.append(f"Escalation accuracy {escalation_accuracy:.1%} < 85%")
            # Tighten thresholds to reduce false alarms
            for k, v in current_thresholds.items():
                adjustments[k] = v * 0.95

        if false_alarm_rate > 0.10:
            recalibrate = True
            reasons.append(f"False alarm rate {false_alarm_rate:.1%} > 10%")
            for k, v in current_thresholds.items():
                adjustments.setdefault(k, v)
                adjustments[k] *= 0.92

        if not adjustments:
            adjustments = dict(current_thresholds)

        adjustments["escalation_accuracy"] = escalation_accuracy
        adjustments["false_alarm_rate"] = false_alarm_rate

        return CalibrationResult(
            engine_name="authority_calibration",
            adjustments=adjustments,
            recalibration_triggered=recalibrate,
            reason="; ".join(reasons) if reasons else "Within acceptable ranges",
        )


# ── LVI Calculator ────────────────────────────────────────────────────


class LearningValueIndex:
    """Calculate and track Learning Value Index progression."""

    def calculate(self, metrics: LearningMetrics) -> LearningMetrics:
        # Determine LVI stage from advancement criteria
        stage = LVIStage.DECISION_RECORDING
        for s in LVIStage:
            min_decisions, min_accuracy = ADVANCEMENT_CRITERIA[s]
            if (metrics.decisions_with_outcomes >= min_decisions
                    and metrics.overall_accuracy >= min_accuracy):
                stage = s

        # Calculate LVI score within stage range
        lo, hi = LVI_RANGES[stage]
        # Progress within stage based on accuracy improvement
        progress = min(1.0, metrics.overall_accuracy / max(ADVANCEMENT_CRITERIA[stage][1], 0.01))
        lvi = lo + (hi - lo) * progress

        metrics.lvi_stage = stage
        metrics.lvi_score = round(lvi, 1)
        return metrics


# ── Unified Adaptive Learning Engine ──────────────────────────────────


class AdaptiveLearningEngine:
    """Orchestrates all 4 learning engines and LVI tracking."""

    def __init__(self) -> None:
        self.causal_calibration = CausalModelCalibration()
        self.ovs_refinement = OVSProjectionRefinement()
        self.velocity_benchmark = DecisionVelocityBenchmarking()
        self.authority_calibration = AuthorityCalibration()
        self.lvi_calculator = LearningValueIndex()

    def run_full_cycle(
        self,
        accuracy_records: list[AccuracyRecord],
        current_weights: dict[str, float],
        gate_predictions: list[tuple[float, float]],
        decision_times: list[float],
        escalation_times: list[float],
        true_escalations: int,
        false_escalations: int,
        total_escalations: int,
        current_thresholds: dict[str, float],
        metrics: LearningMetrics,
    ) -> dict[str, CalibrationResult]:
        results = {
            "causal": self.causal_calibration.calibrate(accuracy_records, current_weights),
            "ovs": self.ovs_refinement.refine(gate_predictions),
            "velocity": self.velocity_benchmark.benchmark(decision_times, escalation_times),
            "authority": self.authority_calibration.calibrate(
                true_escalations, false_escalations, total_escalations, current_thresholds
            ),
        }

        # Update LVI
        self.lvi_calculator.calculate(metrics)

        return results
