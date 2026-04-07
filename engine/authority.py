"""
Authority Engine — Role-based execution rights per decision class.

Implements the authority matrix from engine.yaml:
    D1: AI_Domain_Agent can execute at T3+, no approval needed
    D2: AI_Domain_Agent can execute at T3+, Domain_Owner approval
    D3: Domain_Owner executes at T2+, Human_Executive approval
    D4: Human_Executive executes at T2+, Human_CEO approval
    D5: Human_Executive executes at T1+, Human_CEO approval
    D6: Human_CEO executes at T1+, Human_CEO approval

Actor roles (ordered by authority):
    AI_Domain_Agent < Domain_Owner < Human_Executive < Human_CEO < Board
"""

from .models import DecisionClass, TrustTier
from .config import EngineConfig, AuthorityRule


# Role authority hierarchy — higher number = more authority
ROLE_HIERARCHY = {
    "AI_Domain_Agent": 1,
    "Domain_Owner": 2,
    "Human_Executive": 3,
    "Human_CEO": 4,
    "Board": 5,
}


def _role_gte(actor_role: str, required_role: str) -> bool:
    """Check if actor has sufficient authority."""
    return ROLE_HIERARCHY.get(actor_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


def _trust_gte(actual: str, minimum: str) -> bool:
    """Check if actual trust tier meets minimum."""
    tier_map = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4}
    return tier_map.get(actual, 0) >= tier_map.get(minimum, 0)


def authority_check(
    decision_class: DecisionClass,
    actor_role: str,
    trust_tier: TrustTier,
    config: EngineConfig,
) -> dict:
    """
    Check whether the given actor can execute this decision class
    at the current trust tier.

    Returns:
        {
            "can_execute": bool,
            "reason": str,
            "required_executor": str,
            "required_approval": str,
            "min_trust": str,
            "actor_sufficient": bool,
            "trust_sufficient": bool,
            "approval_required": bool,
        }
    """
    dc_key = decision_class.value  # e.g., "D1"
    rule: AuthorityRule = config.authority_matrix.get(
        dc_key,
        AuthorityRule(min_trust="T4", executor="Human_CEO", required_approval="Human_CEO")
    )

    trust_sufficient = _trust_gte(trust_tier.value, rule.min_trust)
    actor_sufficient = _role_gte(actor_role, rule.executor)
    approval_required = rule.required_approval != "none"

    can_execute = trust_sufficient and actor_sufficient

    if not trust_sufficient:
        reason = f"Trust tier {trust_tier.value} below minimum {rule.min_trust} for {dc_key}"
    elif not actor_sufficient:
        reason = f"Actor role '{actor_role}' insufficient — {dc_key} requires '{rule.executor}' or higher"
    elif approval_required:
        reason = f"Execution allowed but requires approval from '{rule.required_approval}'"
        # can_execute remains True — approval is a routing concern, not a block
    else:
        reason = f"Actor '{actor_role}' authorized to execute {dc_key} at {trust_tier.value}"

    return {
        "can_execute": can_execute,
        "reason": reason,
        "required_executor": rule.executor,
        "required_approval": rule.required_approval,
        "min_trust": rule.min_trust,
        "actor_sufficient": actor_sufficient,
        "trust_sufficient": trust_sufficient,
        "approval_required": approval_required,
    }
