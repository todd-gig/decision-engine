#!/usr/bin/env python3
"""
Executive Decision Engine — CLI Entry Point

Usage:
    python cli.py run                     # Start the API server
    python cli.py test                    # Run the 5-scenario test suite
    python cli.py process <payload.json>  # Process a single decision from JSON file
    python cli.py learning-summary        # Print institutional learning summary
    python cli.py seed-certs              # Seed trust certificates to memory/certs/
"""

import sys
import json
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_run():
    """Start the FastAPI server."""
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting Executive Decision Engine on port {port}...")
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)


def cmd_test():
    """Run the 5-scenario test suite."""
    from engine.runner import main
    success = main()
    sys.exit(0 if success else 1)


def cmd_process(payload_path: str):
    """Process a single decision from a JSON file."""
    from engine.models import (
        DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
        ValueScores, TrustScores, AlignmentScores,
    )
    from engine.config import load_config
    from engine.pipeline import process_decision
    from engine.audit import result_to_json

    with open(payload_path) as f:
        data = f.read()

    payload = json.loads(data)

    # Support both wrapped and unwrapped payloads
    if "decision" in payload:
        payload = payload["decision"]

    # Build decision object from flat payload
    vs_data = {}
    ts_data = {}
    for key in ["revenue_impact", "cost_efficiency", "time_leverage",
                "strategic_alignment", "customer_human_benefit",
                "knowledge_asset_creation", "compounding_potential",
                "reversibility", "downside_risk", "execution_drag",
                "uncertainty", "ethical_misalignment"]:
        if key in payload:
            vs_data[key] = payload[key]
        elif "positive_dimensions" in payload and key in payload["positive_dimensions"]:
            vs_data[key] = int(payload["positive_dimensions"][key])
        elif "penalty_dimensions" in payload and key in payload["penalty_dimensions"]:
            vs_data[key] = int(payload["penalty_dimensions"][key])

    # Map customer_benefit -> customer_human_benefit
    if "positive_dimensions" in payload:
        pd = payload["positive_dimensions"]
        vs_data.setdefault("revenue_impact", int(pd.get("revenue_impact", 0)))
        vs_data.setdefault("cost_efficiency", int(pd.get("cost_efficiency", 0)))
        vs_data.setdefault("time_leverage", int(pd.get("time_leverage", 0)))
        vs_data.setdefault("strategic_alignment", int(pd.get("strategic_alignment", 0)))
        vs_data.setdefault("customer_human_benefit", int(pd.get("customer_benefit", pd.get("customer_human_benefit", 0))))
        vs_data.setdefault("knowledge_asset_creation", int(pd.get("knowledge_creation", pd.get("knowledge_asset_creation", 0))))
        vs_data.setdefault("compounding_potential", int(pd.get("compounding_potential", 0)))
        vs_data.setdefault("reversibility", int(pd.get("reversibility", 0)))

    if "penalty_dimensions" in payload:
        pn = payload["penalty_dimensions"]
        vs_data.setdefault("downside_risk", int(pn.get("downside_risk", 0)))
        vs_data.setdefault("execution_drag", int(pn.get("execution_drag", 0)))
        vs_data.setdefault("uncertainty", int(pn.get("uncertainty", 0)))
        vs_data.setdefault("ethical_misalignment", int(pn.get("ethical_misalignment", 0)))

    if "trust_inputs" in payload:
        ti = payload["trust_inputs"]
        ts_data = {k: int(v) for k, v in ti.items()}

    decision = DecisionObject(
        title=payload.get("title", "CLI Decision"),
        decision_class=DecisionClass(payload.get("decision_class", "D1")),
        owner=payload.get("owner", payload.get("actor_role", "AI_Domain_Agent")),
        problem_statement=payload.get("problem_statement", payload.get("title", "")),
        requested_action=payload.get("requested_action", payload.get("title", "")),
        evidence_refs=payload.get("evidence_refs", ["cli_submission"]),
        stakeholders=payload.get("stakeholders", [payload.get("owner", "cli_user")]),
        current_state=payload.get("current_state", "draft"),
        actor_role=payload.get("actor_role", "AI_Domain_Agent"),
        has_missing_data=payload.get("has_missing_data", False),
        ethical_conflict=payload.get("ethical_conflict", False),
        value_scores=ValueScores(**{k: int(v) for k, v in vs_data.items() if hasattr(ValueScores, k)}),
        trust_scores=TrustScores(**{k: int(v) for k, v in ts_data.items() if hasattr(TrustScores, k)}),
    )

    config = load_config()
    result = process_decision(decision, config)

    print(result.executive_summary)
    print("\n--- Full JSON Output ---")
    print(result_to_json(result))


def cmd_learning_summary():
    """Print institutional learning summary."""
    from engine.learning_loop import LearningStore
    store = LearningStore()
    print(store.generate_learning_summary())


def cmd_seed_certs():
    """Seed trust certificates."""
    from engine.seed_certificates import main as seed_main
    seed_main()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "run":
        cmd_run()
    elif command == "test":
        cmd_test()
    elif command == "process":
        if len(sys.argv) < 3:
            print("Usage: python cli.py process <payload.json>")
            sys.exit(1)
        cmd_process(sys.argv[2])
    elif command == "learning-summary":
        cmd_learning_summary()
    elif command == "seed-certs":
        cmd_seed_certs()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
