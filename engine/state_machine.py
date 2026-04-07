"""
Decision State Machine

Lifecycle states with valid transitions from engine.yaml:

    draft → qualified → value_confirmed → trust_certified →
    execution_cleared → executed → reviewed → archived

Each state represents a decision's progress through the certification pipeline.
Backward transitions are allowed for re-qualification when conditions change.

State mapping to certificate chain:
    draft          → no certificates
    qualified      → QC issued
    value_confirmed → QC + VC issued
    trust_certified → QC + VC + TC issued
    execution_cleared → QC + VC + TC + EC issued
    executed       → post-execution, awaiting review
    reviewed       → learning loop complete
    archived       → decision lifecycle closed
"""

from .config import EngineConfig


# Default transitions if config not loaded
DEFAULT_TRANSITIONS = {
    "draft": ["qualified", "execution_cleared"],
    "qualified": ["value_confirmed", "draft"],
    "value_confirmed": ["trust_certified", "qualified"],
    "trust_certified": ["execution_cleared", "qualified"],
    "execution_cleared": ["executed", "trust_certified"],
    "executed": ["reviewed"],
    "reviewed": ["archived", "qualified"],
    "archived": [],
}

# State to certificate mapping
STATE_CERTIFICATE_MAP = {
    "draft": [],
    "qualified": ["QC"],
    "value_confirmed": ["QC", "VC"],
    "trust_certified": ["QC", "VC", "TC"],
    "execution_cleared": ["QC", "VC", "TC", "EC"],
    "executed": ["QC", "VC", "TC", "EC"],
    "reviewed": ["QC", "VC", "TC", "EC"],
    "archived": ["QC", "VC", "TC", "EC"],
}

# Map engine verdicts to target states
VERDICT_TO_STATE = {
    "auto_execute": "execution_cleared",
    "escalate_tier_1": "trust_certified",  # needs approval routing
    "escalate_tier_2": "trust_certified",
    "escalate_tier_3": "trust_certified",
    "block": "draft",  # reset to draft for re-evaluation
    "information_only": "qualified",
    "needs_data": "draft",
}


def can_transition(current_state: str, target_state: str,
                    config: EngineConfig = None) -> bool:
    """Check if a state transition is valid."""
    transitions = DEFAULT_TRANSITIONS
    if config and config.valid_transitions:
        transitions = config.valid_transitions

    allowed = transitions.get(current_state, [])
    return target_state in allowed


def next_state_for_action(current_state: str, action: str) -> str:
    """
    Determine the next state based on the engine's recommended action.
    """
    return VERDICT_TO_STATE.get(action, current_state)


def advance_state(current_state: str, target_state: str,
                   config: EngineConfig = None) -> dict:
    """
    Attempt to advance the decision to a new state.

    Returns:
        {
            "success": bool,
            "previous_state": str,
            "current_state": str,
            "reason": str,
            "required_certificates": list[str],
        }
    """
    if can_transition(current_state, target_state, config):
        return {
            "success": True,
            "previous_state": current_state,
            "current_state": target_state,
            "reason": f"Valid transition from '{current_state}' to '{target_state}'",
            "required_certificates": STATE_CERTIFICATE_MAP.get(target_state, []),
        }
    else:
        transitions = DEFAULT_TRANSITIONS
        if config and config.valid_transitions:
            transitions = config.valid_transitions
        allowed = transitions.get(current_state, [])
        return {
            "success": False,
            "previous_state": current_state,
            "current_state": current_state,
            "reason": f"Invalid transition from '{current_state}' to '{target_state}'. "
                      f"Allowed: {allowed}",
            "required_certificates": STATE_CERTIFICATE_MAP.get(current_state, []),
        }


def get_lifecycle_status(current_state: str) -> dict:
    """Get a summary of the decision's lifecycle position."""
    state_order = [
        "draft", "qualified", "value_confirmed", "trust_certified",
        "execution_cleared", "executed", "reviewed", "archived"
    ]
    idx = state_order.index(current_state) if current_state in state_order else 0
    progress = (idx / (len(state_order) - 1)) * 100

    return {
        "current_state": current_state,
        "progress_pct": round(progress, 1),
        "certificates_held": STATE_CERTIFICATE_MAP.get(current_state, []),
        "is_terminal": current_state == "archived",
        "is_executable": current_state == "execution_cleared",
        "is_pre_execution": current_state in ("draft", "qualified", "value_confirmed", "trust_certified"),
        "is_post_execution": current_state in ("executed", "reviewed", "archived"),
    }
