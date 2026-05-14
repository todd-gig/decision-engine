"""Tests for ppeme.emitters.penrose_bft_emitter.

WHAT: Validate the PPEME→Penrose Scoreboard BFT state emitter end-to-end:
  - successful emission on 200
  - dry-run modes (URL unset + DRY_RUN env)
  - local validation rejecting non-canonical / out-of-range vectors
  - retry-with-backoff behavior + final failed status
  - ISO-8601 timestamp default
  - never-raises on HTTP error (always-online priority)

WHY: The emitter is the missing wire for Penrose metric #6
(super_additive_network_value). It MUST validate locally and MUST NOT
take PPEME down when the scoreboard is sick.

HOW: All HTTP is mocked via `unittest.mock.patch("requests.post", ...)`.
No real network calls.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from unittest import mock

import pytest

# Repo root on sys.path so `ppeme` import resolves like in prod.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ppeme.emitters.penrose_bft_emitter import (  # noqa: E402
    BFT_CANONICAL_KEYS,
    EmitResult,
    PenroseBFTEmitter,
)


# ── helpers ─────────────────────────────────────────────────────────────────


def _valid_state() -> dict:
    """Return a canonical 9-var state vector with all values in [0,1]."""
    return {k: 0.5 for k in BFT_CANONICAL_KEYS}


def _mock_response(status: int = 202, body: dict | None = None) -> mock.MagicMock:
    m = mock.MagicMock()
    m.status_code = status
    m.json.return_value = body if body is not None else {"id": "NVO-ABC123"}
    return m


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip env vars that influence emitter behavior before every test."""
    for key in (
        "PENROSE_EMIT_DRY_RUN",
        "PENROSE_SCOREBOARD_URL",
        "PENROSE_SCOREBOARD_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


# ── happy path ──────────────────────────────────────────────────────────────


def test_emit_success_returns_emitted_on_200():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = json.loads(data)
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _mock_response(202, {"id": "NVO-OK"})

    with mock.patch("requests.post", side_effect=fake_post):
        result = emitter.emit("user-42", _valid_state())

    assert isinstance(result, EmitResult)
    assert result.status == "emitted"
    assert result.scoreboard_response == {"id": "NVO-OK"}
    assert result.attempts == 1
    assert captured["url"].endswith("/v1/penrose/network-value/record")
    assert captured["body"]["participant_id"] == "user-42"
    assert captured["body"]["source"] == "ppeme"
    assert captured["body"]["state_vector"] == _valid_state()
    assert captured["headers"]["Content-Type"] == "application/json"
    # No auth token env set → no Authorization header.
    assert "Authorization" not in captured["headers"]
    assert captured["timeout"] == 5


def test_emit_with_bearer_token_attaches_authorization_header(monkeypatch):
    monkeypatch.setenv("PENROSE_SCOREBOARD_TOKEN", "sekret-123")
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _mock_response(202)

    with mock.patch("requests.post", side_effect=fake_post):
        emitter.emit("user-X", _valid_state())

    assert captured["headers"]["Authorization"] == "Bearer sekret-123"


def test_emit_timestamp_defaults_to_iso8601_utc_when_not_provided():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["body"] = json.loads(data)
        return _mock_response(202)

    with mock.patch("requests.post", side_effect=fake_post):
        emitter.emit("user-X", _valid_state())

    ts = captured["body"]["timestamp"]
    # Parse to confirm ISO-8601 + UTC.
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    # Should be very recent.
    assert (datetime.now(tz=timezone.utc) - parsed).total_seconds() < 30


def test_emit_preserves_explicit_timestamp():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["body"] = json.loads(data)
        return _mock_response(202)

    with mock.patch("requests.post", side_effect=fake_post):
        emitter.emit(
            "user-X", _valid_state(),
            timestamp="2026-05-14T12:00:00+00:00",
        )

    assert captured["body"]["timestamp"] == "2026-05-14T12:00:00+00:00"


# ── dry-run / disabled paths ────────────────────────────────────────────────


def test_emit_with_no_url_returns_disabled_without_http():
    emitter = PenroseBFTEmitter(scoreboard_url=None)
    with mock.patch("requests.post") as m:
        result = emitter.emit("user-X", _valid_state())
    assert result.status == "disabled"
    assert result.attempts == 0
    m.assert_not_called()


def test_emit_with_empty_url_string_returns_disabled():
    emitter = PenroseBFTEmitter(scoreboard_url="")
    with mock.patch("requests.post") as m:
        result = emitter.emit("user-X", _valid_state())
    assert result.status == "disabled"
    m.assert_not_called()


def test_emit_dry_run_env_short_circuits_before_http(monkeypatch):
    monkeypatch.setenv("PENROSE_EMIT_DRY_RUN", "1")
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    with mock.patch("requests.post") as m:
        result = emitter.emit("user-X", _valid_state())
    assert result.status == "dry_run"
    assert result.payload is not None
    assert result.payload["participant_id"] == "user-X"
    m.assert_not_called()


# ── local validation ────────────────────────────────────────────────────────


def test_emit_rejects_state_vector_missing_required_key():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    bad = _valid_state()
    del bad["trust"]
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="missing"):
            emitter.emit("user-X", bad)
    m.assert_not_called()


def test_emit_rejects_state_vector_with_extra_key():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    bad = _valid_state()
    bad["bogus_dimension"] = 0.5
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="extra"):
            emitter.emit("user-X", bad)
    m.assert_not_called()


def test_emit_rejects_state_vector_with_value_above_one():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    bad = _valid_state()
    bad["trust"] = 1.5
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="out of range"):
            emitter.emit("user-X", bad)
    m.assert_not_called()


def test_emit_rejects_state_vector_with_negative_value():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    bad = _valid_state()
    bad["attention"] = -0.01
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="out of range"):
            emitter.emit("user-X", bad)
    m.assert_not_called()


def test_emit_rejects_state_vector_with_non_numeric_value():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    bad = _valid_state()
    bad["trust"] = "high"  # type: ignore
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="must be numeric"):
            emitter.emit("user-X", bad)
    m.assert_not_called()


def test_emit_rejects_boolean_value_in_state_vector():
    """bool is a subtype of int in Python — explicit reject."""
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    bad = _valid_state()
    bad["trust"] = True  # type: ignore
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="must be numeric"):
            emitter.emit("user-X", bad)
    m.assert_not_called()


def test_emit_rejects_empty_participant_id():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="participant_id"):
            emitter.emit("", _valid_state())
    m.assert_not_called()


def test_emit_rejects_non_string_participant_id():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    with mock.patch("requests.post") as m:
        with pytest.raises(ValueError, match="participant_id"):
            emitter.emit(12345, _valid_state())  # type: ignore
    m.assert_not_called()


def test_emit_accepts_boundary_values_0_and_1():
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    vec = {k: 0.0 for k in BFT_CANONICAL_KEYS}
    vec["trust"] = 1.0  # one at upper bound
    with mock.patch("requests.post", return_value=_mock_response(202)):
        result = emitter.emit("user-X", vec)
    assert result.status == "emitted"


# ── retry + always-online behavior ──────────────────────────────────────────


def test_emit_retries_three_times_on_connection_error_then_returns_failed():
    emitter = PenroseBFTEmitter(
        scoreboard_url="https://decision-engine.example",
        backoff_seconds=0.0,  # speed up test
    )

    # Build a connection-error-like exception.
    class FakeConnError(Exception):
        pass

    call_count = {"n": 0}

    def fake_post(*args, **kwargs):
        call_count["n"] += 1
        raise FakeConnError("connection refused")

    with mock.patch("requests.post", side_effect=fake_post):
        result = emitter.emit("user-X", _valid_state())

    assert result.status == "failed"
    assert result.attempts == 3
    assert call_count["n"] == 3
    assert result.error == "FakeConnError"


def test_emit_retries_on_http_5xx_and_succeeds_on_recovery():
    emitter = PenroseBFTEmitter(
        scoreboard_url="https://decision-engine.example",
        backoff_seconds=0.0,
    )
    responses = [
        _mock_response(503, {}),
        _mock_response(503, {}),
        _mock_response(202, {"id": "NVO-FINAL"}),
    ]

    with mock.patch("requests.post", side_effect=responses):
        result = emitter.emit("user-X", _valid_state())

    assert result.status == "emitted"
    assert result.attempts == 3
    assert result.scoreboard_response == {"id": "NVO-FINAL"}


def test_emit_never_raises_on_http_error():
    """Always-online priority: PPEME stays up if scoreboard is down."""
    emitter = PenroseBFTEmitter(
        scoreboard_url="https://decision-engine.example",
        backoff_seconds=0.0,
    )

    with mock.patch("requests.post", side_effect=RuntimeError("boom")):
        # Should NOT raise.
        result = emitter.emit("user-X", _valid_state())

    assert result.status == "failed"
    assert result.attempts == 3


def test_emit_audit_log_records_failure_reason(caplog):
    emitter = PenroseBFTEmitter(
        scoreboard_url="https://decision-engine.example",
        backoff_seconds=0.0,
    )

    with caplog.at_level("WARNING", logger="ppeme.emitters.penrose_bft_emitter"):
        with mock.patch("requests.post", side_effect=ConnectionError("nope")):
            emitter.emit("user-audit", _valid_state())

    # One of the WARNING records should be the audit failure marker.
    audit_records = [
        r for r in caplog.records
        if "penrose_emit_failed" in r.getMessage()
    ]
    assert len(audit_records) == 1
    assert "user-audit" in audit_records[0].getMessage()


def test_emit_handles_missing_requests_package(monkeypatch):
    """When `requests` isn't installed, emit returns failed without raising."""
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")

    # Simulate ImportError by stashing requests out of sys.modules and
    # injecting an import hook.
    real_requests = sys.modules.pop("requests", None)
    monkeypatch.setitem(sys.modules, "requests", None)
    try:
        result = emitter.emit("user-X", _valid_state())
    finally:
        # Restore so subsequent tests get real requests back.
        if real_requests is not None:
            sys.modules["requests"] = real_requests
        else:
            sys.modules.pop("requests", None)

    assert result.status == "failed"
    assert result.error == "requests_not_installed"


# ── backoff is invoked but not asserted on wall-clock (kept fast) ───────────


def test_emit_uses_backoff_between_retries():
    emitter = PenroseBFTEmitter(
        scoreboard_url="https://decision-engine.example",
        backoff_seconds=0.0,  # 0 to keep test instant
    )

    sleep_calls = []

    def fake_sleep(s):
        sleep_calls.append(s)

    with mock.patch(
        "ppeme.emitters.penrose_bft_emitter.time.sleep",
        side_effect=fake_sleep,
    ):
        with mock.patch("requests.post", side_effect=ConnectionError("nope")):
            emitter.emit("user-X", _valid_state())

    # Should sleep BETWEEN attempts: 2 sleeps for 3 attempts.
    assert len(sleep_calls) == 2


def test_emit_url_trailing_slash_is_stripped():
    """Avoid double-slash in the path."""
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example/")
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        return _mock_response(202)

    with mock.patch("requests.post", side_effect=fake_post):
        emitter.emit("user-X", _valid_state())

    assert captured["url"] == (
        "https://decision-engine.example/v1/penrose/network-value/record"
    )
