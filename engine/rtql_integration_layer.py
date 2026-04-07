"""
RTQL Integration Layer — Registry Mutation Control Plane

Enforces the Recursive Trust Qualification Loop (RTQL) before any entry
is written, upgraded, promoted, or allowed to influence downstream reasoning.

No entry may be created as a durable knowledge entry, upgraded in trust stage,
promoted in causal type, linked as a dependency, or used to influence the value
matrix until it has passed the applicable RTQL gate.

Write policy:
    noise               -> reject or quarantine
    weak_signal         -> staging only
    echo_signal         -> staging with independence warning
    qualified           -> candidate_registry
    certification_gap   -> candidate_registry
    certified           -> operational_registry
    research_grade      -> insight_registry
    first_principles_candidate -> principles_registry
    axiom_candidate     -> axiom_review_queue (governance only)

Upgrade map (no skipping):
    weak_signal         -> qualified
    echo_signal         -> qualified
    qualified           -> certified
    certification_gap   -> certified
    certified           -> research_grade
    research_grade      -> first_principles_candidate
    first_principles_candidate -> axiom_candidate

Stage gates:
    Qualification:    source_integrity >= 4, exposure_count >= 3, independence >= 4
    Certification:    explainability >= 6, replicability >= 6, adversarial_robustness >= 6
    Research-grade:   certified + novelty_yield >= 6
    First-principles: all 4 causal checks pass
    Axiom:            first_principles + broad domain transferability + governance approval
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .models import RTQLStage, WriteTarget


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

# Canonical write target map — single source of truth
_WRITE_TARGET_MAP: dict[str, str] = {
    RTQLStage.NOISE.value:                        WriteTarget.QUARANTINE.value,
    RTQLStage.WEAK_SIGNAL.value:                  WriteTarget.STAGING.value,
    RTQLStage.ECHO_SIGNAL.value:                  WriteTarget.STAGING.value,
    RTQLStage.QUALIFIED.value:                    WriteTarget.CANDIDATE_REGISTRY.value,
    RTQLStage.CERTIFICATION_GAP.value:            WriteTarget.CANDIDATE_REGISTRY.value,
    RTQLStage.CERTIFIED.value:                    WriteTarget.OPERATIONAL_REGISTRY.value,
    RTQLStage.RESEARCH_GRADE.value:               WriteTarget.INSIGHT_REGISTRY.value,
    RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value:   WriteTarget.PRINCIPLES_REGISTRY.value,
    RTQLStage.AXIOM_CANDIDATE.value:              WriteTarget.AXIOM_REVIEW_QUEUE.value,
}

# Valid single-step upgrade transitions — no skipping allowed
_VALID_UPGRADE_PATHS: dict[str, str] = {
    RTQLStage.WEAK_SIGNAL.value:                RTQLStage.QUALIFIED.value,
    RTQLStage.ECHO_SIGNAL.value:                RTQLStage.QUALIFIED.value,
    RTQLStage.QUALIFIED.value:                  RTQLStage.CERTIFIED.value,
    RTQLStage.CERTIFICATION_GAP.value:          RTQLStage.CERTIFIED.value,
    RTQLStage.CERTIFIED.value:                  RTQLStage.RESEARCH_GRADE.value,
    RTQLStage.RESEARCH_GRADE.value:             RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value,
    RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value: RTQLStage.AXIOM_CANDIDATE.value,
}

# Stages that cannot be created/written as durable entries without constraints
_REJECT_STAGES = {RTQLStage.NOISE.value}

# Stages with special warnings on write
_ECHO_WARNING = "Independence not confirmed — entry may reflect echo chamber or authority bias"

# Gate score thresholds (from RTQL spec)
_QUAL_SOURCE_INTEGRITY = 4
_QUAL_EXPOSURE_COUNT = 3
_QUAL_INDEPENDENCE = 4
_CERT_EXPLAINABILITY = 6
_CERT_REPLICABILITY = 6
_CERT_ADVERSARIAL_ROBUSTNESS = 6
_RG_NOVELTY_YIELD = 6


# ─────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────

@dataclass
class MutationRequest:
    """
    Structured input contract for every registry write, upgrade, downgrade,
    relink, or reclassify operation.

    Fields:
        action:             One of: create | upgrade | downgrade | relink | reclassify
        entry_id:           Registry identifier (optional for create)
        proposed_statement: The claim or knowledge entry being mutated
        current_stage:      Current RTQL stage of the entry (optional for create)
        target_stage:       Requested target RTQL stage
        source_summary:     Brief description of the origin of the claim
        evidence:           List of supporting evidence strings
        scores:             Dict with RTQL score keys (source_integrity, exposure_count,
                            independence, explainability, replicability,
                            adversarial_robustness, novelty_yield)
        causal_checks:      Dict with boolean causal keys (reveals_causal_mechanism,
                            is_irreducible, survives_authority_removal,
                            survives_context_shift)
        requested_by:       Identifier for the requesting agent or user
        notes:              Free-text context notes
    """
    action: str                              # create | upgrade | downgrade | relink | reclassify
    entry_id: Optional[str]
    proposed_statement: str
    current_stage: Optional[str]
    target_stage: str
    source_summary: str
    evidence: list[str]
    scores: dict                             # keyed by RTQL score dimension names
    causal_checks: dict                      # keyed by causal check names
    requested_by: str
    notes: str = ""


@dataclass
class MutationDecision:
    """
    Output contract for every RTQL mutation evaluation.

    Fields:
        approved:             Whether the mutation is approved
        action:               Effective action taken (may differ from requested)
        assigned_stage:       The RTQL stage assigned to the entry after this decision
        target_stage_passed:  Whether the requested target stage gate was satisfied
        reasons:              List of positive or negative decision reasons
        missing_requirements: List of unmet gate requirements
        research_actions:     Recommended steps to advance to the target stage
        write_target:         Registry destination for the assigned stage
        audit_log:            Audit-ready dict with decision_basis and risk_note
    """
    approved: bool
    action: str
    assigned_stage: str
    target_stage_passed: bool
    reasons: list[str]
    missing_requirements: list[str]
    research_actions: list[str]
    write_target: str
    audit_log: dict


# ─────────────────────────────────────────────
# RTQL INTEGRATION LAYER
# ─────────────────────────────────────────────

class RTQLIntegrationLayer:
    """
    Enforces RTQL classification before any registry mutation is committed.

    Usage:
        layer = RTQLIntegrationLayer()
        decision = layer.process_mutation(request)
        if decision.approved:
            registry.write(decision.write_target, entry)
    """

    def process_mutation(self, request: MutationRequest) -> MutationDecision:
        """
        Evaluate a mutation request against RTQL gates.

        Decision flow:
          1. Validate upgrade path legality (no skipping).
          2. Check the gate for the target stage.
          3. If gate passes  -> approve, assign target_stage, route write target.
          4. If gate fails   -> block promotion, preserve/assign safe stage,
                               emit missing_requirements and research_actions.
          5. Produce audit_log.

        Returns:
            MutationDecision with complete audit trail.
        """
        scores = request.scores
        causal = request.causal_checks
        target = request.target_stage
        current = request.current_stage
        action = request.action

        reasons: list[str] = []
        missing: list[str] = []
        research: list[str] = []

        # ── Step 1: Validate upgrade path ──
        if action in ("upgrade",) and current is not None:
            path_valid = self._validate_upgrade_path(current, target)
            if not path_valid:
                reasons.append(
                    f"Upgrade path {current} -> {target} is not a valid single-step "
                    f"transition. Permitted next step: "
                    f"{_VALID_UPGRADE_PATHS.get(current, 'none')}"
                )
                assigned_stage = current
                write_target = self._determine_write_target(assigned_stage)
                return MutationDecision(
                    approved=False,
                    action="hold",
                    assigned_stage=assigned_stage,
                    target_stage_passed=False,
                    reasons=reasons,
                    missing_requirements=["Valid single-step upgrade path required"],
                    research_actions=[
                        f"Progress through intermediate stage "
                        f"{_VALID_UPGRADE_PATHS.get(current, 'unknown')} first"
                    ],
                    write_target=write_target,
                    audit_log=self._build_audit_log(
                        request=request,
                        assigned_stage=assigned_stage,
                        approved=False,
                        decision_basis="Upgrade path violation — stage skipping is not permitted",
                        risk_note="Entry stage skipping contaminates ontology integrity",
                    ),
                )

        # ── Step 2: Evaluate the target stage gate ──
        gate_passed, gate_missing = self._check_gate(target, scores, causal)

        # ── Step 3 / 4: Route the decision ──
        if gate_passed:
            assigned_stage = target
            reasons.append(f"Target stage gate '{target}' passed all required checks")

            # Echo signal gets a standing independence warning on any write
            if assigned_stage == RTQLStage.ECHO_SIGNAL.value:
                reasons.append(_ECHO_WARNING)

            # Noise is constrained — route to quarantine, mark as limited write
            if assigned_stage == RTQLStage.NOISE.value:
                approved = False
                effective_action = "quarantine"
                reasons.append("Noise entries are not written as durable entries")
            else:
                approved = True
                effective_action = action

            write_target = self._determine_write_target(assigned_stage)
            decision_basis = (
                f"Target stage '{target}' passed all required gates. "
                f"Routed to {write_target}."
            )
            risk_note = self._risk_note_for_stage(assigned_stage)

        else:
            # Gate failed — block promotion, preserve safe stage
            missing = gate_missing
            research = self._generate_research_actions(target, scores, causal)

            # Assign the safe fallback stage
            assigned_stage = self._safe_fallback_stage(current, target, scores, causal)
            approved = False
            effective_action = "hold"

            reasons.append(
                f"Target stage gate '{target}' failed — entry held at '{assigned_stage}'"
            )
            if assigned_stage == RTQLStage.ECHO_SIGNAL.value:
                reasons.append(_ECHO_WARNING)

            write_target = self._determine_write_target(assigned_stage)
            decision_basis = (
                f"Target stage '{target}' failed gate checks. "
                f"Entry assigned to '{assigned_stage}' pending evidence."
            )
            risk_note = (
                f"Do not promote until the following are resolved: "
                f"{'; '.join(missing) if missing else 'see missing_requirements'}"
            )

        return MutationDecision(
            approved=approved,
            action=effective_action,
            assigned_stage=assigned_stage,
            target_stage_passed=gate_passed,
            reasons=reasons,
            missing_requirements=missing,
            research_actions=research,
            write_target=write_target,
            audit_log=self._build_audit_log(
                request=request,
                assigned_stage=assigned_stage,
                approved=approved,
                decision_basis=decision_basis,
                risk_note=risk_note,
            ),
        )

    # ─────────────────────────────────────────────
    # GATE CHECKER
    # ─────────────────────────────────────────────

    def _check_gate(
        self,
        target_stage: str,
        scores: dict,
        causal_checks: dict,
    ) -> tuple[bool, list[str]]:
        """
        Evaluate whether all requirements for target_stage are satisfied.

        Returns:
            (passed: bool, missing_requirements: list[str])
        """
        missing: list[str] = []

        si  = scores.get("source_integrity", 0)
        ec  = scores.get("exposure_count", 0)
        ind = scores.get("independence", 0)
        exp = scores.get("explainability", 0)
        rep = scores.get("replicability", 0)
        arb = scores.get("adversarial_robustness", 0)
        ny  = scores.get("novelty_yield", 0)

        rcm = causal_checks.get("reveals_causal_mechanism", False)
        irr = causal_checks.get("is_irreducible", False)
        sar = causal_checks.get("survives_authority_removal", False)
        scs = causal_checks.get("survives_context_shift", False)
        bdt = causal_checks.get("broad_domain_transferability", False)
        gov = causal_checks.get("governance_approved", False)

        # ── Noise / weak_signal / echo_signal: always passable at write time ──
        if target_stage in (
            RTQLStage.NOISE.value,
            RTQLStage.WEAK_SIGNAL.value,
            RTQLStage.ECHO_SIGNAL.value,
        ):
            return True, []

        # ── Qualification Gate ──
        if target_stage in (
            RTQLStage.QUALIFIED.value,
            RTQLStage.CERTIFICATION_GAP.value,
        ):
            if si < _QUAL_SOURCE_INTEGRITY:
                missing.append(
                    f"source_integrity {si} < {_QUAL_SOURCE_INTEGRITY} (qualification gate)"
                )
            if ec < _QUAL_EXPOSURE_COUNT:
                missing.append(
                    f"exposure_count {ec} < {_QUAL_EXPOSURE_COUNT} (qualification gate)"
                )
            if ind < _QUAL_INDEPENDENCE:
                missing.append(
                    f"independence {ind} < {_QUAL_INDEPENDENCE} (qualification gate)"
                )
            return len(missing) == 0, missing

        # ── Certification Gate ──
        if target_stage == RTQLStage.CERTIFIED.value:
            # Must first pass qualification
            if si < _QUAL_SOURCE_INTEGRITY:
                missing.append(
                    f"source_integrity {si} < {_QUAL_SOURCE_INTEGRITY} (qualification gate)"
                )
            if ec < _QUAL_EXPOSURE_COUNT:
                missing.append(
                    f"exposure_count {ec} < {_QUAL_EXPOSURE_COUNT} (qualification gate)"
                )
            if ind < _QUAL_INDEPENDENCE:
                missing.append(
                    f"independence {ind} < {_QUAL_INDEPENDENCE} (qualification gate)"
                )
            if exp < _CERT_EXPLAINABILITY:
                missing.append(
                    f"explainability {exp} < {_CERT_EXPLAINABILITY} (certification gate)"
                )
            if rep < _CERT_REPLICABILITY:
                missing.append(
                    f"replicability {rep} < {_CERT_REPLICABILITY} (certification gate)"
                )
            if arb < _CERT_ADVERSARIAL_ROBUSTNESS:
                missing.append(
                    f"adversarial_robustness {arb} < {_CERT_ADVERSARIAL_ROBUSTNESS} "
                    f"(certification gate)"
                )
            return len(missing) == 0, missing

        # ── Research-Grade Gate ──
        if target_stage == RTQLStage.RESEARCH_GRADE.value:
            if si < _QUAL_SOURCE_INTEGRITY:
                missing.append(
                    f"source_integrity {si} < {_QUAL_SOURCE_INTEGRITY} (qualification gate)"
                )
            if ec < _QUAL_EXPOSURE_COUNT:
                missing.append(
                    f"exposure_count {ec} < {_QUAL_EXPOSURE_COUNT} (qualification gate)"
                )
            if ind < _QUAL_INDEPENDENCE:
                missing.append(
                    f"independence {ind} < {_QUAL_INDEPENDENCE} (qualification gate)"
                )
            if exp < _CERT_EXPLAINABILITY:
                missing.append(
                    f"explainability {exp} < {_CERT_EXPLAINABILITY} (certification gate)"
                )
            if rep < _CERT_REPLICABILITY:
                missing.append(
                    f"replicability {rep} < {_CERT_REPLICABILITY} (certification gate)"
                )
            if arb < _CERT_ADVERSARIAL_ROBUSTNESS:
                missing.append(
                    f"adversarial_robustness {arb} < {_CERT_ADVERSARIAL_ROBUSTNESS} "
                    f"(certification gate)"
                )
            if ny < _RG_NOVELTY_YIELD:
                missing.append(
                    f"novelty_yield {ny} < {_RG_NOVELTY_YIELD} (research-grade gate)"
                )
            return len(missing) == 0, missing

        # ── First-Principles Gate ──
        if target_stage == RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value:
            # Must pass research-grade baseline
            if si < _QUAL_SOURCE_INTEGRITY:
                missing.append(
                    f"source_integrity {si} < {_QUAL_SOURCE_INTEGRITY}"
                )
            if ec < _QUAL_EXPOSURE_COUNT:
                missing.append(f"exposure_count {ec} < {_QUAL_EXPOSURE_COUNT}")
            if ind < _QUAL_INDEPENDENCE:
                missing.append(f"independence {ind} < {_QUAL_INDEPENDENCE}")
            if exp < _CERT_EXPLAINABILITY:
                missing.append(f"explainability {exp} < {_CERT_EXPLAINABILITY}")
            if rep < _CERT_REPLICABILITY:
                missing.append(f"replicability {rep} < {_CERT_REPLICABILITY}")
            if arb < _CERT_ADVERSARIAL_ROBUSTNESS:
                missing.append(
                    f"adversarial_robustness {arb} < {_CERT_ADVERSARIAL_ROBUSTNESS}"
                )
            if ny < _RG_NOVELTY_YIELD:
                missing.append(f"novelty_yield {ny} < {_RG_NOVELTY_YIELD}")
            # Four causal checks
            if not rcm:
                missing.append(
                    "reveals_causal_mechanism = False (first-principles gate)"
                )
            if not irr:
                missing.append(
                    "is_irreducible = False (first-principles gate)"
                )
            if not sar:
                missing.append(
                    "survives_authority_removal = False (first-principles gate)"
                )
            if not scs:
                missing.append(
                    "survives_context_shift = False (first-principles gate)"
                )
            return len(missing) == 0, missing

        # ── Axiom Gate ──
        if target_stage == RTQLStage.AXIOM_CANDIDATE.value:
            # Must pass first-principles baseline
            if si < _QUAL_SOURCE_INTEGRITY:
                missing.append(f"source_integrity {si} < {_QUAL_SOURCE_INTEGRITY}")
            if ec < _QUAL_EXPOSURE_COUNT:
                missing.append(f"exposure_count {ec} < {_QUAL_EXPOSURE_COUNT}")
            if ind < _QUAL_INDEPENDENCE:
                missing.append(f"independence {ind} < {_QUAL_INDEPENDENCE}")
            if exp < _CERT_EXPLAINABILITY:
                missing.append(f"explainability {exp} < {_CERT_EXPLAINABILITY}")
            if rep < _CERT_REPLICABILITY:
                missing.append(f"replicability {rep} < {_CERT_REPLICABILITY}")
            if arb < _CERT_ADVERSARIAL_ROBUSTNESS:
                missing.append(
                    f"adversarial_robustness {arb} < {_CERT_ADVERSARIAL_ROBUSTNESS}"
                )
            if ny < _RG_NOVELTY_YIELD:
                missing.append(f"novelty_yield {ny} < {_RG_NOVELTY_YIELD}")
            if not rcm:
                missing.append("reveals_causal_mechanism = False")
            if not irr:
                missing.append("is_irreducible = False")
            if not sar:
                missing.append("survives_authority_removal = False")
            if not scs:
                missing.append("survives_context_shift = False")
            # Axiom-specific requirements
            if not bdt:
                missing.append(
                    "broad_domain_transferability = False (axiom gate)"
                )
            if not gov:
                missing.append(
                    "governance_approved = False — explicit governance approval required (axiom gate)"
                )
            return len(missing) == 0, missing

        # Unknown target stage
        missing.append(f"Unrecognized target_stage '{target_stage}'")
        return False, missing

    # ─────────────────────────────────────────────
    # WRITE TARGET RESOLVER
    # ─────────────────────────────────────────────

    def _determine_write_target(self, stage: str) -> str:
        """
        Return the canonical write target for a given RTQL stage string.

        Falls back to 'quarantine' for unrecognized stages.
        """
        return _WRITE_TARGET_MAP.get(stage, WriteTarget.QUARANTINE.value)

    # ─────────────────────────────────────────────
    # UPGRADE PATH VALIDATOR
    # ─────────────────────────────────────────────

    def _validate_upgrade_path(self, current: str, target: str) -> bool:
        """
        Return True only if current -> target is a valid single-step upgrade.

        Stage skipping is never permitted.
        Downgrades are not validated here — they are always single-step
        by convention (handled separately in process_mutation if needed).
        """
        return _VALID_UPGRADE_PATHS.get(current) == target

    # ─────────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────────

    def _safe_fallback_stage(
        self,
        current: Optional[str],
        target: str,
        scores: dict,
        causal: dict,
    ) -> str:
        """
        Determine the highest stage the entry actually qualifies for,
        to be used when the target gate fails.

        Prefers the current stage if it passes, otherwise walks down
        to find the highest valid assignment.
        """
        # If current stage is provided and passes its own gate, keep it
        if current is not None:
            current_passed, _ = self._check_gate(current, scores, causal)
            if current_passed:
                return current

        # Walk down the stage ladder to find the highest passing stage
        stage_ladder = [
            RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value,
            RTQLStage.RESEARCH_GRADE.value,
            RTQLStage.CERTIFIED.value,
            RTQLStage.CERTIFICATION_GAP.value,
            RTQLStage.QUALIFIED.value,
            RTQLStage.ECHO_SIGNAL.value,
            RTQLStage.WEAK_SIGNAL.value,
            RTQLStage.NOISE.value,
        ]
        # Only walk stages below the target
        try:
            target_idx = stage_ladder.index(target)
            candidates = stage_ladder[target_idx + 1:]
        except ValueError:
            candidates = stage_ladder

        for stage in candidates:
            passed, _ = self._check_gate(stage, scores, causal)
            if passed:
                return stage

        return RTQLStage.NOISE.value

    def _generate_research_actions(
        self,
        target_stage: str,
        scores: dict,
        causal: dict,
    ) -> list[str]:
        """
        Generate minimum-viable research actions required to advance to target_stage.
        """
        actions: list[str] = []

        si  = scores.get("source_integrity", 0)
        ec  = scores.get("exposure_count", 0)
        ind = scores.get("independence", 0)
        exp = scores.get("explainability", 0)
        rep = scores.get("replicability", 0)
        arb = scores.get("adversarial_robustness", 0)
        ny  = scores.get("novelty_yield", 0)

        rcm = causal.get("reveals_causal_mechanism", False)
        irr = causal.get("is_irreducible", False)
        sar = causal.get("survives_authority_removal", False)
        scs = causal.get("survives_context_shift", False)
        bdt = causal.get("broad_domain_transferability", False)
        gov = causal.get("governance_approved", False)

        # Qualification gap actions
        if si < _QUAL_SOURCE_INTEGRITY:
            actions.append(
                "Locate or establish an auditable source trail with integrity >= 4"
            )
        if ec < _QUAL_EXPOSURE_COUNT:
            actions.append(
                "Monitor for repeat appearances in at least 3 independent contexts"
            )
        if ind < _QUAL_INDEPENDENCE:
            actions.append(
                "Seek cross-domain or structurally independent confirmation (independence >= 4)"
            )

        # Certification gap actions
        if target_stage in (
            RTQLStage.CERTIFIED.value,
            RTQLStage.RESEARCH_GRADE.value,
            RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value,
            RTQLStage.AXIOM_CANDIDATE.value,
        ):
            if exp < _CERT_EXPLAINABILITY:
                actions.append(
                    "Decompose the claim into causal variables and mechanism (explainability >= 6)"
                )
            if rep < _CERT_REPLICABILITY:
                actions.append(
                    "Define and execute a replication protocol (replicability >= 6)"
                )
            if arb < _CERT_ADVERSARIAL_ROBUSTNESS:
                actions.append(
                    "Design and run adversarial/red-team test for this claim "
                    "(adversarial_robustness >= 6)"
                )

        # Research-grade gap actions
        if target_stage in (
            RTQLStage.RESEARCH_GRADE.value,
            RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value,
            RTQLStage.AXIOM_CANDIDATE.value,
        ):
            if ny < _RG_NOVELTY_YIELD:
                actions.append(
                    "Assess whether the entry produces materially new information "
                    "or improves predictive quality (novelty_yield >= 6)"
                )

        # First-principles gap actions
        if target_stage in (
            RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value,
            RTQLStage.AXIOM_CANDIDATE.value,
        ):
            if not rcm:
                actions.append("Identify and document the underlying causal mechanism")
            if not irr:
                actions.append(
                    "Test irreducibility — verify this cannot be decomposed "
                    "without losing explanatory power"
                )
            if not sar:
                actions.append(
                    "Verify the claim holds independently of the authority that asserted it"
                )
            if not scs:
                actions.append(
                    "Test the claim across at least two materially different operational contexts"
                )

        # Axiom gap actions
        if target_stage == RTQLStage.AXIOM_CANDIDATE.value:
            if not bdt:
                actions.append(
                    "Demonstrate broad domain transferability across unrelated fields"
                )
            if not gov:
                actions.append(
                    "Obtain explicit governance approval before promoting to axiom_candidate"
                )

        return actions

    def _risk_note_for_stage(self, stage: str) -> str:
        """Return a standing risk note appropriate for the assigned stage."""
        notes = {
            RTQLStage.NOISE.value: (
                "Entry is noise — do not write to durable registry"
            ),
            RTQLStage.WEAK_SIGNAL.value: (
                "Weak signal — entry is in staging only; not eligible to influence decisions"
            ),
            RTQLStage.ECHO_SIGNAL.value: (
                "Echo signal — independence not confirmed; monitor for confirmation bias"
            ),
            RTQLStage.QUALIFIED.value: (
                "Qualified entry — eligible for candidate registry; "
                "not yet certified for operational use"
            ),
            RTQLStage.CERTIFICATION_GAP.value: (
                "Certification gap — qualification passed but certification incomplete; "
                "in candidate registry pending cert evidence"
            ),
            RTQLStage.CERTIFIED.value: (
                "Certified entry — eligible for operational registry with standard trust multiplier"
            ),
            RTQLStage.RESEARCH_GRADE.value: (
                "Research-grade entry — eligible for insight registry; "
                "not yet first-principles candidate"
            ),
            RTQLStage.FIRST_PRINCIPLES_CANDIDATE.value: (
                "First-principles candidate — eligible for principles registry; "
                "axiom promotion requires governance review"
            ),
            RTQLStage.AXIOM_CANDIDATE.value: (
                "Axiom candidate — governance-only write to axiom_review_queue"
            ),
        }
        return notes.get(stage, "Unknown stage — manual review required")

    def _build_audit_log(
        self,
        request: MutationRequest,
        assigned_stage: str,
        approved: bool,
        decision_basis: str,
        risk_note: str,
    ) -> dict:
        """Build an audit-ready log dict for this mutation decision."""
        return {
            "audit_id": f"RTQL-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": datetime.now().isoformat(),
            "entry_id": request.entry_id,
            "requested_action": request.action,
            "requested_by": request.requested_by,
            "current_stage": request.current_stage,
            "target_stage": request.target_stage,
            "assigned_stage": assigned_stage,
            "approved": approved,
            "decision_basis": decision_basis,
            "risk_note": risk_note,
            "scores_snapshot": dict(request.scores),
            "causal_checks_snapshot": dict(request.causal_checks),
            "evidence_count": len(request.evidence),
            "notes": request.notes,
        }
