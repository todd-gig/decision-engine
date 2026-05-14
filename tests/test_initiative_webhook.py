"""Initiative-webhook emission tests — infer_initiative_id + emit_inferred_transition.

Covers the agentic-loop closure: when the decision-engine pipeline
AUTO_EXECUTEs a decision tied to an initiative, this webhook advances
HME's 5-stage lifecycle (per HME Locked Decision #3). Tests verify the
emitter is robust to:
  - feature-flag OFF (EMIT_INFERRED_TRANSITION=0 → no emission)
  - matching decision (one POST, correct payload)
  - non-matching decision (no UUID → no POST)
  - 4xx / 5xx responses (logged, never raise, pipeline continues)
  - timeouts (URLError → logged, never raise)
  - 2xx successes (logged at info)
  - per-process idempotency (same decision/initiative/stage → suppressed)
"""
from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
from io import BytesIO
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.hme_event_emitter import (
    _reset_idempotency_cache,
    emit_inferred_transition,
    emit_initiative_webhook,  # backwards-compat alias — same function
    infer_initiative_id,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("DECISION_HME_DISABLE_OIDC", "1")
    monkeypatch.delenv("DECISION_HME_EMIT_DISABLED", raising=False)
    monkeypatch.delenv("EMIT_INFERRED_TRANSITION", raising=False)
    # Per-process idempotency cache must not leak across tests.
    _reset_idempotency_cache()
    yield
    _reset_idempotency_cache()


def _ok_response(status: int = 200) -> mock.MagicMock:
    m = mock.MagicMock()
    m.__enter__ = mock.MagicMock(return_value=m)
    m.__exit__ = mock.MagicMock(return_value=None)
    m.status = status
    m.read.return_value = b"{}"
    return m


# ── infer_initiative_id heuristic ─────────────────────────────────────────────


def test_infer_finds_uuid_after_initiative_keyword():
    text = "Advance initiative 12345678-1234-1234-1234-123456789012 to next stage"
    assert infer_initiative_id(text) == "12345678-1234-1234-1234-123456789012"


def test_infer_handles_various_separators():
    cases = [
        ("initiative-12345678-1234-1234-1234-123456789012", "12345678-1234-1234-1234-123456789012"),
        ("initiative_12345678-1234-1234-1234-123456789012", "12345678-1234-1234-1234-123456789012"),
        ("initiative:12345678-1234-1234-1234-123456789012", "12345678-1234-1234-1234-123456789012"),
        ("initiative/12345678-1234-1234-1234-123456789012", "12345678-1234-1234-1234-123456789012"),
    ]
    for text, expected in cases:
        assert infer_initiative_id(text) == expected, f"Failed: {text}"


def test_infer_searches_multiple_texts_in_order():
    """Returns the first match across the provided texts."""
    a = "no uuid here"
    b = "initiative aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa shipped"
    c = "initiative bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert infer_initiative_id(a, b, c) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_infer_returns_none_when_no_keyword():
    """A UUID without 'initiative' keyword nearby does NOT match."""
    text = "Update property 12345678-1234-1234-1234-123456789012 listing"
    assert infer_initiative_id(text) is None


def test_infer_returns_none_when_no_uuid():
    text = "Advance the initiative through its next stage"
    assert infer_initiative_id(text) is None


def test_infer_handles_none_inputs():
    assert infer_initiative_id(None, None, None) is None
    assert infer_initiative_id() is None


def test_infer_is_case_insensitive():
    text = "INITIATIVE 12345678-1234-1234-1234-123456789012"
    assert infer_initiative_id(text) == "12345678-1234-1234-1234-123456789012"


# ── emit_initiative_webhook ───────────────────────────────────────────────────


def test_webhook_posts_to_inferred_transition_path():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        ok = emit_initiative_webhook(
            initiative_id="11111111-1111-1111-1111-111111111111",
            decision_id="DEC-WHK",
            to_stage="IN_PROGRESS",
            reasoning="auto-execute did it",
        )
    assert ok is True
    assert captured["url"].endswith("/v1/webhooks/inferred-transition")
    body = captured["body"]
    assert body["initiative_id"] == "11111111-1111-1111-1111-111111111111"
    assert body["to_stage"] == "IN_PROGRESS"
    assert "[decision-engine DEC-WHK]" in body["reasoning"]
    assert body["source_engine"] == "decision-engine"


def test_webhook_carries_decision_certificate_id_when_provided():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_initiative_webhook(
            initiative_id="i", decision_id="d",
            decision_certificate_id="EC-CERT-123",
        )
    assert captured["body"]["decision_certificate_id"] == "EC-CERT-123"


def test_webhook_no_gateway_url_disables(monkeypatch):
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    monkeypatch.delenv("HME_EVENTS_URL", raising=False)
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_initiative_webhook(initiative_id="x", decision_id="y")
    assert ok is False
    m.assert_not_called()


def test_webhook_kill_switch_disables(monkeypatch):
    monkeypatch.setenv("DECISION_HME_EMIT_DISABLED", "1")
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_initiative_webhook(initiative_id="x", decision_id="y")
    assert ok is False
    m.assert_not_called()


def test_webhook_http_error_does_not_raise():
    err = urllib.error.HTTPError(
        "https://gateway.example/v1/webhooks/inferred-transition", 503, "down",
        hdrs=None, fp=BytesIO(b"{}")
    )
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_initiative_webhook(initiative_id="x", decision_id="y")
    assert ok is False


def test_webhook_network_error_does_not_raise():
    err = urllib.error.URLError("connection refused")
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_initiative_webhook(initiative_id="x", decision_id="y")
    assert ok is False


def test_webhook_unexpected_error_does_not_raise():
    with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        ok = emit_initiative_webhook(initiative_id="x", decision_id="y")
    assert ok is False


# ── EMIT_INFERRED_TRANSITION feature flag ─────────────────────────────────────


def test_webhook_feature_flag_off_suppresses_emission(monkeypatch):
    """EMIT_INFERRED_TRANSITION=0 disables ONLY this webhook (not gamification)."""
    monkeypatch.setenv("EMIT_INFERRED_TRANSITION", "0")
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_inferred_transition(initiative_id="x", decision_id="y")
    assert ok is False
    m.assert_not_called()


def test_webhook_feature_flag_on_emits(monkeypatch):
    """EMIT_INFERRED_TRANSITION=1 (default) allows emission."""
    monkeypatch.setenv("EMIT_INFERRED_TRANSITION", "1")
    with mock.patch("urllib.request.urlopen", return_value=_ok_response()):
        ok = emit_inferred_transition(initiative_id="x", decision_id="y")
    assert ok is True


def test_webhook_feature_flag_default_is_on():
    """Unset EMIT_INFERRED_TRANSITION → emission proceeds (default ON)."""
    # The autouse _env fixture already deletes this var; verify default.
    assert "EMIT_INFERRED_TRANSITION" not in os.environ
    with mock.patch("urllib.request.urlopen", return_value=_ok_response()):
        ok = emit_inferred_transition(
            initiative_id="11111111-1111-1111-1111-111111111111",
            decision_id="DEC-DEFAULT",
        )
    assert ok is True


# ── 4xx vs 5xx response handling ─────────────────────────────────────────────


def test_webhook_4xx_response_does_not_raise():
    """HTTP 404 / 409 / 422 from HME → log warning, return False, no raise."""
    err = urllib.error.HTTPError(
        "https://gateway.example/v1/webhooks/inferred-transition", 422, "bad payload",
        hdrs=None, fp=BytesIO(b'{"detail":"to_stage invalid"}')
    )
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_inferred_transition(initiative_id="x", decision_id="y")
    assert ok is False


def test_webhook_5xx_response_does_not_raise():
    """HTTP 502 / 503 / 504 from HME → log error, return False, no raise."""
    err = urllib.error.HTTPError(
        "https://gateway.example/v1/webhooks/inferred-transition", 502, "bad gateway",
        hdrs=None, fp=BytesIO(b"{}")
    )
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_inferred_transition(initiative_id="x", decision_id="y")
    assert ok is False


# ── Timeout handling ─────────────────────────────────────────────────────────


def test_webhook_timeout_does_not_raise():
    """Network timeout (URLError wrapping socket.timeout) → return False."""
    err = urllib.error.URLError(socket.timeout("timed out"))
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_inferred_transition(initiative_id="x", decision_id="y")
    assert ok is False


# ── Idempotency ──────────────────────────────────────────────────────────────


def test_webhook_idempotency_suppresses_duplicate_emit():
    """Re-running the same decision through the pipeline must NOT double-emit.

    Same (decision_id, initiative_id, to_stage) → first POST goes through,
    second is suppressed by the in-process cache.
    """
    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        ok1 = emit_inferred_transition(
            initiative_id="11111111-1111-1111-1111-111111111111",
            decision_id="DEC-DUP",
            to_stage="IN_PROGRESS",
        )
        ok2 = emit_inferred_transition(
            initiative_id="11111111-1111-1111-1111-111111111111",
            decision_id="DEC-DUP",
            to_stage="IN_PROGRESS",
        )

    assert ok1 is True
    assert ok2 is False  # Suppressed
    assert call_count["n"] == 1  # Only one network call


def test_webhook_idempotency_does_not_suppress_different_stage():
    """Same decision + initiative but different to_stage → both fire.

    Real-world example: AUTO_EXECUTE advances to IN_PROGRESS, then a
    subsequent completion advances to COMPLETED. Both are distinct
    transitions and should both reach HME.
    """
    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_inferred_transition(
            initiative_id="11111111-1111-1111-1111-111111111111",
            decision_id="DEC-PROGRESS",
            to_stage="IN_PROGRESS",
        )
        emit_inferred_transition(
            initiative_id="11111111-1111-1111-1111-111111111111",
            decision_id="DEC-PROGRESS",
            to_stage="COMPLETED",
        )
    assert call_count["n"] == 2


# ── Alias coverage ───────────────────────────────────────────────────────────


def test_emit_initiative_webhook_alias_routes_to_inferred_transition():
    """Legacy name `emit_initiative_webhook` is an alias of `emit_inferred_transition`."""
    assert emit_initiative_webhook is emit_inferred_transition
