"""ppeme.emitters — outbound emitters from PPEME to peer engines.

WHAT: Package of fire-and-forget HTTP emitters that publish PPEME state /
outcomes to other engines in the Gigaton ecosystem.

WHY: PPEME computes the canonical 9-variable BFT state per participant
(Framework 5.19). Peer engines (Penrose Falsification Scoreboard,
OVS-Calibration, HME) consume that state to compute their own metrics.

CONTEXT: Always-online priority — every emitter here MUST validate locally,
retry on transient failure, and never raise so PPEME stays up if peers go
down.

penrose_signal: weakens
penrose_dimension: network_value
"""
from __future__ import annotations

from .penrose_bft_emitter import (
    PenroseBFTEmitter,
    EmitResult,
    BFT_CANONICAL_KEYS,
)

__all__ = [
    "PenroseBFTEmitter",
    "EmitResult",
    "BFT_CANONICAL_KEYS",
]
