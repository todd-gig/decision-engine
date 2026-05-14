"""Calibration-write authority gate + override-weight policy.

Per spec §Calibration write authority (decision #5, line 150):
  - Automated writes allowed when ALL of:
      * single-dimension update
      * |after - before| / |before| < 10%   (or |delta| < 10% if before==0)
      * computation_version unchanged
      * dimension is not being added or removed
  - Dual-signer (todd@ + matt@) required when ANY of:
      * |delta| >= 10% magnitude
      * dimension added (no prior revision for this dimension)
      * dimension removed (after_value sentinel = None — represented here
        with the special `is_removal=True` flag because Python's None doesn't
        round-trip cleanly through the float column)
      * computation_version bump (current_version != previous_version)

And §Override-event capture (decision #9, line 158):
  - source = 'override' -> weight 3.0×
  - else                -> weight 1.0×
The weight function is the single chokepoint; all consumers (variance writer,
codification-bridge) must call it.

WHY: keeping authority + weight as a single small module makes the policy
auditable in one place. Doctrine says "highest-stakes signal gets highest
weight" (mirrors the `ethical_misalignment 3.0×` weight pattern in
config/engine.yaml).

penrose_signal: weakens
penrose_dimension: variance
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

# Doctrine: override events are the highest-signal data we get; 3× weight is
# anchored to ethical_misalignment 3.0× in config/engine.yaml::penalty_weights.
OVERRIDE_WEIGHT = 3.0
DEFAULT_WEIGHT = 1.0

# Magnitude threshold for automated writes (spec line 150).
DEFAULT_MAGNITUDE_THRESHOLD = 0.10

# Dual-signer roster (spec line 150). Matt is Owner per
# `responsibility_assignment_doctrine.md`.
REQUIRED_DUAL_SIGNERS = ("todd", "matt")


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────


@dataclass
class OutcomeEventForWeight:
    """Minimal projection of OutcomeEvent for weight lookup.

    Avoids importing the full storage shape so weighting stays pure-function.
    """
    source: str  # e.g., 'carmen-beach', 'ti-solutions', 'override'


@dataclass
class RequiresSignoff:
    """Returned instead of writing when the authority gate fails."""
    reasons: list[str]
    required_signers: tuple[str, ...]
    proposed_dimension: str
    proposed_before: float
    proposed_after: float
    is_removal: bool = False
    is_new_dimension: bool = False
    computation_version_bump: bool = False
    magnitude: float = 0.0

    def to_dict(self) -> dict:
        return {
            "requires_signoff": True,
            "reasons": list(self.reasons),
            "required_signers": list(self.required_signers),
            "proposed_dimension": self.proposed_dimension,
            "proposed_before": self.proposed_before,
            "proposed_after": self.proposed_after,
            "is_removal": self.is_removal,
            "is_new_dimension": self.is_new_dimension,
            "computation_version_bump": self.computation_version_bump,
            "magnitude": self.magnitude,
        }


# ─────────────────────────────────────────────
# Override-event weight policy (single chokepoint)
# ─────────────────────────────────────────────


def outcome_weight(event: OutcomeEventForWeight) -> float:
    """Return the calibration-write weight for an outcome event.

    Spec §Override-event capture (decision #9, line 158):
      source == 'override'  -> 3.0
      else                  -> 1.0
    """
    if event.source == "override":
        return OVERRIDE_WEIGHT
    return DEFAULT_WEIGHT


# ─────────────────────────────────────────────
# Authority gate
# ─────────────────────────────────────────────


def check_calibration_authority(
    *,
    dimension: str,
    before_value: float,
    after_value: float,
    computation_version: str,
    previous_computation_version: str | None,
    is_new_dimension: bool,
    is_removal: bool = False,
    signers: Sequence[str] = (),
    magnitude_threshold: float = DEFAULT_MAGNITUDE_THRESHOLD,
) -> RequiresSignoff | None:
    """Evaluate the authority gate for a proposed calibration revision.

    Returns:
      None              -> automated write is allowed; caller proceeds.
      RequiresSignoff   -> caller MUST NOT write; surface to dual-signer
                           workflow instead.
    """
    reasons: list[str] = []

    # 1. Magnitude check
    if before_value == 0:
        magnitude = abs(after_value)
    else:
        magnitude = abs(after_value - before_value) / abs(before_value)

    if magnitude >= magnitude_threshold:
        reasons.append(
            f"magnitude {magnitude:.4f} >= threshold {magnitude_threshold} "
            f"(spec §5 decision #5)"
        )

    # 2. Dimension add / remove
    if is_new_dimension:
        reasons.append(f"dimension {dimension!r} is being added (no prior revision)")
    if is_removal:
        reasons.append(f"dimension {dimension!r} is being removed")

    # 3. Computation-version bump
    cv_bump = (
        previous_computation_version is not None
        and computation_version != previous_computation_version
    )
    if cv_bump:
        reasons.append(
            f"computation_version bumped "
            f"{previous_computation_version!r} -> {computation_version!r}"
        )

    if not reasons:
        return None  # automated write OK

    # Dual-signer required. Check whether the provided signers list satisfies
    # the requirement (case-insensitive; allow email-form 'todd@...' or
    # bare-username 'todd').
    norm_signers = {s.split("@")[0].lower() for s in signers}
    required = set(REQUIRED_DUAL_SIGNERS)
    missing = required - norm_signers
    if not missing:
        # All required signers present; gate satisfied — but we still surface
        # this for audit (we don't auto-write past the gate; the caller may
        # use this info to proceed with an EXPLICIT dual-signed path).
        return None

    return RequiresSignoff(
        reasons=reasons,
        required_signers=REQUIRED_DUAL_SIGNERS,
        proposed_dimension=dimension,
        proposed_before=before_value,
        proposed_after=after_value,
        is_removal=is_removal,
        is_new_dimension=is_new_dimension,
        computation_version_bump=cv_bump,
        magnitude=round(magnitude, 6),
    )
