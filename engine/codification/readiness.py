"""Codification readiness scorer — gates analyzer candidates into proposals.

Per `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` §5.7 (Adaptive Learning Loop)
and §5.8 (Decision Routing Framework). The analyzer produces candidates
purely from audit-log signal; the readiness scorer applies doctrine
thresholds and a composite formula to decide which candidates are mature
enough to enter the proposal queue.

Doctrine floors (apply as HARD GATES):
- ≥50 executions
- ≤5% exception rate
- ≥0.8 outcome stability

Composite score weights:
- volume        0.30
- exception_inv 0.30  (1 - exception_rate)
- stability     0.25
- value         0.10  (business value proxy 0-1)
- risk_inv      0.05  (1 - risk 0-1)

Thresholds live in `config/engine.yaml` under `codification.readiness`
so they're tunable without code change. Doctrine defaults are the
baked-in fallbacks.

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Mapping, Optional

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - pyyaml is a hard runtime dep
    yaml = None  # type: ignore[assignment]


# ── Doctrine defaults (single source of truth fallback) ────────────────────

DOCTRINE_DEFAULTS: dict[str, Any] = {
    "min_executions": 50,
    "max_exception_rate": 0.05,
    "min_stability": 0.80,
    "weights": {
        "volume": 0.30,
        "exception_inv": 0.30,
        "stability": 0.25,
        "value": 0.10,
        "risk_inv": 0.05,
    },
    "score_threshold": 0.70,
}


# ── Data structures ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReadinessThresholds:
    """Tunable thresholds. Defaults track doctrine verbatim."""
    min_executions: int = 50
    max_exception_rate: float = 0.05
    min_stability: float = 0.80
    weight_volume: float = 0.30
    weight_exception_inv: float = 0.30
    weight_stability: float = 0.25
    weight_value: float = 0.10
    weight_risk_inv: float = 0.05
    score_threshold: float = 0.70

    def weights_sum(self) -> float:
        return (
            self.weight_volume
            + self.weight_exception_inv
            + self.weight_stability
            + self.weight_value
            + self.weight_risk_inv
        )


@dataclass(frozen=True)
class ReadinessCandidate:
    """Shape the scorer accepts. Subset of fields needed for readiness."""
    candidate_pv: str
    candidate_sv: str
    executions: int
    exception_rate: float
    stability: float
    value: float = 0.5     # business value proxy, neutral when unknown
    risk: float = 0.5      # risk proxy, neutral when unknown


@dataclass
class ReadinessScore:
    """Result of scoring one candidate."""
    candidate_pv: str
    candidate_sv: str
    score: float
    is_ready: bool
    blockers: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Threshold loading ──────────────────────────────────────────────────────


def _load_yaml_section(yaml_path: Optional[str]) -> Mapping[str, Any]:
    """Read `codification.readiness` block from engine.yaml. Returns {} on miss."""
    if yaml is None:
        return {}
    if yaml_path is None:
        # Match engine.config.load_config layout: <repo>/config/engine.yaml
        here = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(os.path.dirname(here))
        candidate = os.path.join(repo_root, "config", "engine.yaml")
        if not os.path.exists(candidate):
            return {}
        yaml_path = candidate
    if not os.path.exists(yaml_path):
        return {}
    with open(yaml_path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    block = data.get("codification", {}).get("readiness", {})
    return block if isinstance(block, dict) else {}


def load_thresholds(yaml_path: Optional[str] = None) -> ReadinessThresholds:
    """Load tunable thresholds from engine.yaml; fall back to doctrine defaults."""
    cfg = _load_yaml_section(yaml_path)
    weights = cfg.get("weights", {}) or {}
    return ReadinessThresholds(
        min_executions=int(cfg.get("min_executions", DOCTRINE_DEFAULTS["min_executions"])),
        max_exception_rate=float(
            cfg.get("max_exception_rate", DOCTRINE_DEFAULTS["max_exception_rate"])
        ),
        min_stability=float(cfg.get("min_stability", DOCTRINE_DEFAULTS["min_stability"])),
        weight_volume=float(weights.get("volume", DOCTRINE_DEFAULTS["weights"]["volume"])),
        weight_exception_inv=float(
            weights.get("exception_inv", DOCTRINE_DEFAULTS["weights"]["exception_inv"])
        ),
        weight_stability=float(
            weights.get("stability", DOCTRINE_DEFAULTS["weights"]["stability"])
        ),
        weight_value=float(weights.get("value", DOCTRINE_DEFAULTS["weights"]["value"])),
        weight_risk_inv=float(
            weights.get("risk_inv", DOCTRINE_DEFAULTS["weights"]["risk_inv"])
        ),
        score_threshold=float(
            cfg.get("score_threshold", DOCTRINE_DEFAULTS["score_threshold"])
        ),
    )


# ── Component normalizers ──────────────────────────────────────────────────


def _normalize_volume(executions: int, min_executions: int) -> float:
    """Log-scaled normalization. 0 at executions=0, ~0.5 at executions=10×floor,
    saturates to 1.0 by executions=100×floor.

    Floor is `min_executions` (the doctrine hard gate). The score climbs
    smoothly above the floor; a candidate that just barely meets the floor
    gets ~0.30 volume credit.
    """
    if executions <= 0 or min_executions <= 0:
        return 0.0
    ratio = executions / float(min_executions)
    if ratio <= 0:
        return 0.0
    # log10(ratio+1) -> 0.30 at ratio=1, 1.04 at ratio=10. Clamp to 1.0.
    raw = math.log10(ratio + 1.0)
    return max(0.0, min(1.0, raw))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# ── Scorer ─────────────────────────────────────────────────────────────────


def compute_readiness(
    candidate: ReadinessCandidate,
    thresholds: Optional[ReadinessThresholds] = None,
) -> ReadinessScore:
    """Score one candidate against doctrine thresholds + composite formula.

    Hard gates (any failure → is_ready=False, blocker recorded, but the
    composite score is still returned so operators can see how close
    a candidate is to ready).
    """
    th = thresholds or load_thresholds()
    blockers: list[str] = []

    # Hard gates per doctrine §5.7
    if candidate.executions < th.min_executions:
        blockers.append(
            f"executions={candidate.executions} below floor {th.min_executions}"
        )
    if candidate.exception_rate > th.max_exception_rate:
        blockers.append(
            f"exception_rate={candidate.exception_rate:.4f} above ceiling "
            f"{th.max_exception_rate:.4f}"
        )
    if candidate.stability < th.min_stability:
        blockers.append(
            f"stability={candidate.stability:.4f} below floor {th.min_stability:.4f}"
        )

    # Components — each in [0, 1].
    volume_norm = _normalize_volume(candidate.executions, th.min_executions)
    exception_inv = _clamp01(1.0 - candidate.exception_rate)
    stability = _clamp01(candidate.stability)
    value = _clamp01(candidate.value)
    risk_inv = _clamp01(1.0 - candidate.risk)

    score = (
        th.weight_volume * volume_norm
        + th.weight_exception_inv * exception_inv
        + th.weight_stability * stability
        + th.weight_value * value
        + th.weight_risk_inv * risk_inv
    )
    # Normalize if weights don't sum to exactly 1.0 (operator tuning).
    weight_total = th.weights_sum()
    if weight_total > 0 and weight_total != 1.0:
        score = score / weight_total
    score = _clamp01(score)

    is_ready = not blockers and score >= th.score_threshold

    return ReadinessScore(
        candidate_pv=candidate.candidate_pv,
        candidate_sv=candidate.candidate_sv,
        score=round(score, 6),
        is_ready=is_ready,
        blockers=blockers,
        components={
            "volume_norm": round(volume_norm, 6),
            "exception_inv": round(exception_inv, 6),
            "stability": round(stability, 6),
            "value": round(value, 6),
            "risk_inv": round(risk_inv, 6),
        },
    )


__all__ = [
    "ReadinessThresholds",
    "ReadinessCandidate",
    "ReadinessScore",
    "DOCTRINE_DEFAULTS",
    "load_thresholds",
    "compute_readiness",
]
