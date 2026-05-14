"""Tests for ppeme.master_calculator — Master Calculator + Penrose wire.

WHAT: Validate that `finalize_participant_state` fires emission
fire-and-forget and never blocks / never raises on emit failure.

WHY: Per Framework 5.19, every BFT state finalization is intelligence
the Penrose Scoreboard needs. The wire MUST be exercised by tests so
metric #6 emissions don't silently regress.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import Future
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ppeme.emitters.penrose_bft_emitter import (  # noqa: E402
    BFT_CANONICAL_KEYS,
    EmitResult,
    PenroseBFTEmitter,
)
from ppeme.master_calculator import (  # noqa: E402
    MasterCalculator,
    get_master_calculator,
    reset_master_calculator_for_tests,
)


def _valid_state() -> dict:
    return {k: 0.5 for k in BFT_CANONICAL_KEYS}


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_master_calculator_for_tests()
    yield
    reset_master_calculator_for_tests()


def test_finalize_returns_state_dict_synchronously():
    """Caller never blocks on emit."""
    emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine.example")
    calc = MasterCalculator(emitter=emitter)

    # Block the emitter's HTTP forever — finalize should STILL return.
    def slow_post(*args, **kwargs):
        time.sleep(60)
        raise RuntimeError("should not reach")

    with mock.patch("requests.post", side_effect=slow_post):
        start = time.time()
        result = calc.finalize_participant_state("user-X", _valid_state())
        elapsed = time.time() - start

    assert result["participant_id"] == "user-X"
    assert result["state_vector"] == _valid_state()
    assert "timestamp" in result
    # Finalize must return immediately even though emit is sleeping in
    # the background thread.
    assert elapsed < 1.0


def test_finalize_calls_emitter_with_canonical_vector():
    """The wire actually fires."""
    emitter = mock.MagicMock(spec=PenroseBFTEmitter)
    emitter.emit.return_value = EmitResult(status="emitted", attempts=1)
    calc = MasterCalculator(emitter=emitter)

    calc.finalize_participant_state("user-fire", _valid_state())
    # Drain pool to ensure background emit ran.
    calc.shutdown(wait=True)

    emitter.emit.assert_called_once()
    kwargs = emitter.emit.call_args.kwargs
    assert kwargs["participant_id"] == "user-fire"
    assert kwargs["state_vector"] == _valid_state()
    assert kwargs["timestamp"] is not None


def test_finalize_rejects_state_vector_missing_keys():
    """Bad state surfaces immediately to caller — bug stays close to source."""
    calc = MasterCalculator(emitter=PenroseBFTEmitter())
    bad = _valid_state()
    del bad["urgency"]
    with pytest.raises(ValueError, match="missing canonical BFT keys"):
        calc.finalize_participant_state("user-X", bad)


def test_finalize_swallows_background_emit_exception():
    """Always-online: emitter raise in background must not crash anything."""
    emitter = mock.MagicMock(spec=PenroseBFTEmitter)
    emitter.emit.side_effect = RuntimeError("scoreboard exploded")
    calc = MasterCalculator(emitter=emitter)

    # No raise:
    result = calc.finalize_participant_state("user-X", _valid_state())
    assert result["participant_id"] == "user-X"
    calc.shutdown(wait=True)  # exception was swallowed in worker thread


def test_get_master_calculator_returns_singleton(monkeypatch):
    monkeypatch.setenv(
        "PENROSE_SCOREBOARD_URL",
        "https://decision-engine.example",
    )
    a = get_master_calculator()
    b = get_master_calculator()
    assert a is b
    assert a.emitter._scoreboard_url == "https://decision-engine.example"


def test_get_master_calculator_dry_run_when_url_unset(monkeypatch):
    monkeypatch.delenv("PENROSE_SCOREBOARD_URL", raising=False)
    calc = get_master_calculator()
    # No URL → emitter reports "disabled" on emit.
    with mock.patch("requests.post") as m:
        result = calc.emitter.emit("user-X", _valid_state())
    assert result.status == "disabled"
    m.assert_not_called()
