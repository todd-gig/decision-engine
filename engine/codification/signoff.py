"""Sign-off routing for codification certificates.

A codification proposal touches different risk surfaces depending on
what kind of change it produces. The signer set must match the surface:

- "new-module"      → adds a deterministic module that replaces an
                      LLM call entirely → founder sign-off (todd@gigaton.ai)
- "tuning"          → adjusts thresholds / weights of an existing
                      codified path → owner sign-off (matt@gigaton.ai)
- "doctrine-touching" → modifies behavior that intersects canonical
                      doctrine (§5.7/5.8/anti-patterns) → both signers
- everything else   → default to founder sign-off (conservative)

Today this convention lives nowhere else in the codebase
(`engine/governance_gates.py` handles 30/60/90-day gates, not
human-signer routing). Promoting it to a tiny module keeps it
greppable and testable.

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

from typing import Final, Iterable


# Canonical signer identities. Mirrors the same identities used by
# the user-access-engine v0 bootstrap + the governance certificate chain.
FOUNDER_SIGNER: Final[str] = "todd@gigaton.ai"
OWNER_SIGNER: Final[str] = "matt@gigaton.ai"


# Decision class → required signer set (canonical).
DECISION_CLASS_SIGNERS: Final[dict[str, tuple[str, ...]]] = {
    "new-module": (FOUNDER_SIGNER,),
    "tuning": (OWNER_SIGNER,),
    "doctrine-touching": (FOUNDER_SIGNER, OWNER_SIGNER),
}


def required_signers(decision_class: str) -> list[str]:
    """Return the canonical signer list for a codification decision class.

    Unknown classes default to the conservative founder-only set; the
    sweep CLI surfaces a warning so operators notice unrecognized
    classes rather than silently defaulting.
    """
    key = (decision_class or "").strip().lower()
    if key in DECISION_CLASS_SIGNERS:
        return list(DECISION_CLASS_SIGNERS[key])
    return [FOUNDER_SIGNER]


def is_authorized(approver_user_id: str, decision_class: str) -> bool:
    """Approver must be in the required signer set for this class."""
    if not approver_user_id:
        return False
    return approver_user_id.strip().lower() in {
        s.lower() for s in required_signers(decision_class)
    }


def has_quorum(signers: Iterable[str], decision_class: str) -> bool:
    """For `doctrine-touching` we need BOTH signers; otherwise ≥1 listed."""
    required = {s.lower() for s in required_signers(decision_class)}
    given = {s.lower() for s in signers if s and isinstance(s, str)}
    if (decision_class or "").strip().lower() == "doctrine-touching":
        return required.issubset(given)
    # Single-signer flows: any one of the required must be present.
    return bool(required & given)


__all__ = [
    "FOUNDER_SIGNER",
    "OWNER_SIGNER",
    "DECISION_CLASS_SIGNERS",
    "required_signers",
    "is_authorized",
    "has_quorum",
]
