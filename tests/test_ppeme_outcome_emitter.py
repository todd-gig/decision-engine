"""ppeme_outcome_emitter — emit observed outcomes to PPEME /v1/outcomes/record.

Mirrors test_initiative_webhook style: mocked urllib.request, env-driven
configuration. No real network calls.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from io import BytesIO
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ppeme_outcome_emitter import emit_observed_outcome


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PPEME_URL", "https://ppeme.example")
    monkeypatch.setenv("DECISION_PPEME_DISABLE_OIDC", "1")
    monkeypatch.delenv("DECISION_PPEME_EMIT_DISABLED", raising=False)


def _ok_response(status: int = 202) -> mock.MagicMock:
    m = mock.MagicMock()
    m.__enter__ = mock.MagicMock(return_value=m)
    m.__exit__ = mock.MagicMock(return_value=None)
    m.status = status
    m.read.return_value = b"{}"
    return m


def test_emit_minimal_posts_to_outcomes_record():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        ok = emit_observed_outcome(
            decision_id="DEC-1234",
            subject_kind="user",
            subject_id="11111111-1111-1111-1111-111111111111",
            outcome_metric="revenue_usd_30d",
            outcome_value=280.0,
            outcome_unit="usd",
        )
    assert ok is True
    assert captured["url"].endswith("/v1/outcomes/record")
    body = captured["body"]
    assert body["decision_id"] == "DEC-1234"
    assert body["outcome_value"] == 280.0
    assert body["outcome_metric"] == "revenue_usd_30d"
    assert body["outcome_unit"] == "usd"
    assert body["subject_kind"] == "user"
    assert body["source_engine"] == "decision-engine"
    # observed_at auto-stamped when not provided
    assert "observed_at" in body


def test_emit_with_prediction_metadata_populates_payload():
    """When predicted_p50 + estimator_version + decision_class are present,
    metadata_payload is populated so recompute_calibration can group."""
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_observed_outcome(
            decision_id="DEC-PRED",
            subject_kind="org",
            outcome_metric="conversion",
            outcome_value=1.0,
            outcome_unit="boolean",
            predicted_p50=0.65,
            estimator_version="v0-rules-from-events",
            decision_class="D3",
        )
    meta = captured["body"]["metadata_payload"]
    assert meta["predicted_p50"] == 0.65
    assert meta["estimator_version"] == "v0-rules-from-events"
    assert meta["decision_class"] == "D3"


def test_emit_with_extra_metadata_preserves_keys():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_observed_outcome(
            decision_id="DEC-META",
            subject_kind="user",
            outcome_metric="rev",
            outcome_value=1.0,
            outcome_unit="usd",
            extra_metadata={"opportunity_id": "opp-1", "stage": "closed_won"},
            predicted_p50=0.5,
            estimator_version="v0",
            decision_class="D2",
        )
    meta = captured["body"]["metadata_payload"]
    assert meta["opportunity_id"] == "opp-1"
    assert meta["stage"] == "closed_won"
    assert meta["predicted_p50"] == 0.5


def test_emit_invalid_subject_kind_returns_false():
    """Bad subject_kind short-circuits before network call."""
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_observed_outcome(
            decision_id="DEC-X",
            subject_kind="spaceship",
            outcome_metric="rev",
            outcome_value=1.0,
            outcome_unit="usd",
        )
    assert ok is False
    m.assert_not_called()


def test_emit_no_ppeme_url_disables(monkeypatch):
    monkeypatch.delenv("PPEME_URL", raising=False)
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_observed_outcome(
            decision_id="DEC-X",
            subject_kind="user",
            outcome_metric="rev",
            outcome_value=1.0,
            outcome_unit="usd",
        )
    assert ok is False
    m.assert_not_called()


def test_emit_kill_switch_disables(monkeypatch):
    monkeypatch.setenv("DECISION_PPEME_EMIT_DISABLED", "1")
    with mock.patch("urllib.request.urlopen") as m:
        ok = emit_observed_outcome(
            decision_id="DEC-X",
            subject_kind="user",
            outcome_metric="rev",
            outcome_value=1.0,
            outcome_unit="usd",
        )
    assert ok is False
    m.assert_not_called()


def test_emit_falls_back_to_gateway_url(monkeypatch):
    """When PPEME_URL is missing but GATEWAY_URL is set, route via gateway."""
    monkeypatch.delenv("PPEME_URL", raising=False)
    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example")
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_observed_outcome(
            decision_id="DEC-G",
            subject_kind="user",
            outcome_metric="rev",
            outcome_value=1.0,
            outcome_unit="usd",
        )
    # Gateway-routed path: /v1/ppeme/v1/outcomes/record
    assert "/v1/ppeme/v1/outcomes/record" in captured["url"]


def test_emit_http_error_returns_false():
    err = urllib.error.HTTPError(
        "https://ppeme.example/v1/outcomes/record", 503, "down",
        hdrs=None, fp=BytesIO(b"{}"),
    )
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_observed_outcome(
            decision_id="DEC-X", subject_kind="user",
            outcome_metric="rev", outcome_value=1.0, outcome_unit="usd",
        )
    assert ok is False


def test_emit_network_error_returns_false():
    err = urllib.error.URLError("connection refused")
    with mock.patch("urllib.request.urlopen", side_effect=err):
        ok = emit_observed_outcome(
            decision_id="DEC-X", subject_kind="user",
            outcome_metric="rev", outcome_value=1.0, outcome_unit="usd",
        )
    assert ok is False


def test_emit_unexpected_error_returns_false():
    with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        ok = emit_observed_outcome(
            decision_id="DEC-X", subject_kind="user",
            outcome_metric="rev", outcome_value=1.0, outcome_unit="usd",
        )
    assert ok is False


def test_emit_carries_observation_window():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return _ok_response()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        emit_observed_outcome(
            decision_id="DEC-WIN",
            subject_kind="org",
            outcome_metric="ltv",
            outcome_value=12000.0,
            outcome_unit="usd",
            observation_window_start="2026-04-14T00:00:00Z",
            observation_window_end="2026-05-14T00:00:00Z",
        )
    body = captured["body"]
    assert body["observation_window_start"] == "2026-04-14T00:00:00Z"
    assert body["observation_window_end"] == "2026-05-14T00:00:00Z"
