"""Layer Tracking System.

Operational tracking for decision implementations across 4 layers,
with escalation triggers, daily metrics, and rollback procedures.
From LAYER_TRACKING_IMPLEMENTATION_PLAYBOOKS.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class TrackingLayer(int, Enum):
    LAYER_1 = 1  # Days 0-30: Primary Impact
    LAYER_2 = 2  # Days 7-60: Secondary Cascading
    LAYER_3 = 3  # Days 30-90: Tertiary Cultural/Structural
    LAYER_4 = 4  # 90+: Compound Strategic


class SystemType(str, Enum):
    PEOPLE = "people"
    PROCESS = "process"
    TECHNOLOGY = "technology"
    LEARNING = "learning"


class ImplementationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


class RollbackPhase(str, Enum):
    IMMEDIATE_RESPONSE = "immediate_response"  # Days 1-3
    SYSTEM_ROLLBACK = "system_rollback"        # Days 4-7
    PROCESS_RESTORATION = "process_restoration" # Days 8-14
    STAFF_TRANSITION = "staff_transition"      # Days 15-21
    FINANCIAL_CLOSEOUT = "financial_closeout"   # Days 22-30


# ── Data structures ───────────────────────────────────────────────────


@dataclass
class DailyMetric:
    date: str
    system: SystemType
    layer: TrackingLayer
    metric_name: str
    value: float
    target: float
    on_track: bool = True

    def evaluate(self) -> bool:
        self.on_track = self.value >= self.target * 0.80
        return self.on_track


@dataclass
class LayerSnapshot:
    layer: TrackingLayer
    day: int
    status: ImplementationStatus = ImplementationStatus.NOT_STARTED
    adoption_rate: float = 0.0
    efficiency_gain: float = 0.0
    behavioral_alignment: float = 0.0
    system_metrics: dict[str, float] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class RollbackStep:
    phase: RollbackPhase
    description: str
    owner: str
    day_range: tuple[int, int]
    completed: bool = False
    notes: str = ""


@dataclass
class DecisionImplementationRecord:
    record_id: str = field(default_factory=lambda: str(uuid4()))
    decision_id: str = ""
    decision_name: str = ""
    start_date: str = ""
    current_day: int = 0
    current_layer: TrackingLayer = TrackingLayer.LAYER_1
    status: ImplementationStatus = ImplementationStatus.NOT_STARTED
    snapshots: list[LayerSnapshot] = field(default_factory=list)
    daily_metrics: list[DailyMetric] = field(default_factory=list)
    rollback_plan: list[RollbackStep] = field(default_factory=list)
    gate_results: list[str] = field(default_factory=list)  # gate decision strings


# ── Tracking defaults by system ───────────────────────────────────────

DAILY_TARGETS = {
    TrackingLayer.LAYER_1: {
        SystemType.PEOPLE: {"adoption_pct": 0.60, "proficiency": 0.50, "knowledge_gaps": 0.30},
        SystemType.PROCESS: {"workflow_transition_pct": 0.60, "efficiency_baseline": 0.50},
        SystemType.TECHNOLOGY: {"stability": 0.95, "data_integrity": 0.95, "integration_success": 0.90},
        SystemType.LEARNING: {"training_completion_pct": 0.80, "capability_proficiency": 0.50},
    },
    TrackingLayer.LAYER_2: {
        SystemType.PEOPLE: {"behavioral_alignment": 0.70, "capability_growth": 0.15},
        SystemType.PROCESS: {"efficiency_gain": 0.15, "process_adherence": 0.80},
        SystemType.TECHNOLOGY: {"zero_new_failures": 1.0, "cascade_activation": 0.75},
        SystemType.LEARNING: {"knowledge_transfer": 0.60, "pattern_application": 0.50},
    },
    TrackingLayer.LAYER_3: {
        SystemType.PEOPLE: {"sustained_alignment": 0.75, "culture_shift": 0.50},
        SystemType.PROCESS: {"structural_adaptation": 0.80, "incentive_alignment": 0.70},
        SystemType.TECHNOLOGY: {"compound_capability": 0.60, "platform_maturity": 0.70},
        SystemType.LEARNING: {"org_learning_velocity": 0.65, "institutional_memory": 0.60},
    },
}


# ── Engine ─────────────────────────────────────────────────────────────


class LayerTracker:
    """Track decision implementation progress across 4 layers."""

    def __init__(self) -> None:
        self._records: dict[str, DecisionImplementationRecord] = {}

    def create_record(
        self,
        decision_id: str,
        decision_name: str,
        start_date: Optional[str] = None,
    ) -> DecisionImplementationRecord:
        record = DecisionImplementationRecord(
            decision_id=decision_id,
            decision_name=decision_name,
            start_date=start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            status=ImplementationStatus.IN_PROGRESS,
            rollback_plan=self._default_rollback_plan(),
        )
        self._records[record.record_id] = record
        return record

    def get_record(self, record_id: str) -> Optional[DecisionImplementationRecord]:
        return self._records.get(record_id)

    def record_daily_metrics(
        self,
        record_id: str,
        day: int,
        metrics: list[DailyMetric],
    ) -> DecisionImplementationRecord:
        record = self._records.get(record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")

        record.current_day = day
        for m in metrics:
            m.evaluate()
        record.daily_metrics.extend(metrics)

        # Auto-detect current layer from day
        if day <= 30:
            record.current_layer = TrackingLayer.LAYER_1
        elif day <= 60:
            record.current_layer = TrackingLayer.LAYER_2
        elif day <= 90:
            record.current_layer = TrackingLayer.LAYER_3
        else:
            record.current_layer = TrackingLayer.LAYER_4

        # Check for blockers
        off_track = [m for m in metrics if not m.on_track]
        if len(off_track) >= 3:
            record.status = ImplementationStatus.AT_RISK
        elif len(off_track) >= 5:
            record.status = ImplementationStatus.BLOCKED

        return record

    def take_snapshot(self, record_id: str) -> LayerSnapshot:
        record = self._records.get(record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")

        # Aggregate latest metrics into a snapshot
        latest_by_name: dict[str, DailyMetric] = {}
        for m in record.daily_metrics:
            latest_by_name[f"{m.system.value}.{m.metric_name}"] = m

        snapshot = LayerSnapshot(
            layer=record.current_layer,
            day=record.current_day,
            status=record.status,
            system_metrics={k: v.value for k, v in latest_by_name.items()},
            blockers=[
                f"{k}: {v.value:.2f} vs target {v.target:.2f}"
                for k, v in latest_by_name.items()
                if not v.on_track
            ],
        )
        record.snapshots.append(snapshot)
        return snapshot

    def initiate_rollback(self, record_id: str) -> DecisionImplementationRecord:
        record = self._records.get(record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        record.status = ImplementationStatus.ROLLED_BACK
        return record

    def complete_rollback_step(
        self, record_id: str, phase: RollbackPhase, notes: str = ""
    ) -> DecisionImplementationRecord:
        record = self._records.get(record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        for step in record.rollback_plan:
            if step.phase == phase:
                step.completed = True
                step.notes = notes
                break
        return record

    def get_targets(
        self, layer: TrackingLayer, system: SystemType
    ) -> dict[str, float]:
        return DAILY_TARGETS.get(layer, {}).get(system, {})

    @staticmethod
    def _default_rollback_plan() -> list[RollbackStep]:
        return [
            RollbackStep(
                RollbackPhase.IMMEDIATE_RESPONSE,
                "Escalation communication, root cause hypothesis",
                "PM", (1, 3),
            ),
            RollbackStep(
                RollbackPhase.SYSTEM_ROLLBACK,
                "Revert to baseline state, disable new processes",
                "Engineering", (4, 7),
            ),
            RollbackStep(
                RollbackPhase.PROCESS_RESTORATION,
                "Restore previous operational models",
                "Operations", (8, 14),
            ),
            RollbackStep(
                RollbackPhase.STAFF_TRANSITION,
                "Role realignment, capability restoration",
                "HR", (15, 21),
            ),
            RollbackStep(
                RollbackPhase.FINANCIAL_CLOSEOUT,
                "Project costs reconciliation, contingency release",
                "Finance", (22, 30),
            ),
        ]
