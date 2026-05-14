"""Gate 5 now consults the pricing bridge for pricing-domain decisions.

Verifies the wiring closes B-05 fully:
  - is_pricing_decision()=False → bridge NOT consulted (no perf regression)
  - is_pricing_decision()=True + status=ok + guard_rail_status="ok"     → gate passes, note included
  - is_pricing_decision()=True + status=ok + guard_rail_status="violation" → gate FAILS with explanation
  - is_pricing_decision()=True + status=unavailable                     → gate result unchanged (observational)
"""
from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gates import gate_5_risk_containment
from engine.models import (
    DecisionClass,
    DecisionObject,
    ReversibilityTag,
    TimeHorizon,
    ValueScores,
)


def _clean_decision(action: str = "Send weekly newsletter") -> DecisionObject:
    """A decision that passes Gate 5 on its own — no risk/uncertainty issues."""
    return DecisionObject(
        decision_id="dec-1",
        title="Test",
        requested_action=action,
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        time_horizon=TimeHorizon.IMMEDIATE,
        value_scores=ValueScores(downside_risk=2, uncertainty=2),
        monitoring_metric="open_rate",
    )


def test_non_pricing_decision_skips_bridge_consult():
    """Bridge must NOT be called when decision isn't pricing-domain."""
    decision = _clean_decision(action="Send weekly newsletter")
    with mock.patch("engine.pricing_bridge.get_pricing_signal") as mock_signal:
        ok, rationale = gate_5_risk_containment(decision)
    assert ok is True
    mock_signal.assert_not_called()
    assert "pricing-engine" not in rationale


def test_pricing_decision_with_ok_signal_includes_note():
    """When bridge returns status=ok + guard_rail=ok, gate passes with note appended."""
    decision = _clean_decision(action="Adjust nightly pricing for property X")
    fake_envelope = {
        "status": "ok",
        "signal": {"guard_rail_status": "ok", "margin": 0.42},
        "engine_response": {},
        "consulted_at": "2026-05-13T22:00:00+00:00",
        "reason": None,
    }
    with mock.patch("engine.pricing_bridge.get_pricing_signal", return_value=fake_envelope):
        ok, rationale = gate_5_risk_containment(decision)
    assert ok is True
    assert "pricing-engine consulted: ok" in rationale
    assert "margin=0.42" in rationale


def test_pricing_decision_with_guard_rail_violation_fails_gate():
    """Guard-rail violation from gigaton-engine demotes the gate to FAIL."""
    decision = _clean_decision(action="Drop pricing 40% on Q4 inventory")
    fake_envelope = {
        "status": "ok",
        "signal": {
            "guard_rail_status": "violation",
            "warning": "Margin would drop below 20% minimum",
        },
        "engine_response": {},
        "consulted_at": "2026-05-13T22:00:00+00:00",
        "reason": None,
    }
    with mock.patch("engine.pricing_bridge.get_pricing_signal", return_value=fake_envelope):
        ok, rationale = gate_5_risk_containment(decision)
    assert ok is False
    assert "guard-rail violation" in rationale
    assert "Margin would drop below 20%" in rationale


def test_pricing_decision_with_unavailable_engine_is_observational():
    """gigaton-engine outage is logged but does NOT fail the gate (resilience)."""
    decision = _clean_decision(action="Adjust pricing")
    fake_envelope = {
        "status": "unavailable",
        "signal": None,
        "engine_response": None,
        "consulted_at": "2026-05-13T22:00:00+00:00",
        "reason": "gigaton-engine HTTP 503: down",
    }
    with mock.patch("engine.pricing_bridge.get_pricing_signal", return_value=fake_envelope):
        ok, rationale = gate_5_risk_containment(decision)
    assert ok is True
    assert "pricing-engine unavailable" in rationale


def test_existing_risk_issues_still_fail_independent_of_pricing():
    """Risk + pricing both can fail — pricing-bridge note appended to risk issues."""
    decision = _clean_decision(action="Adjust pricing")
    decision.value_scores.downside_risk = 5  # forces issue
    fake_envelope = {
        "status": "ok",
        "signal": {"guard_rail_status": "ok"},
        "engine_response": {},
        "consulted_at": "2026-05-13T22:00:00+00:00",
        "reason": None,
    }
    with mock.patch("engine.pricing_bridge.get_pricing_signal", return_value=fake_envelope):
        ok, rationale = gate_5_risk_containment(decision)
    assert ok is False
    assert "Downside risk" in rationale
    assert "pricing-engine consulted" in rationale  # note still appended


def test_pricing_bridge_exception_does_not_break_gate():
    """If pricing_bridge itself throws, gate must continue on its base rules."""
    decision = _clean_decision(action="Adjust pricing")
    with mock.patch("engine.pricing_bridge.get_pricing_signal", side_effect=RuntimeError("kaboom")):
        ok, rationale = gate_5_risk_containment(decision)
    assert ok is True  # base rules pass; bridge failure swallowed
    assert "skipped" in rationale or "internal error" in rationale
