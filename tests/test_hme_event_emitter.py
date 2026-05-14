"""HME event emitter — verdict mapping + fire-and-forget HTTP."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from io import BytesIO
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.hme_event_emitter import emit_decision_event


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("DECISION_HME_DISABLE_OIDC", "1")
    monkeypatch.delenv("DECISION_HME_EMIT_DISABLED", raising=False)


def _ok_response(status: int = 200) -> mock.MagicMock:
    m = mock.MagicMock()
    m.__enter__ = mock.MagicMock(return_value=m)
    m.__exit__ = mock.MagicMock(return_value=None)
    m.status = status
    m.read.return_value = b'{"event_id":"xx","accepted":true}'
    return m


# ── Verdict → event mapping ───────────────────────────────────────────────────


def test_auto_execute_emits_initiative_advanced():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        ok = emit_decision_event(
            decision_id="DEC-1",
            verdict="AUTO_EXECUTE",
            user_id="11111111-1111-1111-1111-111111111111",
            decision_class="D1",
            requested_action="Run nightly inventory check",
        )
    assert ok is True
    assert captured["body"]["event_type"] == "InitiativeAdvanced"
    assert captured["body"]["source_engine"] == "decision-engine"
    assert captured["body"]["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert captured["body"]["event_payload"]["decision_id"] == "DEC-1"
    assert captured["body"]["event_payload"]["decision_class"] == "D1"


def test_escalate_tier_emits_initiative_progressed():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_decision_event(decision_id="DEC-2", verdict="ESCALATE_TIER_1")
    assert captured["body"]["event_type"] == "InitiativeProgressed"


def test_block_emits_nothing():
    """BLOCK verdicts get NO event — only positive forward motion fires gamification."""
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_decision_event(decision_id="DEC-3", verdict="BLOCK")
    assert ok is False
    m.assert_not_called()


def test_needs_data_emits_nothing():
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_decision_event(decision_id="DEC-4", verdict="NEEDS_DATA")
    assert ok is False
    m.assert_not_called()


def test_unknown_verdict_emits_nothing():
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_decision_event(decision_id="DEC-5", verdict="UNKNOWN_VERDICT")
    assert ok is False
    m.assert_not_called()


# ── No-op cases (env-gated) ───────────────────────────────────────────────────


def test_no_gateway_url_disables_emission(monkeypatch):
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    monkeypatch.delenv("HME_EVENTS_URL", raising=False)
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_decision_event(decision_id="DEC-X", verdict="AUTO_EXECUTE")
    assert ok is False
    m.assert_not_called()


def test_kill_switch_disables_emission(monkeypatch):
    monkeypatch.setenv("DECISION_HME_EMIT_DISABLED", "1")
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_decision_event(decision_id="DEC-X", verdict="AUTO_EXECUTE")
    assert ok is False
    m.assert_not_called()


# ── Error handling — never raise ──────────────────────────────────────────────


def test_http_error_does_not_raise():
    err = urllib.error.HTTPError(
        "https://gateway.example/v1/events", 503, "down",
        hdrs=None, fp=BytesIO(b"{}")
    )
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_decision_event(decision_id="DEC-Y", verdict="AUTO_EXECUTE")
    assert ok is False  # silent failure


def test_network_error_does_not_raise():
    err = urllib.error.URLError("connection refused")
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_decision_event(decision_id="DEC-Y", verdict="AUTO_EXECUTE")
    assert ok is False


def test_unexpected_exception_does_not_raise():
    with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        ok = emit_decision_event(decision_id="DEC-Y", verdict="AUTO_EXECUTE")
    assert ok is False


# ── Payload shape ─────────────────────────────────────────────────────────────


def test_no_user_id_falls_back_to_zero_uuid():
    captured = {}
    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()
    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_decision_event(decision_id="DEC-Z", verdict="AUTO_EXECUTE")
    assert captured["body"]["user_id"] == "00000000-0000-0000-0000-000000000000"


def test_org_id_included_when_provided():
    captured = {}
    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()
    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_decision_event(
            decision_id="DEC-Z", verdict="AUTO_EXECUTE",
            org_id="22222222-2222-2222-2222-222222222222",
        )
    assert captured["body"]["org_id"] == "22222222-2222-2222-2222-222222222222"


def test_requested_action_truncated_to_300_chars():
    captured = {}
    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()
    big_action = "x" * 500
    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_decision_event(
            decision_id="DEC-Z", verdict="AUTO_EXECUTE",
            requested_action=big_action,
        )
    assert len(captured["body"]["event_payload"]["requested_action"]) == 300
