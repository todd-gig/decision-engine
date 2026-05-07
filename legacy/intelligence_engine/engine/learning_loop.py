"""
Learning Loop — Post-Execution Variance Tracking & Institutional Learning

Implements the feedback loop described in docs/09_learning_loop.md:
1. Record expected vs actual outcomes for executed decisions
2. Calculate variance with directional decomposition
3. Recommend trust adjustments (upgrade/downgrade)
4. Identify update targets (registries, weights, thresholds, playbooks)
5. Persist all learning records to JSON flat-file storage
6. Surface aggregate learning metrics for continuous improvement

Core Rule: A repeated decision class should get easier, faster, and safer over time.

Storage: JSON-lines file at {data_dir}/learning_records.jsonl
Index:   JSON file at {data_dir}/learning_index.json (keyed by decision_id)
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class VarianceDirection(Enum):
    POSITIVE = "positive"       # Actual exceeded expected
    NEUTRAL = "neutral"         # Within tolerance
    NEGATIVE = "negative"       # Actual fell short of expected


class TrustRecommendation(Enum):
    UPGRADE = "upgrade"
    MAINTAIN = "maintain"
    DOWNGRADE = "downgrade"
    REVIEW = "review"           # Needs human review — ambiguous signal


class UpdateTarget(Enum):
    FIRST_PRINCIPLES_REGISTRY = "first_principles_registry"
    VALUE_MATRIX_WEIGHTS = "value_matrix_weights"
    TRUST_MATRIX_WEIGHTS = "trust_matrix_weights"
    EXECUTION_THRESHOLDS = "execution_thresholds"
    PLAYBOOKS = "playbooks"
    TEMPLATES = "templates"


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

@dataclass
class OutcomeRecord:
    """Captures the actual outcome of an executed decision."""
    decision_id: str = ""
    decision_class: str = ""
    original_verdict: str = ""
    # Expected outcome (captured at execution time)
    expected_value: float = 0.0
    expected_timeline_days: int = 0
    expected_risk_level: str = ""       # low, medium, high
    # Actual outcome (captured post-execution)
    actual_value: float = 0.0
    actual_timeline_days: int = 0
    actual_risk_materialized: bool = False
    actual_risk_description: str = ""
    # Qualitative
    outcome_summary: str = ""
    lessons_learned: list[str] = field(default_factory=list)
    # Metadata
    recorded_by: str = ""
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class VarianceAnalysis:
    """Decomposed variance between expected and actual."""
    decision_id: str = ""
    # Value variance
    value_variance: float = 0.0         # actual_value - expected_value
    value_variance_pct: float = 0.0     # percentage deviation
    value_direction: VarianceDirection = VarianceDirection.NEUTRAL
    # Timeline variance
    timeline_variance_days: int = 0     # actual - expected (positive = late)
    timeline_direction: VarianceDirection = VarianceDirection.NEUTRAL
    # Risk variance
    risk_surprise: bool = False         # risk materialized when not expected (or vice versa)
    # Composite
    composite_variance_score: float = 0.0   # -1.0 to +1.0 normalized
    # Derived recommendations
    trust_recommendation: TrustRecommendation = TrustRecommendation.MAINTAIN
    trust_recommendation_reason: str = ""
    suggested_update_targets: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    # Metadata
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LearningRecord:
    """Complete learning record combining outcome + variance."""
    record_id: str = ""
    decision_id: str = ""
    decision_class: str = ""
    outcome: OutcomeRecord = field(default_factory=OutcomeRecord)
    variance: VarianceAnalysis = field(default_factory=VarianceAnalysis)
    # Tracking
    applied: bool = False               # Has this learning been applied?
    applied_at: Optional[str] = None
    applied_targets: list[str] = field(default_factory=list)
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ─────────────────────────────────────────────
# VARIANCE CALCULATION ENGINE
# ─────────────────────────────────────────────

# Tolerance band: variance within ±10% is considered neutral
VALUE_TOLERANCE_PCT = 0.10
TIMELINE_TOLERANCE_DAYS = 3


def calculate_variance(outcome: OutcomeRecord) -> VarianceAnalysis:
    """
    Decompose expected vs actual into directional variance components.
    Returns a VarianceAnalysis with trust recommendation and update targets.
    """
    va = VarianceAnalysis(decision_id=outcome.decision_id)

    # ── Value variance ──
    va.value_variance = outcome.actual_value - outcome.expected_value
    if outcome.expected_value != 0:
        va.value_variance_pct = va.value_variance / abs(outcome.expected_value)
    else:
        va.value_variance_pct = 1.0 if outcome.actual_value > 0 else 0.0

    if va.value_variance_pct > VALUE_TOLERANCE_PCT:
        va.value_direction = VarianceDirection.POSITIVE
    elif va.value_variance_pct < -VALUE_TOLERANCE_PCT:
        va.value_direction = VarianceDirection.NEGATIVE
    else:
        va.value_direction = VarianceDirection.NEUTRAL

    # ── Timeline variance ──
    va.timeline_variance_days = outcome.actual_timeline_days - outcome.expected_timeline_days
    if va.timeline_variance_days < -TIMELINE_TOLERANCE_DAYS:
        va.timeline_direction = VarianceDirection.POSITIVE   # Faster than expected
    elif va.timeline_variance_days > TIMELINE_TOLERANCE_DAYS:
        va.timeline_direction = VarianceDirection.NEGATIVE   # Slower than expected
    else:
        va.timeline_direction = VarianceDirection.NEUTRAL

    # ── Risk variance ──
    va.risk_surprise = outcome.actual_risk_materialized and outcome.expected_risk_level == "low"

    # ── Composite score (-1.0 to +1.0) ──
    # Weighted: value 50%, timeline 30%, risk 20%
    value_component = _direction_to_score(va.value_direction)
    timeline_component = _direction_to_score(va.timeline_direction)
    risk_component = -1.0 if va.risk_surprise else (0.5 if not outcome.actual_risk_materialized else -0.3)
    va.composite_variance_score = round(
        value_component * 0.50 + timeline_component * 0.30 + risk_component * 0.20,
        3
    )

    # ── Trust recommendation ──
    va.trust_recommendation, va.trust_recommendation_reason = _derive_trust_recommendation(va)

    # ── Update targets ──
    va.suggested_update_targets = _derive_update_targets(va, outcome)
    va.suggested_actions = _derive_actions(va, outcome)

    return va


def _direction_to_score(d: VarianceDirection) -> float:
    return {
        VarianceDirection.POSITIVE: 1.0,
        VarianceDirection.NEUTRAL: 0.0,
        VarianceDirection.NEGATIVE: -1.0,
    }[d]


def _derive_trust_recommendation(va: VarianceAnalysis) -> tuple[TrustRecommendation, str]:
    """Map composite variance to a trust recommendation."""
    score = va.composite_variance_score

    if va.risk_surprise:
        return (
            TrustRecommendation.DOWNGRADE,
            f"Risk materialized unexpectedly. Composite: {score}. "
            "Risk containment model needs recalibration."
        )

    if score >= 0.5:
        return (
            TrustRecommendation.UPGRADE,
            f"Strong positive variance ({score}). "
            "Decision framework predicted conservatively — trust can be elevated."
        )
    elif score >= -0.2:
        return (
            TrustRecommendation.MAINTAIN,
            f"Variance within acceptable range ({score}). "
            "No trust adjustment needed."
        )
    elif score >= -0.5:
        return (
            TrustRecommendation.REVIEW,
            f"Moderate negative variance ({score}). "
            "Human review recommended to identify root cause."
        )
    else:
        return (
            TrustRecommendation.DOWNGRADE,
            f"Significant negative variance ({score}). "
            "Decision framework overestimated value or underestimated risk."
        )


def _derive_update_targets(va: VarianceAnalysis, outcome: OutcomeRecord) -> list[str]:
    """Determine which system artifacts should be updated based on variance."""
    targets = []

    if va.value_direction == VarianceDirection.NEGATIVE:
        targets.append(UpdateTarget.VALUE_MATRIX_WEIGHTS.value)

    if va.risk_surprise:
        targets.append(UpdateTarget.TRUST_MATRIX_WEIGHTS.value)
        targets.append(UpdateTarget.EXECUTION_THRESHOLDS.value)

    if va.timeline_direction == VarianceDirection.NEGATIVE:
        targets.append(UpdateTarget.PLAYBOOKS.value)

    if va.composite_variance_score >= 0.5:
        # Positive learnings → update playbooks and templates to codify
        targets.append(UpdateTarget.PLAYBOOKS.value)
        targets.append(UpdateTarget.TEMPLATES.value)

    if any(
        "first_principle" in lesson.lower() or "axiom" in lesson.lower()
        for lesson in outcome.lessons_learned
    ):
        targets.append(UpdateTarget.FIRST_PRINCIPLES_REGISTRY.value)

    return list(set(targets))  # deduplicate


def _derive_actions(va: VarianceAnalysis, outcome: OutcomeRecord) -> list[str]:
    """Generate specific action items from the variance analysis."""
    actions = []

    if va.trust_recommendation == TrustRecommendation.DOWNGRADE:
        actions.append(
            f"DOWNGRADE trust parameters for {outcome.decision_class} decisions. "
            f"Reason: {va.trust_recommendation_reason}"
        )

    if va.trust_recommendation == TrustRecommendation.UPGRADE:
        actions.append(
            f"EVALUATE trust promotion for {outcome.decision_class} decisions. "
            f"Pattern shows conservative estimation."
        )

    if va.risk_surprise:
        actions.append(
            "AUDIT risk containment model — unexpected risk materialization indicates "
            "blind spot in risk scoring."
        )

    if va.value_direction == VarianceDirection.NEGATIVE:
        actions.append(
            "RECALIBRATE value scoring weights — actual value fell short of prediction."
        )

    if va.timeline_direction == VarianceDirection.NEGATIVE:
        actions.append(
            f"REVIEW execution playbooks — timeline overran by "
            f"{va.timeline_variance_days} days."
        )

    if not actions:
        actions.append("No corrective actions required — outcome within tolerance.")

    return actions


# ─────────────────────────────────────────────
# PERSISTENCE LAYER (JSON flat-file)
# ─────────────────────────────────────────────

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RECORDS_FILE = "learning_records.jsonl"
INDEX_FILE = "learning_index.json"


class LearningStore:
    """
    File-based persistence for learning records.

    Storage format:
    - learning_records.jsonl: Append-only JSON-lines (one record per line)
    - learning_index.json: Keyed by decision_id for fast lookups
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or DEFAULT_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._records_path = self.data_dir / RECORDS_FILE
        self._index_path = self.data_dir / INDEX_FILE

    # ── Write ──

    def store_record(self, record: LearningRecord) -> str:
        """
        Persist a learning record. Returns the record_id.
        Appends to JSONL and updates the index.
        """
        if not record.record_id:
            record.record_id = f"LRN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{record.decision_id}"

        record_dict = _serialize_learning_record(record)

        # Append to JSONL (append-only log)
        with open(self._records_path, "a") as f:
            f.write(json.dumps(record_dict) + "\n")

        # Update index
        index = self._load_index()
        index[record.decision_id] = {
            "record_id": record.record_id,
            "decision_class": record.decision_class,
            "composite_variance": record.variance.composite_variance_score,
            "trust_recommendation": record.variance.trust_recommendation.value,
            "applied": record.applied,
            "created_at": record.created_at,
        }
        self._save_index(index)

        return record.record_id

    def mark_applied(self, decision_id: str, applied_targets: list[str]) -> bool:
        """Mark a learning record as applied to specific update targets."""
        index = self._load_index()
        if decision_id not in index:
            return False

        index[decision_id]["applied"] = True
        index[decision_id]["applied_at"] = datetime.now().isoformat()
        index[decision_id]["applied_targets"] = applied_targets
        self._save_index(index)
        return True

    # ── Read ──

    def get_record(self, decision_id: str) -> Optional[LearningRecord]:
        """Retrieve a learning record by decision_id."""
        for record_dict in self._iter_records():
            if record_dict.get("decision_id") == decision_id:
                return _deserialize_learning_record(record_dict)
        return None

    def get_all_records(self) -> list[LearningRecord]:
        """Load all learning records."""
        return [_deserialize_learning_record(d) for d in self._iter_records()]

    def get_unapplied(self) -> list[LearningRecord]:
        """Get records that haven't been applied yet (checks index for applied status)."""
        index = self._load_index()
        results = []
        for r in self.get_all_records():
            # Index is authoritative for applied status
            idx_entry = index.get(r.decision_id, {})
            if idx_entry.get("applied", r.applied):
                continue
            results.append(r)
        return results

    def get_by_class(self, decision_class: str) -> list[LearningRecord]:
        """Get all learning records for a specific decision class."""
        return [
            r for r in self.get_all_records()
            if r.decision_class == decision_class
        ]

    # ── Aggregate Analytics ──

    def compute_class_stats(self) -> dict:
        """
        Compute aggregate learning statistics per decision class.
        Returns: {decision_class: {count, avg_variance, upgrade_rate, downgrade_rate}}
        """
        records = self.get_all_records()
        stats: dict = {}

        for r in records:
            cls = r.decision_class
            if cls not in stats:
                stats[cls] = {
                    "count": 0,
                    "total_variance": 0.0,
                    "upgrades": 0,
                    "downgrades": 0,
                    "reviews": 0,
                    "risk_surprises": 0,
                }
            s = stats[cls]
            s["count"] += 1
            s["total_variance"] += r.variance.composite_variance_score
            if r.variance.trust_recommendation == TrustRecommendation.UPGRADE:
                s["upgrades"] += 1
            elif r.variance.trust_recommendation == TrustRecommendation.DOWNGRADE:
                s["downgrades"] += 1
            elif r.variance.trust_recommendation == TrustRecommendation.REVIEW:
                s["reviews"] += 1
            if r.variance.risk_surprise:
                s["risk_surprises"] += 1

        # Compute rates
        for cls, s in stats.items():
            n = s["count"]
            s["avg_variance"] = round(s["total_variance"] / n, 3) if n > 0 else 0.0
            s["upgrade_rate"] = round(s["upgrades"] / n, 3) if n > 0 else 0.0
            s["downgrade_rate"] = round(s["downgrades"] / n, 3) if n > 0 else 0.0

        return stats

    def generate_learning_summary(self) -> str:
        """Generate a human-readable summary of institutional learning to date."""
        stats = self.compute_class_stats()
        records = self.get_all_records()
        unapplied = [r for r in records if not r.applied]

        lines = [
            "═══════════════════════════════════════════════",
            "  INSTITUTIONAL LEARNING SUMMARY",
            f"  As of: {datetime.now().isoformat()}",
            "═══════════════════════════════════════════════",
            f"Total learning records: {len(records)}",
            f"Unapplied learnings: {len(unapplied)}",
            "",
        ]

        if stats:
            lines.append("Per-Class Performance:")
            for cls, s in sorted(stats.items()):
                lines.append(
                    f"  {cls}: {s['count']} decisions | "
                    f"avg variance: {s['avg_variance']:+.3f} | "
                    f"upgrade rate: {s['upgrade_rate']:.0%} | "
                    f"downgrade rate: {s['downgrade_rate']:.0%} | "
                    f"risk surprises: {s['risk_surprises']}"
                )

        # Pending action items
        if unapplied:
            lines.append("")
            lines.append("Pending Actions:")
            for r in unapplied:
                for action in r.variance.suggested_actions:
                    lines.append(f"  [{r.decision_id}] {action}")

        return "\n".join(lines)

    # ── Internal helpers ──

    def _iter_records(self):
        """Iterate over raw record dicts from JSONL file."""
        if not self._records_path.exists():
            return
        with open(self._records_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def _load_index(self) -> dict:
        if self._index_path.exists():
            with open(self._index_path, "r") as f:
                return json.load(f)
        return {}

    def _save_index(self, index: dict):
        with open(self._index_path, "w") as f:
            json.dump(index, f, indent=2)


# ─────────────────────────────────────────────
# SERIALIZATION HELPERS
# ─────────────────────────────────────────────

def _serialize_learning_record(record: LearningRecord) -> dict:
    """Convert LearningRecord to a JSON-serializable dict."""
    return {
        "record_id": record.record_id,
        "decision_id": record.decision_id,
        "decision_class": record.decision_class,
        "outcome": {
            "decision_id": record.outcome.decision_id,
            "decision_class": record.outcome.decision_class,
            "original_verdict": record.outcome.original_verdict,
            "expected_value": record.outcome.expected_value,
            "expected_timeline_days": record.outcome.expected_timeline_days,
            "expected_risk_level": record.outcome.expected_risk_level,
            "actual_value": record.outcome.actual_value,
            "actual_timeline_days": record.outcome.actual_timeline_days,
            "actual_risk_materialized": record.outcome.actual_risk_materialized,
            "actual_risk_description": record.outcome.actual_risk_description,
            "outcome_summary": record.outcome.outcome_summary,
            "lessons_learned": record.outcome.lessons_learned,
            "recorded_by": record.outcome.recorded_by,
            "recorded_at": record.outcome.recorded_at,
        },
        "variance": {
            "decision_id": record.variance.decision_id,
            "value_variance": record.variance.value_variance,
            "value_variance_pct": record.variance.value_variance_pct,
            "value_direction": record.variance.value_direction.value,
            "timeline_variance_days": record.variance.timeline_variance_days,
            "timeline_direction": record.variance.timeline_direction.value,
            "risk_surprise": record.variance.risk_surprise,
            "composite_variance_score": record.variance.composite_variance_score,
            "trust_recommendation": record.variance.trust_recommendation.value,
            "trust_recommendation_reason": record.variance.trust_recommendation_reason,
            "suggested_update_targets": record.variance.suggested_update_targets,
            "suggested_actions": record.variance.suggested_actions,
            "analyzed_at": record.variance.analyzed_at,
        },
        "applied": record.applied,
        "applied_at": record.applied_at,
        "applied_targets": record.applied_targets,
        "created_at": record.created_at,
    }


def _deserialize_learning_record(d: dict) -> LearningRecord:
    """Reconstruct a LearningRecord from a serialized dict."""
    outcome_d = d.get("outcome", {})
    variance_d = d.get("variance", {})

    outcome = OutcomeRecord(
        decision_id=outcome_d.get("decision_id", ""),
        decision_class=outcome_d.get("decision_class", ""),
        original_verdict=outcome_d.get("original_verdict", ""),
        expected_value=outcome_d.get("expected_value", 0.0),
        expected_timeline_days=outcome_d.get("expected_timeline_days", 0),
        expected_risk_level=outcome_d.get("expected_risk_level", ""),
        actual_value=outcome_d.get("actual_value", 0.0),
        actual_timeline_days=outcome_d.get("actual_timeline_days", 0),
        actual_risk_materialized=outcome_d.get("actual_risk_materialized", False),
        actual_risk_description=outcome_d.get("actual_risk_description", ""),
        outcome_summary=outcome_d.get("outcome_summary", ""),
        lessons_learned=outcome_d.get("lessons_learned", []),
        recorded_by=outcome_d.get("recorded_by", ""),
        recorded_at=outcome_d.get("recorded_at", ""),
    )

    variance = VarianceAnalysis(
        decision_id=variance_d.get("decision_id", ""),
        value_variance=variance_d.get("value_variance", 0.0),
        value_variance_pct=variance_d.get("value_variance_pct", 0.0),
        value_direction=VarianceDirection(variance_d.get("value_direction", "neutral")),
        timeline_variance_days=variance_d.get("timeline_variance_days", 0),
        timeline_direction=VarianceDirection(variance_d.get("timeline_direction", "neutral")),
        risk_surprise=variance_d.get("risk_surprise", False),
        composite_variance_score=variance_d.get("composite_variance_score", 0.0),
        trust_recommendation=TrustRecommendation(
            variance_d.get("trust_recommendation", "maintain")
        ),
        trust_recommendation_reason=variance_d.get("trust_recommendation_reason", ""),
        suggested_update_targets=variance_d.get("suggested_update_targets", []),
        suggested_actions=variance_d.get("suggested_actions", []),
        analyzed_at=variance_d.get("analyzed_at", ""),
    )

    return LearningRecord(
        record_id=d.get("record_id", ""),
        decision_id=d.get("decision_id", ""),
        decision_class=d.get("decision_class", ""),
        outcome=outcome,
        variance=variance,
        applied=d.get("applied", False),
        applied_at=d.get("applied_at"),
        applied_targets=d.get("applied_targets", []),
        created_at=d.get("created_at", ""),
    )


# ─────────────────────────────────────────────
# PIPELINE INTEGRATION FUNCTION
# ─────────────────────────────────────────────

def record_outcome(
    decision_id: str,
    decision_class: str,
    original_verdict: str,
    expected_value: float,
    expected_timeline_days: int,
    expected_risk_level: str,
    actual_value: float,
    actual_timeline_days: int,
    actual_risk_materialized: bool,
    actual_risk_description: str = "",
    outcome_summary: str = "",
    lessons_learned: list[str] = None,
    recorded_by: str = "",
    data_dir: Optional[str] = None,
) -> LearningRecord:
    """
    Top-level convenience function for recording a decision outcome.

    1. Creates the OutcomeRecord
    2. Runs variance analysis
    3. Builds LearningRecord
    4. Persists to store
    5. Returns the complete record

    This is the primary integration point for the pipeline.
    """
    outcome = OutcomeRecord(
        decision_id=decision_id,
        decision_class=decision_class,
        original_verdict=original_verdict,
        expected_value=expected_value,
        expected_timeline_days=expected_timeline_days,
        expected_risk_level=expected_risk_level,
        actual_value=actual_value,
        actual_timeline_days=actual_timeline_days,
        actual_risk_materialized=actual_risk_materialized,
        actual_risk_description=actual_risk_description,
        outcome_summary=outcome_summary,
        lessons_learned=lessons_learned or [],
        recorded_by=recorded_by,
    )

    variance = calculate_variance(outcome)

    record = LearningRecord(
        decision_id=decision_id,
        decision_class=decision_class,
        outcome=outcome,
        variance=variance,
    )

    store = LearningStore(data_dir=data_dir)
    store.store_record(record)

    return record
