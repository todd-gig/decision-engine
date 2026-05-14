"""Initiative-webhook emission tests — infer_initiative_id + emit_initiative_webhook."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from io import BytesIO
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.hme_event_emitter import (
    emit_initiative_webhook,
    infer_initiative_id,
)


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
