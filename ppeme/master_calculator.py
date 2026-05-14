"""master_calculator — PPEME's Mtheory Simulation Layer (Framework 5.19).

WHAT: Computes the canonical 9-variable BFT state vector per participant.
Per Framework 5.19, this is the Simulation Layer of the 4-layer Mtheory
execution stack: State Model / Interaction Model / Transformation Engine /
**Simulation Layer (= Master Calculator)**.

WHY: BFT (Business Field Theory) requires a per-participant state vector
to compute interactions and emergent outcomes. The Master Calculator is
PPEME's canonical computation point. Every other engine reads BFT state
FROM the Master Calculator; nobody else computes it.

WHERE: This module owns the function `finalize_participant_state` which
is the EMIT POINT for the Penrose Scoreboard wire (metric #6,
super_additive_network_value).

WHEN: v0 scaffold (2026-05-14). The BFT computation itself is still
WIP — see `bft_package_integration_plan.md` for the 9-var math. This
file ships the wire + the contract so as the computation lands, every
finalization automatically emits to the scoreboard.

HOW: A singleton `MasterCalculator` instance owns a `PenroseBFTEmitter`
and a `ThreadPoolExecutor` (size 2). Every call to
`finalize_participant_state(...)` submits an emit job and returns the
state immediately — caller is NEVER blocked on Penrose availability.

CONTEXT: This is the "system + interaction → emergent outcome" doctrine
in code form. Every state mutation IS intelligence the scoreboard needs.

penrose_signal: weakens
penrose_dimension: network_value
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from .emitters.penrose_bft_emitter import (
    BFT_CANONICAL_KEYS,
    EmitResult,
    PenroseBFTEmitter,
)

logger = logging.getLogger(__name__)


class MasterCalculator:
    """PPEME's BFT Simulation Layer (Framework 5.19) — v0 scaffold.

    v0 responsibility: hold the canonical state finalization entry point
    so the Penrose wire is committed and tested NOW; the BFT computation
    fills in as `bft_package_integration_plan.md` lands.
    """

    def __init__(
        self,
        emitter: Optional[PenroseBFTEmitter] = None,
        max_emit_workers: int = 2,
    ) -> None:
        self._emitter = emitter or PenroseBFTEmitter()
        # Small pool — emit is light, but we never want to block.
        self._pool = ThreadPoolExecutor(
            max_workers=max_emit_workers,
            thread_name_prefix="ppeme-penrose-emit",
        )

    @property
    def emitter(self) -> PenroseBFTEmitter:
        return self._emitter

    def finalize_participant_state(
        self,
        participant_id: str,
        state_vector: dict,
        timestamp: Optional[str] = None,
    ) -> dict:
        """Finalize a participant's BFT state and fire scoreboard emit.

        Returns the finalized state dict (passthrough today; future
        versions may normalize / project before returning).

        Emission is fire-and-forget — never blocks the caller.
        """
        # Validate locally so callers get immediate feedback. The emitter
        # will validate again, but failing here keeps the error close to
        # the bug site.
        missing = set(BFT_CANONICAL_KEYS) - set(state_vector.keys())
        if missing:
            raise ValueError(
                f"state_vector missing canonical BFT keys: {sorted(missing)}"
            )

        ts = timestamp or datetime.now(tz=timezone.utc).isoformat()

        # Fire-and-forget emit. We deliberately do NOT await / .result().
        try:
            self._pool.submit(
                self._safe_emit, participant_id, state_vector, ts
            )
        except RuntimeError as exc:
            # Pool shutdown after app stop — degrade gracefully.
            logger.info(
                "master_calculator: emit pool unavailable (%s) — "
                "running inline as last resort", exc,
            )
            self._safe_emit(participant_id, state_vector, ts)

        return {
            "participant_id": participant_id,
            "state_vector": state_vector,
            "timestamp": ts,
        }

    def _safe_emit(
        self,
        participant_id: str,
        state_vector: dict,
        timestamp: str,
    ) -> Optional[EmitResult]:
        """Wrap emit so background-thread exceptions never escape."""
        try:
            return self._emitter.emit(
                participant_id=participant_id,
                state_vector=state_vector,
                timestamp=timestamp,
            )
        except Exception as exc:  # noqa: BLE001
            # Always-online priority: PPEME stays up if Penrose is sick.
            logger.warning(
                "master_calculator: background emit raised %s — "
                "swallowed (always-online priority)",
                type(exc).__name__,
            )
            return None

    def shutdown(self, wait: bool = False) -> None:
        """Tear down the emit pool. Called on FastAPI shutdown."""
        try:
            self._pool.shutdown(wait=wait)
        except Exception:  # noqa: BLE001
            pass


# ── module-level singleton ──────────────────────────────────────────────────
#
# Bootstrapped lazily on first access OR explicitly by api/main.py at startup.
# Lazy bootstrap means tests can import the module without triggering env reads.

_calculator_singleton: Optional[MasterCalculator] = None
_calculator_lock = threading.Lock()


def get_master_calculator() -> MasterCalculator:
    """Return the process-wide MasterCalculator, building one if needed.

    Env-config (consumed only on first build):
      - PENROSE_SCOREBOARD_URL    base URL of decision-engine; absent → dry_run
      - PENROSE_SCOREBOARD_TOKEN  optional bearer token
      - PENROSE_EMIT_DRY_RUN      "1" → disable emission entirely
    """
    global _calculator_singleton
    if _calculator_singleton is None:
        with _calculator_lock:
            if _calculator_singleton is None:
                _calculator_singleton = _build_from_env()
    return _calculator_singleton


def _build_from_env() -> MasterCalculator:
    url = os.environ.get("PENROSE_SCOREBOARD_URL")
    emitter = PenroseBFTEmitter(scoreboard_url=url)
    return MasterCalculator(emitter=emitter)


def reset_master_calculator_for_tests() -> None:
    """Test helper — clear the singleton so env changes take effect."""
    global _calculator_singleton
    with _calculator_lock:
        if _calculator_singleton is not None:
            _calculator_singleton.shutdown(wait=False)
        _calculator_singleton = None
