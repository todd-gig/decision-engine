"""ppeme — Predictably Profitable Experience Management Engine.

WHAT: Sub-package hosting PPEME-side code that lives in the decision-engine
repo today (pre-extraction). The Master Calculator + BFT emitter live here
until PPEME is extracted into its own repo per
`predictably_profitable_experience_management_engine.md`.

WHY: Per Framework 5.19 (Business Field Theory) PPEME is the canonical
owner of the 9-variable BFT state vector. Emitting BFT state to the Penrose
Falsification Scoreboard (metric #6, super_additive_network_value) requires
a PPEME-owned emitter. Co-locating it here today closes the loop now;
extraction to its own repo can happen later without breaking the wire.

WHERE: `ppeme/emitters/` for outbound emission; `ppeme/master_calculator.py`
for the BFT state computation scaffold (v0 placeholder — fills in as
Master Calculator lands).

WHEN: 2026-05-14 — wires metric #6 inbox that has been awaiting an emitter
since penrose-v0.6.

HOW: Emitter validates the canonical 9-var state vector locally (CRIT-010)
BEFORE POST so no 422-bound payloads ever leave the process; HTTP failure
never raises (always-online priority); fire-and-forget via a thread pool
so emit never blocks the request.

CONTEXT: Closes the "Doctrine-claim ≠ committed code" gap on metric #6 —
network-value-per-added-participant cannot graduate from stub until rows
exist; this emitter is what fills the table.

penrose_signal: weakens
penrose_dimension: network_value
"""
from __future__ import annotations

from .emitters.penrose_bft_emitter import (
    PenroseBFTEmitter,
    EmitResult,
    BFT_CANONICAL_KEYS,
)

__all__ = [
    "PenroseBFTEmitter",
    "EmitResult",
    "BFT_CANONICAL_KEYS",
]
