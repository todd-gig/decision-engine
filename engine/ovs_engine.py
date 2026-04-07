"""Organizational Value Score (OVS) Engine.

Implements the 4-system health scoring framework from OVS_INTEGRATION_FRAMEWORK.md
and DATA_VALUE_MATRIX_SCHEMA.md.

Composite_OVS = (People × 0.30) + (Process × 0.25) + (Technology × 0.25) + (Learning × 0.20)
Organizational_Value = P × Pr × T × L  (multiplicative — all systems must be healthy)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HealthStatus(str, Enum):
    GREEN = "green"            # 0.7–1.0
    YELLOW = "yellow"          # 0.5–0.7 (AT RISK)
    RED = "red"                # <0.5
    TRENDING_RED = "trending_red"  # declining >5% WoW for 2+ weeks


class MaturityLevel(int, Enum):
    BASIC_BASELINE = 1
    BASELINE_CONSISTENCY = 2
    MEASUREMENT_OPS = 3
    PREDICTIVE_MODELING = 4
    STRATEGIC_OPTIMIZATION = 5


# ── Dimension inputs ──────────────────────────────────────────────────


@dataclass
class PeopleDimensions:
    cultural_diversity: float = 0.0       # CD  0–1
    decision_making_quality: float = 0.0  # DMQ 0–1
    relationship_cohesion: float = 0.0    # RC  0–1
    information_availability: float = 0.0 # IA  0–1
    learning_velocity: float = 0.0        # LV  0–1


@dataclass
class ProcessDimensions:
    standardization: float = 0.0   # PS  0–1
    efficiency: float = 0.0        # PE  0–1
    quality: float = 0.0           # PQ  0–1
    automation: float = 0.0        # PA  0–1
    discipline: float = 0.0        # PD  0–1


@dataclass
class TechnologyDimensions:
    reliability: float = 0.0       # SR  0–1
    capability: float = 0.0        # SC  0–1
    data_quality: float = 0.0      # DQ  0–1
    technical_debt: float = 0.0    # TD  0–1 (inverted: lower is better)
    security: float = 0.0          # S   0–1


@dataclass
class LearningDimensions:
    learning_culture: float = 0.0      # LC  0–1
    knowledge_capture: float = 0.0     # KC  0–1
    knowledge_distribution: float = 0.0 # KD 0–1
    knowledge_application: float = 0.0  # KA 0–1
    learning_velocity: float = 0.0      # LV 0–1


# ── System scores ─────────────────────────────────────────────────────


@dataclass
class SystemScore:
    name: str
    score: float
    status: HealthStatus
    dimensions: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0
    trend: Optional[float] = None  # WoW change rate


@dataclass
class OVSResult:
    composite_ovs: float  # 0–100 scale
    people_score: SystemScore
    process_score: SystemScore
    technology_score: SystemScore
    learning_score: SystemScore
    organizational_value: float  # multiplicative P×Pr×T×L (0–1)
    maturity_level: MaturityLevel
    warnings: list[str] = field(default_factory=list)


# ── Engine ─────────────────────────────────────────────────────────────


# Default composite weights
DEFAULT_WEIGHTS = {
    "people": 0.30,
    "process": 0.25,
    "technology": 0.25,
    "learning": 0.20,
}


class OVSEngine:
    """Calculate Organizational Value Score from four system dimensions."""

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def calculate(
        self,
        people: PeopleDimensions,
        process: ProcessDimensions,
        technology: TechnologyDimensions,
        learning: LearningDimensions,
        confidence_factors: Optional[dict[str, float]] = None,
        prior_scores: Optional[dict[str, list[float]]] = None,
    ) -> OVSResult:
        cf = confidence_factors or {}
        prior = prior_scores or {}

        p = self._score_people(people, cf.get("people", 1.0), prior.get("people"))
        pr = self._score_process(process, cf.get("process", 1.0), prior.get("process"))
        t = self._score_technology(technology, cf.get("technology", 1.0), prior.get("technology"))
        lr = self._score_learning(learning, cf.get("learning", 1.0), prior.get("learning"))

        composite = (
            p.score * self.weights["people"]
            + pr.score * self.weights["process"]
            + t.score * self.weights["technology"]
            + lr.score * self.weights["learning"]
        ) * 100  # 0–100 scale

        org_value = p.score * pr.score * t.score * lr.score

        warnings: list[str] = []
        for s in (p, pr, t, lr):
            if s.status in (HealthStatus.RED, HealthStatus.TRENDING_RED):
                warnings.append(f"{s.name} system is {s.status.value} ({s.score:.2f})")

        maturity = self._assess_maturity(composite, [p, pr, t, lr])

        return OVSResult(
            composite_ovs=round(composite, 2),
            people_score=p,
            process_score=pr,
            technology_score=t,
            learning_score=lr,
            organizational_value=round(org_value, 4),
            maturity_level=maturity,
            warnings=warnings,
        )

    # ── People ─────────────────────────────────────────────────────────

    def _score_people(
        self, d: PeopleDimensions, confidence: float, history: Optional[list[float]]
    ) -> SystemScore:
        raw = (
            d.cultural_diversity * 0.25
            + d.decision_making_quality * 0.25
            + d.relationship_cohesion * 0.20
            + d.information_availability * 0.20
            + d.learning_velocity * 0.10
        )
        score, trend = self._apply_confidence_and_trend(raw, confidence, history)
        return SystemScore(
            name="People",
            score=round(score, 4),
            status=self._status(score, trend),
            dimensions={
                "cultural_diversity": d.cultural_diversity,
                "decision_making_quality": d.decision_making_quality,
                "relationship_cohesion": d.relationship_cohesion,
                "information_availability": d.information_availability,
                "learning_velocity": d.learning_velocity,
            },
            confidence=confidence,
            trend=trend,
        )

    # ── Process ────────────────────────────────────────────────────────

    def _score_process(
        self, d: ProcessDimensions, confidence: float, history: Optional[list[float]]
    ) -> SystemScore:
        raw = (
            d.standardization * 0.25
            + d.efficiency * 0.25
            + d.quality * 0.20
            + d.automation * 0.15
            + d.discipline * 0.15
        )
        score, trend = self._apply_confidence_and_trend(raw, confidence, history)
        return SystemScore(
            name="Process",
            score=round(score, 4),
            status=self._status(score, trend),
            dimensions={
                "standardization": d.standardization,
                "efficiency": d.efficiency,
                "quality": d.quality,
                "automation": d.automation,
                "discipline": d.discipline,
            },
            confidence=confidence,
            trend=trend,
        )

    # ── Technology ─────────────────────────────────────────────────────

    def _score_technology(
        self, d: TechnologyDimensions, confidence: float, history: Optional[list[float]]
    ) -> SystemScore:
        # Technical debt is inverted (lower is better)
        td_inverted = 1.0 - d.technical_debt
        raw = (
            d.reliability * 0.25
            + d.capability * 0.25
            + d.data_quality * 0.25
            + td_inverted * 0.15
            + d.security * 0.10
        )
        score, trend = self._apply_confidence_and_trend(raw, confidence, history)
        return SystemScore(
            name="Technology",
            score=round(score, 4),
            status=self._status(score, trend),
            dimensions={
                "reliability": d.reliability,
                "capability": d.capability,
                "data_quality": d.data_quality,
                "technical_debt": d.technical_debt,
                "security": d.security,
            },
            confidence=confidence,
            trend=trend,
        )

    # ── Learning ───────────────────────────────────────────────────────

    def _score_learning(
        self, d: LearningDimensions, confidence: float, history: Optional[list[float]]
    ) -> SystemScore:
        raw = (
            d.learning_culture * 0.25
            + d.knowledge_capture * 0.25
            + d.knowledge_distribution * 0.20
            + d.knowledge_application * 0.20
            + d.learning_velocity * 0.10
        )
        score, trend = self._apply_confidence_and_trend(raw, confidence, history)
        return SystemScore(
            name="Learning",
            score=round(score, 4),
            status=self._status(score, trend),
            dimensions={
                "learning_culture": d.learning_culture,
                "knowledge_capture": d.knowledge_capture,
                "knowledge_distribution": d.knowledge_distribution,
                "knowledge_application": d.knowledge_application,
                "learning_velocity": d.learning_velocity,
            },
            confidence=confidence,
            trend=trend,
        )

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _apply_confidence_and_trend(
        raw: float, confidence: float, history: Optional[list[float]]
    ) -> tuple[float, Optional[float]]:
        adjusted = raw * max(0.5, min(1.0, confidence))
        trend = None
        if history and len(history) >= 2:
            prev = history[-2] if history[-2] > 0 else 0.001
            trend = (history[-1] - prev) / prev
            trending_factor = 1 + trend * 0.25
            adjusted *= max(0.5, min(1.5, trending_factor))
        return max(0.0, min(1.0, adjusted)), trend

    @staticmethod
    def _status(score: float, trend: Optional[float]) -> HealthStatus:
        if trend is not None and trend < -0.05:
            # Check for 2+ weeks declining (approximated by trend magnitude)
            if score < 0.7:
                return HealthStatus.TRENDING_RED
        if score >= 0.7:
            return HealthStatus.GREEN
        if score >= 0.5:
            return HealthStatus.YELLOW
        return HealthStatus.RED

    @staticmethod
    def _assess_maturity(composite: float, scores: list[SystemScore]) -> MaturityLevel:
        min_confidence = min(s.confidence for s in scores)
        if composite >= 80 and min_confidence >= 0.95:
            return MaturityLevel.STRATEGIC_OPTIMIZATION
        if composite >= 70 and min_confidence >= 0.85:
            return MaturityLevel.PREDICTIVE_MODELING
        if composite >= 60 and min_confidence >= 0.75:
            return MaturityLevel.MEASUREMENT_OPS
        if composite >= 50:
            return MaturityLevel.BASELINE_CONSISTENCY
        return MaturityLevel.BASIC_BASELINE
