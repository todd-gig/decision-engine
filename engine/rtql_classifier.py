"""
RTQL Classifier Engine
Recursive Trust Qualification Loop — classifies input records into trust stages
and routes research actions based on failed qualification/certification gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Allowed dimension values
# ---------------------------------------------------------------------------
ALLOWED_SCORES = {0, 1, 2, 3, 4, 5, 6, 8, 10, 12}

# ---------------------------------------------------------------------------
# Trust stages
# ---------------------------------------------------------------------------
class TrustStage:
    NOISE = "noise"
    WEAK_SIGNAL = "weak_signal"
    ECHO_SIGNAL = "echo_signal"
    QUALIFIED = "qualified"
    CERTIFICATION_GAP = "certification_gap"
    CERTIFIED = "certified"
    RESEARCH_GRADE = "research_grade"
    FIRST_PRINCIPLES_CANDIDATE = "first_principles_candidate"
    AXIOM_CANDIDATE = "axiom_candidate"


TRUST_MULTIPLIERS: Dict[str, float] = {
    TrustStage.NOISE: 0.00,
    TrustStage.WEAK_SIGNAL: 0.35,
    TrustStage.ECHO_SIGNAL: 0.50,
    TrustStage.QUALIFIED: 1.00,
    TrustStage.CERTIFICATION_GAP: 0.85,
    TrustStage.CERTIFIED: 1.15,
    TrustStage.RESEARCH_GRADE: 1.30,
    TrustStage.FIRST_PRINCIPLES_CANDIDATE: 1.50,
    TrustStage.AXIOM_CANDIDATE: 2.00,
}

# ---------------------------------------------------------------------------
# Principle labels (ordered by increasing epistemic strength)
# ---------------------------------------------------------------------------
PRINCIPLE_LABELS = ["derived", "pattern", "mechanism", "principle", "axiom_candidate"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class InputRecord:
    """Full data model for an RTQL input record."""

    # --- 7 trust dimensions (must be in ALLOWED_SCORES) ---
    source_integrity: int = 0
    exposure_count: int = 0
    independence: int = 0
    explainability: int = 0
    replicability: int = 0
    adversarial_robustness: int = 0
    novelty_yield: int = 0

    # --- 4 causal checks ---
    reveals_causal_mechanism: bool = False
    is_irreducible: bool = False
    survives_authority_removal: bool = False
    survives_context_shift: bool = False

    # --- Optional metadata ---
    record_id: Optional[str] = None
    label: Optional[str] = None
    raw_value: float = 0.0

    def __post_init__(self) -> None:
        dims = [
            "source_integrity", "exposure_count", "independence",
            "explainability", "replicability", "adversarial_robustness",
            "novelty_yield",
        ]
        for dim in dims:
            val = getattr(self, dim)
            if val not in ALLOWED_SCORES:
                raise ValueError(
                    f"Dimension '{dim}' has value {val} which is not in "
                    f"allowed scores {sorted(ALLOWED_SCORES)}"
                )


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
class RTQLClassifier:
    """
    Classifies InputRecord instances into trust stages and provides
    supporting utilities (scoring, routing, value adjustment).
    """

    # Gate thresholds
    QUAL_GATE = {
        "source_integrity": 4,
        "exposure_count": 3,
        "independence": 4,
    }
    CERT_GATE = {
        "explainability": 6,
        "replicability": 6,
        "adversarial_robustness": 6,
    }
    NOVELTY_RESEARCH_GRADE = 6

    # Pre-qualification thresholds used for noise / weak_signal / echo_signal
    _NOISE_THRESHOLD = 1          # all dims <= this → noise
    _WEAK_SIGNAL_THRESHOLD = 2    # any dim <= this without meeting echo → weak_signal

    def classify(self, record: InputRecord) -> str:
        """
        Classify a record and return the trust stage string.

        Hierarchy (highest wins when all lower conditions met):
          axiom_candidate → first_principles_candidate → research_grade →
          certified → certification_gap → qualified →
          echo_signal → weak_signal → noise
        """
        dims = self.score_dimensions(record)

        # --- Pre-qualification tiers ---
        max_dim = max(dims.values())
        if max_dim <= self._NOISE_THRESHOLD:
            return TrustStage.NOISE

        # Check qualification gate
        qual_pass = self._passes_qual_gate(record)
        if not qual_pass:
            # Distinguish echo vs weak vs noise based on dimension averages
            avg = sum(dims.values()) / len(dims)
            if avg >= 2:
                return TrustStage.ECHO_SIGNAL
            return TrustStage.WEAK_SIGNAL

        # Qualified — now check certification gate
        cert_pass = self._passes_cert_gate(record)
        if not cert_pass:
            return TrustStage.CERTIFICATION_GAP

        # Certified — check research-grade novelty
        if record.novelty_yield >= self.NOVELTY_RESEARCH_GRADE:
            # Check first-principles
            if self._all_causal_checks(record):
                # Axiom candidate — reserved for external promotion; return FPC here
                return TrustStage.FIRST_PRINCIPLES_CANDIDATE
            return TrustStage.RESEARCH_GRADE

        return TrustStage.CERTIFIED

    def promote_to_axiom(self, record: InputRecord) -> str:
        """
        Explicitly promote a first_principles_candidate to axiom_candidate.
        Returns the new stage string.
        """
        stage = self.classify(record)
        if stage == TrustStage.FIRST_PRINCIPLES_CANDIDATE:
            return TrustStage.AXIOM_CANDIDATE
        return stage

    # ------------------------------------------------------------------
    # score_dimensions
    # ------------------------------------------------------------------
    def score_dimensions(self, record: InputRecord) -> Dict[str, int]:
        """Return a dict of all 7 trust dimension scores."""
        return {
            "source_integrity": record.source_integrity,
            "exposure_count": record.exposure_count,
            "independence": record.independence,
            "explainability": record.explainability,
            "replicability": record.replicability,
            "adversarial_robustness": record.adversarial_robustness,
            "novelty_yield": record.novelty_yield,
        }

    # ------------------------------------------------------------------
    # get_trust_multiplier
    # ------------------------------------------------------------------
    def get_trust_multiplier(self, stage: str) -> float:
        """Return the trust multiplier for a given stage."""
        if stage not in TRUST_MULTIPLIERS:
            raise ValueError(f"Unknown trust stage: '{stage}'")
        return TRUST_MULTIPLIERS[stage]

    # ------------------------------------------------------------------
    # route_research
    # ------------------------------------------------------------------
    def route_research(self, record: InputRecord, stage: str) -> List[str]:
        """
        Generate specific research actions for each failed gate.
        Returns an empty list when the stage is certified or higher.
        """
        actions: List[str] = []

        # Nothing actionable for noise
        if stage == TrustStage.NOISE:
            actions.append(
                "Discard or seek entirely new data sources — all dimensions are at noise floor."
            )
            return actions

        # Qualification gate failures
        if record.source_integrity < self.QUAL_GATE["source_integrity"]:
            gap = self.QUAL_GATE["source_integrity"] - record.source_integrity
            actions.append(
                f"QUAL-GATE | source_integrity: score {record.source_integrity} is "
                f"{gap} point(s) below threshold {self.QUAL_GATE['source_integrity']}. "
                "Action: Identify primary sources; cross-validate provenance; "
                "remove or flag unverifiable citations."
            )
        if record.exposure_count < self.QUAL_GATE["exposure_count"]:
            gap = self.QUAL_GATE["exposure_count"] - record.exposure_count
            actions.append(
                f"QUAL-GATE | exposure_count: score {record.exposure_count} is "
                f"{gap} point(s) below threshold {self.QUAL_GATE['exposure_count']}. "
                "Action: Seek additional independent observations or real-world trials."
            )
        if record.independence < self.QUAL_GATE["independence"]:
            gap = self.QUAL_GATE["independence"] - record.independence
            actions.append(
                f"QUAL-GATE | independence: score {record.independence} is "
                f"{gap} point(s) below threshold {self.QUAL_GATE['independence']}. "
                "Action: Source evidence from organisations/teams with no shared incentive."
            )

        # Certification gate failures (only relevant if qualification passed)
        if self._passes_qual_gate(record):
            if record.explainability < self.CERT_GATE["explainability"]:
                gap = self.CERT_GATE["explainability"] - record.explainability
                actions.append(
                    f"CERT-GATE | explainability: score {record.explainability} is "
                    f"{gap} point(s) below threshold {self.CERT_GATE['explainability']}. "
                    "Action: Document the mechanism step-by-step; produce an explanatory model."
                )
            if record.replicability < self.CERT_GATE["replicability"]:
                gap = self.CERT_GATE["replicability"] - record.replicability
                actions.append(
                    f"CERT-GATE | replicability: score {record.replicability} is "
                    f"{gap} point(s) below threshold {self.CERT_GATE['replicability']}. "
                    "Action: Design and run controlled replication studies."
                )
            if record.adversarial_robustness < self.CERT_GATE["adversarial_robustness"]:
                gap = self.CERT_GATE["adversarial_robustness"] - record.adversarial_robustness
                actions.append(
                    f"CERT-GATE | adversarial_robustness: score {record.adversarial_robustness} is "
                    f"{gap} point(s) below threshold {self.CERT_GATE['adversarial_robustness']}. "
                    "Action: Stress-test claim under adversarial conditions; invite structured critique."
                )

        # Research-grade / first-principles gap
        if stage in (TrustStage.CERTIFIED,):
            if record.novelty_yield < self.NOVELTY_RESEARCH_GRADE:
                gap = self.NOVELTY_RESEARCH_GRADE - record.novelty_yield
                actions.append(
                    f"RESEARCH-GRADE | novelty_yield: score {record.novelty_yield} is "
                    f"{gap} point(s) below threshold {self.NOVELTY_RESEARCH_GRADE}. "
                    "Action: Articulate what new understanding this generates; "
                    "compare against existing literature."
                )

        if stage == TrustStage.RESEARCH_GRADE:
            causal_map = {
                "reveals_causal_mechanism": record.reveals_causal_mechanism,
                "is_irreducible": record.is_irreducible,
                "survives_authority_removal": record.survives_authority_removal,
                "survives_context_shift": record.survives_context_shift,
            }
            action_hints = {
                "reveals_causal_mechanism": (
                    "Map the causal pathway; identify mediating variables."
                ),
                "is_irreducible": (
                    "Attempt to decompose further; confirm irreducibility through elimination."
                ),
                "survives_authority_removal": (
                    "Test whether the claim holds when all authority references are stripped."
                ),
                "survives_context_shift": (
                    "Apply the claim across multiple distinct contexts; document failures."
                ),
            }
            for check, passed in causal_map.items():
                if not passed:
                    actions.append(
                        f"FIRST-PRINCIPLES | {check}: check not satisfied. "
                        f"Action: {action_hints[check]}"
                    )

        return actions

    # ------------------------------------------------------------------
    # adjust_value
    # ------------------------------------------------------------------
    def adjust_value(self, raw_value: float, stage: str) -> float:
        """
        Multiply raw_value by the trust multiplier for the given stage.
        Returns 0.0 for noise regardless of raw_value.
        """
        return raw_value * self.get_trust_multiplier(stage)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _passes_qual_gate(self, record: InputRecord) -> bool:
        return (
            record.source_integrity >= self.QUAL_GATE["source_integrity"]
            and record.exposure_count >= self.QUAL_GATE["exposure_count"]
            and record.independence >= self.QUAL_GATE["independence"]
        )

    def _passes_cert_gate(self, record: InputRecord) -> bool:
        return (
            record.explainability >= self.CERT_GATE["explainability"]
            and record.replicability >= self.CERT_GATE["replicability"]
            and record.adversarial_robustness >= self.CERT_GATE["adversarial_robustness"]
        )

    def _all_causal_checks(self, record: InputRecord) -> bool:
        return (
            record.reveals_causal_mechanism
            and record.is_irreducible
            and record.survives_authority_removal
            and record.survives_context_shift
        )
