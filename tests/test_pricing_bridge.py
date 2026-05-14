"""Tests for engine.pricing_bridge — heuristic detection + signal envelope."""
from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import (
    DecisionClass,
    DecisionObject,
    ReversibilityTag,
    TimeHorizon,
)
from engine.pricing_bridge import (
    _build_pricing_payload,
    get_pricing_signal,
    is_pricing_decision,
)
from gigaton_client import GigatonClient, GigatonClientError


def _decision(**overrides) -> DecisionObject:
    base = dict(
        decision_id="d-1",
        title="Test decision",
        problem_statement="Just testing",
        requested_action="Do the thing",
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        time_horizon=TimeHorizon.IMMEDIATE,
    )
    base.update(overrides)
    return DecisionObject(**base)


# ── is_pricing_decision heuristic ─────────────────────────────────────────────


@pytest.mark.parametrize("action", [
    "Adjust nightly rate for property X",
    "Raise pricing for shoulder season",
    "Apply 10% discount to early-bird bookings",
    "Recalculate margin on Q3 inventory",
    "Update markup for premium properties",
    "Set tariff for new affiliate partner",
    "Approve payout schedule",
    "Quote ADR for owner",
])
def test_pricing_keywords_match(action):
    d = _decision(requested_action=action)
    assert is_pricing_decision(d) is True


@pytest.mark.parametrize("action", [
    "Send weekly customer newsletter",
    "Onboard new operator",
    "Generate intelligence brief",
    "Approve content publication",
])
def test_non_pricing_keywords_dont_match(action):
    d = _decision(requested_action=action)
    assert is_pricing_decision(d) is False


def test_heuristic_checks_title_too():
    d = _decision(requested_action="generic action", title="Pricing review Q3")
    assert is_pricing_decision(d) is True


def test_heuristic_checks_problem_statement_too():
    d = _decision(
        requested_action="generic",
        title="Plain title",
        problem_statement="The margin on Q4 inventory needs investigation",
    )
    assert is_pricing_decision(d) is True


# ── get_pricing_signal envelope ───────────────────────────────────────────────


def test_signal_skipped_when_decision_is_not_pricing(monkeypatch):
    monkeypatch.setenv("DECISION_PRICING_BRIDGE_ENABLED", "1")
    d = _decision(requested_action="Send weekly newsletter")
    result = get_pricing_signal(d)
    assert result["status"] == "skipped"
    assert result["signal"] is None
    assert result["engine_response"] is None
    assert "pricing heuristics" in result["reason"]


def test_signal_skipped_when_bridge_disabled(monkeypatch):
    monkeypatch.setenv("DECISION_PRICING_BRIDGE_ENABLED", "0")
    d = _decision(requested_action="Adjust nightly pricing")
    result = get_pricing_signal(d)
    assert result["status"] == "skipped"
    assert "DECISION_PRICING_BRIDGE_ENABLED=0" in result["reason"]


def test_signal_ok_when_engine_returns_data(monkeypatch):
    monkeypatch.setenv("DECISION_PRICING_BRIDGE_ENABLED", "1")
    d = _decision(requested_action="Adjust nightly pricing for property 123")
    fake_response = {
        "nightly_rate": 180,
        "margin": 0.42,
        "recommendation": "hold",
        "confidence": 0.85,
        "noise_field": "ignored by summary",
    }
    fake_client = mock.MagicMock(spec=GigatonClient)
    fake_client.get_pricing.return_value = fake_response

    result = get_pricing_signal(d, client=fake_client)

    assert result["status"] == "ok"
    assert result["engine_response"] == fake_response
    assert result["signal"] == {
        "nightly_rate": 180,
        "margin": 0.42,
        "recommendation": "hold",
        "confidence": 0.85,
    }
    fake_client.get_pricing.assert_called_once()


def test_signal_unavailable_on_http_error(monkeypatch):
    monkeypatch.setenv("DECISION_PRICING_BRIDGE_ENABLED", "1")
    d = _decision(requested_action="Adjust pricing")
    fake_client = mock.MagicMock(spec=GigatonClient)
    fake_client.get_pricing.side_effect = GigatonClientError(503, '{"err":"down"}')

    result = get_pricing_signal(d, client=fake_client)

    assert result["status"] == "unavailable"
    assert "503" in result["reason"]
    assert result["signal"] is None


def test_signal_unavailable_on_unexpected_exception(monkeypatch):
    monkeypatch.setenv("DECISION_PRICING_BRIDGE_ENABLED", "1")
    d = _decision(requested_action="Adjust pricing")
    fake_client = mock.MagicMock(spec=GigatonClient)
    fake_client.get_pricing.side_effect = RuntimeError("kaboom")

    result = get_pricing_signal(d, client=fake_client)

    assert result["status"] == "unavailable"
    assert "kaboom" in result["reason"]


def test_payload_carries_decision_metadata():
    d = _decision(
        decision_id="dec-abc",
        title="Pricing review",
        requested_action="Adjust nightly rates",
        evidence_refs=["properties/prop_123", "dates/2026-06-01_2026-06-07"],
    )
    payload = _build_pricing_payload(d)
    assert payload["source"] == "decision-engine"
    assert payload["decision_id"] == "dec-abc"
    assert payload["requested_action"] == "Adjust nightly rates"
    assert "properties/prop_123" in payload["evidence_refs"]


def test_payload_caps_evidence_refs_at_10():
    d = _decision(
        requested_action="Adjust pricing",
        evidence_refs=[f"ref-{i}" for i in range(50)],
    )
    payload = _build_pricing_payload(d)
    assert len(payload["evidence_refs"]) == 10


def test_signal_consulted_at_is_iso8601(monkeypatch):
    monkeypatch.setenv("DECISION_PRICING_BRIDGE_ENABLED", "1")
    d = _decision(requested_action="Send newsletter")  # skipped path
    result = get_pricing_signal(d)
    # Just check parseable
    from datetime import datetime
    datetime.fromisoformat(result["consulted_at"])
