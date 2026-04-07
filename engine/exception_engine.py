"""
Exception Engine — Structured Exception Classification, Escalation, and Learning

Classifies, escalates, logs, and analyzes exceptions that arise during
decision processing. Tracks recurrence to identify patterns that should be
codified into policy.

Exception classes:
    missing_data            — Required inputs are absent or incomplete
    conflicting_data        — Multiple sources present contradictory information
    ambiguous_intent        — Decision intent or desired outcome is unclear
    threshold_conflict      — Scoring thresholds cannot be simultaneously satisfied
    policy_gap              — No existing policy covers the decision scenario
    out_of_distribution_input — Input falls outside trained/expected operational range
    compliance_risk         — Decision may violate regulatory or governance rules
    irreversible_action_risk — Decision involves actions that cannot be undone

Escalation triggers:
    - Confidence below threshold for the action class
    - Action is irreversible
    - Compliance risk is present
    - Failure cost tolerance is low relative to exception severity

Codification candidates:
    Exceptions that recur frequently enough to warrant policy formalization.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


# ─────────────────────────────────────────────
# EXCEPTION CLASSES
# ─────────────────────────────────────────────

EXCEPTION_CLASSES = frozenset({
    "missing_data",
    "conflicting_data",
    "ambiguous_intent",
    "threshold_conflict",
    "policy_gap",
    "out_of_distribution_input",
    "compliance_risk",
    "irreversible_action_risk",
})

# Recurrence threshold: exceptions seen >= this many times become codification candidates
_CODIFICATION_RECURRENCE_THRESHOLD = 3

# Minimum confidence required before auto-proceeding (below this -> escalate)
_CONFIDENCE_ESCALATION_THRESHOLD = 0.65

# Exception classes that always trigger escalation regardless of confidence
_ALWAYS_ESCALATE_CLASSES = frozenset({
    "compliance_risk",
    "irreversible_action_risk",
})


# ─────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────

@dataclass
class ExceptionRecord:
    """
    A structured record of a single exception event.

    Fields:
        exception_id:           Unique identifier for this exception instance
        exception_class:        One of the 8 canonical exception classes
        triggering_variables:   Dict of decision variables that caused the exception
        decision_path:          Dot-path string describing where in the pipeline the
                                exception was raised (e.g., "gate.certification.replicability")
        resolution:             Description of how the exception was resolved or
                                why it was escalated
        recurrence_tag:         A stable string key identifying structurally identical
                                exceptions (used for recurrence tracking)
        codification_candidate: True if this exception has recurred enough times
                                to warrant policy formalization
        timestamp:              ISO 8601 timestamp of when the exception was logged
    """
    exception_id: str
    exception_class: str
    triggering_variables: dict
    decision_path: str
    resolution: str
    recurrence_tag: str
    codification_candidate: bool
    timestamp: str


@dataclass
class EscalationRule:
    """
    Result of evaluating whether an exception should be escalated.

    Fields:
        condition_type:  The condition that was evaluated
                         (e.g., "low_confidence", "irreversible_action",
                          "compliance_risk", "low_failure_tolerance")
        threshold:       The threshold value that was compared against
        current_value:   The actual value at evaluation time
        should_escalate: True if escalation is warranted
        reason:          Human-readable explanation of the escalation decision
    """
    condition_type: str
    threshold: Any
    current_value: Any
    should_escalate: bool
    reason: str


# ─────────────────────────────────────────────
# EXCEPTION ENGINE
# ─────────────────────────────────────────────

class ExceptionEngine:
    """
    Classifies exceptions from decision payloads, evaluates escalation rules,
    maintains an in-memory exception log, and provides recurrence analysis
    and codification candidate identification.

    Usage:
        engine = ExceptionEngine()

        # During a decision pipeline run:
        exc_class = engine.classify(decision_payload)
        rule = engine.check_escalation(
            exception_class=exc_class,
            confidence=0.55,
            action_reversible=False,
            compliance_risk=True,
            failure_cost_tolerance="low",
        )
        record = engine.build_exception(
            exception_class=exc_class,
            triggering_variables=decision_payload,
            decision_path="gate.certification",
            resolution="escalated" if rule.should_escalate else "auto_resolved",
        )
        engine.log_exception(record)

        # Periodic review:
        analysis = engine.get_recurrence_analysis()
        candidates = engine.get_codification_candidates()
    """

    def __init__(self) -> None:
        self._log: list[ExceptionRecord] = []
        # recurrence_tag -> count
        self._recurrence_counts: dict[str, int] = defaultdict(int)

    # ─────────────────────────────────────────────
    # CLASSIFY
    # ─────────────────────────────────────────────

    def classify(self, decision_payload: dict) -> str:
        """
        Classify a decision payload into one of the 8 canonical exception classes.

        Classification priority order (highest to lowest specificity):
          1. compliance_risk         — explicit compliance flags
          2. irreversible_action_risk — irreversibility signals
          3. missing_data            — required keys absent or None
          4. conflicting_data        — detected data conflicts
          5. ambiguous_intent        — intent or outcome is unclear
          6. threshold_conflict      — competing threshold violations
          7. out_of_distribution_input — input outside expected range
          8. policy_gap              — no other class applies

        Args:
            decision_payload: dict representing the decision context.
                Expected optional keys (all presence-checked, not required):
                    compliance_flags: list or bool
                    is_reversible: bool
                    reversibility_tag: str (R3/R4 = effectively irreversible)
                    data_conflicts: list or bool
                    missing_fields: list
                    intent: str
                    action: str
                    outcome: str
                    threshold_violations: list or bool
                    confidence: float
                    out_of_distribution: bool
                    input_range_flags: list

        Returns:
            One of the 8 exception class strings.
        """
        # ── 1. Compliance risk ──
        compliance_flags = decision_payload.get("compliance_flags")
        if compliance_flags:
            return "compliance_risk"

        # ── 2. Irreversible action risk ──
        is_reversible = decision_payload.get("is_reversible")
        reversibility_tag = decision_payload.get("reversibility_tag", "")
        if is_reversible is False or reversibility_tag in ("R3", "R4"):
            return "irreversible_action_risk"

        # ── 3. Missing data ──
        missing_fields = decision_payload.get("missing_fields")
        if missing_fields:
            return "missing_data"
        # Also check for None values on expected keys
        expected_keys = decision_payload.get("expected_keys", [])
        if expected_keys:
            if any(decision_payload.get(k) is None for k in expected_keys):
                return "missing_data"

        # ── 4. Conflicting data ──
        data_conflicts = decision_payload.get("data_conflicts")
        if data_conflicts:
            return "conflicting_data"

        # ── 5. Ambiguous intent ──
        intent = decision_payload.get("intent", "")
        action = decision_payload.get("action", "")
        outcome = decision_payload.get("outcome", "")
        if not intent and not action and not outcome:
            return "ambiguous_intent"
        if decision_payload.get("ambiguous_intent"):
            return "ambiguous_intent"

        # ── 6. Threshold conflict ──
        threshold_violations = decision_payload.get("threshold_violations")
        if threshold_violations:
            return "threshold_conflict"
        # Detect implicit threshold conflict: confidence present but very low
        confidence = decision_payload.get("confidence")
        if confidence is not None and 0.0 <= confidence < _CONFIDENCE_ESCALATION_THRESHOLD:
            # Only classify as threshold_conflict if there is contextual signal
            if decision_payload.get("threshold_conflict"):
                return "threshold_conflict"

        # ── 7. Out of distribution ──
        if decision_payload.get("out_of_distribution"):
            return "out_of_distribution_input"
        input_range_flags = decision_payload.get("input_range_flags")
        if input_range_flags:
            return "out_of_distribution_input"

        # ── 8. Policy gap (default) ──
        return "policy_gap"

    # ─────────────────────────────────────────────
    # CHECK ESCALATION
    # ─────────────────────────────────────────────

    def check_escalation(
        self,
        exception_class: str,
        confidence: float,
        action_reversible: bool,
        compliance_risk: bool,
        failure_cost_tolerance: str,
    ) -> EscalationRule:
        """
        Evaluate whether an exception warrants escalation.

        Escalation is triggered by the FIRST condition that is true, in
        priority order:
          1. Exception class always escalates (compliance_risk, irreversible_action_risk)
          2. Action is not reversible
          3. Compliance risk flag is explicitly set
          4. Confidence is below the escalation threshold
          5. Failure cost tolerance is "low" or "zero"

        Args:
            exception_class:        Classified exception class string
            confidence:             0.0-1.0 confidence score for the current decision
            action_reversible:      Whether the proposed action can be undone
            compliance_risk:        Whether a compliance risk has been detected
            failure_cost_tolerance: One of: "zero" | "low" | "medium" | "high"

        Returns:
            EscalationRule with the primary triggering condition.
        """
        # ── 1. Always-escalate exception classes ──
        if exception_class in _ALWAYS_ESCALATE_CLASSES:
            return EscalationRule(
                condition_type="exception_class_always_escalates",
                threshold=list(_ALWAYS_ESCALATE_CLASSES),
                current_value=exception_class,
                should_escalate=True,
                reason=(
                    f"Exception class '{exception_class}' requires mandatory escalation "
                    f"regardless of confidence or reversibility"
                ),
            )

        # ── 2. Irreversible action ──
        if not action_reversible:
            return EscalationRule(
                condition_type="irreversible_action",
                threshold=True,
                current_value=False,
                should_escalate=True,
                reason=(
                    "Action is not reversible — human review required before execution"
                ),
            )

        # ── 3. Compliance risk flag ──
        if compliance_risk:
            return EscalationRule(
                condition_type="compliance_risk",
                threshold=False,
                current_value=True,
                should_escalate=True,
                reason=(
                    "Compliance risk flag is set — legal or governance review required"
                ),
            )

        # ── 4. Confidence below threshold ──
        if confidence < _CONFIDENCE_ESCALATION_THRESHOLD:
            return EscalationRule(
                condition_type="low_confidence",
                threshold=_CONFIDENCE_ESCALATION_THRESHOLD,
                current_value=confidence,
                should_escalate=True,
                reason=(
                    f"Confidence {confidence:.2f} < threshold "
                    f"{_CONFIDENCE_ESCALATION_THRESHOLD} — insufficient certainty to proceed"
                ),
            )

        # ── 5. Low failure cost tolerance ──
        if failure_cost_tolerance in ("zero", "low"):
            return EscalationRule(
                condition_type="low_failure_tolerance",
                threshold="medium",
                current_value=failure_cost_tolerance,
                should_escalate=True,
                reason=(
                    f"Failure cost tolerance is '{failure_cost_tolerance}' — "
                    f"escalate to avoid unacceptable downside"
                ),
            )

        # ── No escalation triggered ──
        return EscalationRule(
            condition_type="no_escalation_condition",
            threshold=None,
            current_value=None,
            should_escalate=False,
            reason=(
                "No escalation conditions met — exception can be handled autonomously"
            ),
        )

    # ─────────────────────────────────────────────
    # LOG EXCEPTION
    # ─────────────────────────────────────────────

    def log_exception(self, exception: ExceptionRecord) -> None:
        """
        Store an exception record in the internal log and update recurrence counts.

        Args:
            exception: A fully constructed ExceptionRecord instance.
        """
        self._recurrence_counts[exception.recurrence_tag] += 1
        # Update codification_candidate flag based on current recurrence count
        if (
            self._recurrence_counts[exception.recurrence_tag]
            >= _CODIFICATION_RECURRENCE_THRESHOLD
        ):
            exception.codification_candidate = True
        self._log.append(exception)

    # ─────────────────────────────────────────────
    # RECURRENCE ANALYSIS
    # ─────────────────────────────────────────────

    def get_recurrence_analysis(self) -> dict:
        """
        Return a summary of logged exceptions by class and by recurrence tag.

        Returns:
            dict with keys:
                total_count:         int — total exceptions logged
                counts_by_class:     dict[str, int] — count per exception class
                rates_by_class:      dict[str, float] — proportion per exception class
                counts_by_tag:       dict[str, int] — count per recurrence_tag
                top_recurrence_tags: list[dict] — top 10 tags by count, sorted desc
                codification_count:  int — total exceptions flagged as codification candidates
        """
        total = len(self._log)

        counts_by_class: dict[str, int] = defaultdict(int)
        for record in self._log:
            counts_by_class[record.exception_class] += 1

        rates_by_class: dict[str, float] = {
            cls: (count / total if total > 0 else 0.0)
            for cls, count in counts_by_class.items()
        }

        top_tags = sorted(
            [
                {"recurrence_tag": tag, "count": count}
                for tag, count in self._recurrence_counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        codification_count = sum(
            1 for r in self._log if r.codification_candidate
        )

        return {
            "total_count": total,
            "counts_by_class": dict(counts_by_class),
            "rates_by_class": rates_by_class,
            "counts_by_tag": dict(self._recurrence_counts),
            "top_recurrence_tags": top_tags,
            "codification_count": codification_count,
        }

    # ─────────────────────────────────────────────
    # CODIFICATION CANDIDATES
    # ─────────────────────────────────────────────

    def get_codification_candidates(self) -> list[ExceptionRecord]:
        """
        Return exception records that are flagged as codification candidates.

        An exception is a codification candidate when its recurrence_tag has
        been seen >= _CODIFICATION_RECURRENCE_THRESHOLD times, indicating the
        pattern is stable enough to warrant formalizing into policy.

        Returns:
            List of ExceptionRecord instances where codification_candidate is True.
            Deduplicated by recurrence_tag — returns the most recent record per tag.
        """
        seen_tags: set[str] = set()
        candidates: list[ExceptionRecord] = []

        # Walk in reverse to get most recent record per tag first
        for record in reversed(self._log):
            if (
                record.codification_candidate
                and record.recurrence_tag not in seen_tags
            ):
                seen_tags.add(record.recurrence_tag)
                candidates.append(record)

        return candidates

    # ─────────────────────────────────────────────
    # FACTORY HELPER
    # ─────────────────────────────────────────────

    def build_exception(
        self,
        exception_class: str,
        triggering_variables: dict,
        decision_path: str,
        resolution: str,
        recurrence_tag: Optional[str] = None,
    ) -> ExceptionRecord:
        """
        Convenience factory to construct an ExceptionRecord.

        If recurrence_tag is not provided, it is derived from
        exception_class + decision_path as a stable structural key.

        Args:
            exception_class:       One of the 8 canonical exception class strings
            triggering_variables:  Dict of variables that caused this exception
            decision_path:         Dot-path location in the pipeline
            resolution:            How the exception was resolved or why escalated
            recurrence_tag:        Optional stable tag for grouping identical exceptions

        Returns:
            An ExceptionRecord (not yet logged — call log_exception to persist).
        """
        if exception_class not in EXCEPTION_CLASSES:
            raise ValueError(
                f"Unknown exception_class '{exception_class}'. "
                f"Must be one of: {sorted(EXCEPTION_CLASSES)}"
            )

        tag = recurrence_tag or f"{exception_class}::{decision_path}"
        # Determine codification_candidate based on current recurrence count
        # (will be re-evaluated in log_exception, but pre-compute for convenience)
        current_count = self._recurrence_counts.get(tag, 0)
        codification_candidate = (
            current_count + 1 >= _CODIFICATION_RECURRENCE_THRESHOLD
        )

        return ExceptionRecord(
            exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
            exception_class=exception_class,
            triggering_variables=dict(triggering_variables),
            decision_path=decision_path,
            resolution=resolution,
            recurrence_tag=tag,
            codification_candidate=codification_candidate,
            timestamp=datetime.now().isoformat(),
        )

    # ─────────────────────────────────────────────
    # INSPECTION HELPERS
    # ─────────────────────────────────────────────

    def get_log(self) -> list[ExceptionRecord]:
        """Return the full exception log (read-only copy)."""
        return list(self._log)

    def clear_log(self) -> None:
        """Clear the exception log and recurrence counters. Use with caution."""
        self._log.clear()
        self._recurrence_counts.clear()
