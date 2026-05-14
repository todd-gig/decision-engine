"""Counterfactual scoring — observable rejected-alternative outcomes.

Per outcome_calibration_engine_spec.md §Counterfactual handling (lines 81-89)
and the spec's CounterfactualRecord schema (line 50):

  id, rejectedDecisionId, alternativeChosenId (nullable),
  observedAlternativeOutcomeIds[], inferredCounterfactualScore, confidence,
  schemaVersion

Three observability kinds (the ONLY conditions under which a counterfactual
may be scored — doctrine: evidence over assumption, Non-Negotiable #6):

  1. **direct**       — the decision was rejected, an *alternative was chosen*,
                        and the alternative's outcome is in our outcome stream.
                        We can read the alternative's actual outcome directly,
                        compare against the rejected decision's projection, and
                        score "would the rejected decision have done better?"
  2. **comparative**  — the same decision pattern was applied differently at
                        different entities (e.g., aggressive pricing at Carmen
                        Beach, conservative pricing at Ti Solutions) where
                        BOTH outcomes are observable. The not-chosen variant
                        is the counterfactual.
  3. **temporal**     — the same decision was applied before vs. after a known
                        regime change (e.g., before-event vs. after-event). The
                        pre/post outcomes are both observable.

Where NONE of these apply, this module returns `None` — never synthesizes a
speculative counterfactual. Speculative counterfactuals would feed assumption
into calibration, violating Non-Negotiable #6 and corrupting the calibration
vector with no audit anchor.

HMAC + audit envelope on every persisted row (same key source as the cert chain
and the CalibrationRevision twin — `CERT_SECRET_KEY` first, then
`OVS_CALIBRATION_HMAC_KEY` fallback to dev default).

penrose_signal: weakens
penrose_dimension: variance
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from . import storage


# ─────────────────────────────────────────────
# HMAC key — same source as revisions
# ─────────────────────────────────────────────

_DEFAULT_DEV_KEY = "dev-only-ovs-calibration-key-do-not-use-in-prod"


def _hmac_key() -> bytes:
    return os.environ.get(
        "CERT_SECRET_KEY",
        os.environ.get("OVS_CALIBRATION_HMAC_KEY", _DEFAULT_DEV_KEY),
    ).encode("utf-8")


# ─────────────────────────────────────────────
# Validation constants
# ─────────────────────────────────────────────

_VALID_KINDS = {"direct", "comparative", "temporal"}
_MIN_REASONING_CHARS = 20


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────


@dataclass
class CounterfactualScore:
    """Computed score returned to the caller.

    `inferred_counterfactual_score` is signed:
      + means the rejected decision *would have* outperformed the chosen one
        (i.e., rejecting was a mistake — strongest signal for re-evaluation)
      - means the rejected decision would have underperformed (rejection was
        correct — confirmation signal)
      0 means insufficient differentiation observed
    """
    rejected_decision_id: str
    kind: str  # direct | comparative | temporal
    observed_alternative_outcome_ids: list[str]
    inferred_counterfactual_score: float
    confidence: float
    reasoning: str
    alternative_chosen_id: Optional[str] = None
    evidence_metadata: dict = field(default_factory=dict)


@dataclass
class CounterfactualRecord:
    """Persisted counterfactual row.

    Mirrors the spec line 51 schema plus required reasoning + HMAC envelope.
    """
    rejected_decision_id: str
    kind: str  # direct | comparative | temporal
    observed_alternative_outcome_ids: list[str]
    inferred_counterfactual_score: float
    confidence: float
    reasoning: str
    alternative_chosen_id: Optional[str] = None
    evidence_metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"cf-{uuid.uuid4().hex[:12]}")
    hmac: str = ""
    scored_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    scored_by: str = "system"
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(_VALID_KINDS)}; got {self.kind!r}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0,1]; got {self.confidence}"
            )
        if not self.rejected_decision_id:
            raise ValueError("rejected_decision_id is required")
        if not self.reasoning or len(self.reasoning.strip()) < _MIN_REASONING_CHARS:
            raise ValueError(
                f"reasoning is required and must be >= {_MIN_REASONING_CHARS} "
                f"characters (always-record-WHY); got "
                f"{len(self.reasoning.strip()) if self.reasoning else 0}"
            )
        if not self.observed_alternative_outcome_ids:
            # Without observable alternative outcomes, this can't be a real
            # counterfactual — speculative counterfactual guard.
            raise ValueError(
                "observed_alternative_outcome_ids must be non-empty "
                "(speculative counterfactuals are forbidden per Non-Negotiable #6)"
            )

    # HMAC envelope — identical pattern to CalibrationRevision

    def signable_payload(self) -> str:
        payload = {
            "id": self.id,
            "rejected_decision_id": self.rejected_decision_id,
            "alternative_chosen_id": self.alternative_chosen_id or "",
            "observed_alternative_outcome_ids": sorted(
                self.observed_alternative_outcome_ids
            ),
            "kind": self.kind,
            "inferred_counterfactual_score": self.inferred_counterfactual_score,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "scored_at": self.scored_at,
            "scored_by": self.scored_by,
            "evidence_metadata": self.evidence_metadata,
            "schema_version": self.schema_version,
        }
        return json.dumps(payload, sort_keys=True)

    def sign(self) -> "CounterfactualRecord":
        self.hmac = _hmac.new(
            _hmac_key(),
            self.signable_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return self

    def verify(self) -> bool:
        expected = _hmac.new(
            _hmac_key(),
            self.signable_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return _hmac.compare_digest(self.hmac, expected)


# ─────────────────────────────────────────────
# Scoring functions
# ─────────────────────────────────────────────


def _validate_observability(
    kind: str,
    observed_alternative_outcome_ids: Iterable[str],
    evidence_metadata: dict | None,
) -> tuple[bool, str]:
    """Return (observable, reason). Doctrine guard at the entrance.

    Each kind has its own minimum-evidence bar:
      direct       — at least one observed alternative outcome id
      comparative  — at least one outcome id AND `comparing_entities` in metadata
      temporal     — at least one outcome id AND `regime_change_at` in metadata
    """
    outcome_ids = list(observed_alternative_outcome_ids)
    if not outcome_ids:
        return (
            False,
            "no observed_alternative_outcome_ids — would be speculation",
        )
    if kind == "direct":
        return (True, "")
    if kind == "comparative":
        if not evidence_metadata or "comparing_entities" not in evidence_metadata:
            return (
                False,
                "comparative requires evidence_metadata.comparing_entities "
                "(list of >=2 entities observed)",
            )
        ents = evidence_metadata.get("comparing_entities") or []
        if not isinstance(ents, list) or len(ents) < 2:
            return (
                False,
                "comparative requires >=2 entries in "
                "evidence_metadata.comparing_entities",
            )
        return (True, "")
    if kind == "temporal":
        if not evidence_metadata or "regime_change_at" not in evidence_metadata:
            return (
                False,
                "temporal requires evidence_metadata.regime_change_at (ISO-8601 ts)",
            )
        return (True, "")
    # Should never hit — kind was validated upstream.
    return (False, f"unknown kind {kind!r}")


def score_counterfactual(
    rejected_decision_id: str,
    observed_alternative_outcome_ids: Iterable[str],
    kind: str,
    *,
    rejected_projection_value: float | None = None,
    observed_alternative_value: float | None = None,
    alternative_chosen_id: str | None = None,
    evidence_metadata: dict | None = None,
    reasoning: str = "",
) -> Optional[CounterfactualScore]:
    """Score one counterfactual, or return None if not observable.

    Doctrine: NEVER synthesizes a speculative counterfactual — returns None
    when the observability bar isn't met. The caller's contract is:
      - if None is returned, do not persist anything;
      - if a CounterfactualScore is returned, the caller may persist it via
        `persist_record(...)`.

    Args:
      rejected_decision_id:        the decision whose alternative is being
                                   scored as a counterfactual.
      observed_alternative_outcome_ids:
                                   ids of OutcomeEvents the alternative
                                   actually produced. MUST be non-empty.
      kind:                        'direct' | 'comparative' | 'temporal'
      rejected_projection_value:   the rejected decision's projected metric
                                   value (used to compute relative score).
                                   When None, score defaults to 0.0 (we still
                                   record the counterfactual is observable).
      observed_alternative_value:  the alternative's actually-observed metric
                                   value. Same default behavior as above.
      alternative_chosen_id:       (direct only) the decision that was chosen
                                   instead of the rejected one. Optional.
      evidence_metadata:           extra evidence fields the kind requires:
                                     comparative -> {'comparing_entities': [...]}
                                     temporal    -> {'regime_change_at': ISO}
      reasoning:                   caller-supplied reason (>=20 chars when the
                                   score is non-zero). When omitted, we compose
                                   a default.

    Returns: CounterfactualScore | None
    """
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"kind must be one of {sorted(_VALID_KINDS)}; got {kind!r}"
        )
    if not rejected_decision_id:
        raise ValueError("rejected_decision_id is required")

    outcome_ids = list(observed_alternative_outcome_ids)
    observable, why_not = _validate_observability(
        kind, outcome_ids, evidence_metadata
    )
    if not observable:
        return None

    # Compute the signed score. Convention:
    #   score = (rejected_projection - observed_alternative) / |observed_alternative|
    # Positive => rejected would have beaten the chosen alternative (rejection
    # looks like a mistake). Clamped to [-1.0, 1.0].
    score = 0.0
    if (
        rejected_projection_value is not None
        and observed_alternative_value is not None
    ):
        denom = abs(observed_alternative_value)
        if denom > 1e-12:
            score = (rejected_projection_value - observed_alternative_value) / denom
        else:
            # Zero alternative -> use raw_diff direction
            diff = rejected_projection_value - observed_alternative_value
            score = 1.0 if diff > 0 else (-1.0 if diff < 0 else 0.0)
        score = max(-1.0, min(1.0, score))

    # Confidence per kind — comparative + temporal are weaker than direct
    # because they rely on assumptions about entity/regime similarity.
    confidence = {
        "direct": 0.85,
        "comparative": 0.65,
        "temporal": 0.55,
    }[kind]
    # Boost if multiple alternative outcomes observed (cross-checked signal).
    if len(outcome_ids) >= 3:
        confidence = min(0.95, confidence + 0.10)

    composed_reasoning = reasoning or (
        f"Counterfactual({kind}) for rejected decision "
        f"{rejected_decision_id!r}: observed {len(outcome_ids)} alternative "
        f"outcome(s); score={score:+.4f}; confidence={confidence:.2f}"
    )

    return CounterfactualScore(
        rejected_decision_id=rejected_decision_id,
        kind=kind,
        observed_alternative_outcome_ids=outcome_ids,
        inferred_counterfactual_score=round(score, 6),
        confidence=round(confidence, 4),
        reasoning=composed_reasoning,
        alternative_chosen_id=alternative_chosen_id,
        evidence_metadata=dict(evidence_metadata or {}),
    )


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────


def persist_record(
    record_or_score: CounterfactualRecord | CounterfactualScore,
    db_path: str | None = None,
    *,
    scored_by: str = "system",
) -> dict:
    """Persist a counterfactual record. Auto-signs HMAC.

    Accepts either a constructed CounterfactualRecord or a CounterfactualScore
    (from `score_counterfactual`). The score variant is the typical caller
    path — score in memory, persist when ready.
    """
    if isinstance(record_or_score, CounterfactualScore):
        record = CounterfactualRecord(
            rejected_decision_id=record_or_score.rejected_decision_id,
            kind=record_or_score.kind,
            observed_alternative_outcome_ids=list(
                record_or_score.observed_alternative_outcome_ids
            ),
            inferred_counterfactual_score=record_or_score.inferred_counterfactual_score,
            confidence=record_or_score.confidence,
            reasoning=record_or_score.reasoning,
            alternative_chosen_id=record_or_score.alternative_chosen_id,
            evidence_metadata=dict(record_or_score.evidence_metadata),
            scored_by=scored_by,
        )
    else:
        record = record_or_score
        if scored_by and scored_by != "system":
            record.scored_by = scored_by

    if not record.hmac:
        record.sign()

    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO counterfactual_records (
                id, rejected_decision_id, alternative_chosen_id,
                observed_alternative_outcome_ids, kind,
                inferred_counterfactual_score, confidence,
                reasoning, scored_at, scored_by, hmac,
                evidence_metadata, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.rejected_decision_id,
                record.alternative_chosen_id,
                json.dumps(record.observed_alternative_outcome_ids),
                record.kind,
                record.inferred_counterfactual_score,
                record.confidence,
                record.reasoning,
                record.scored_at,
                record.scored_by,
                record.hmac,
                json.dumps(record.evidence_metadata),
                record.schema_version,
            ),
        )
    finally:
        conn.close()
    return _record_to_dict(record)


def get_record(
    record_id: str,
    db_path: str | None = None,
) -> Optional[CounterfactualRecord]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM counterfactual_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)
    finally:
        conn.close()


def list_records(
    rejected_decision_id: str | None = None,
    kind: str | None = None,
    db_path: str | None = None,
    limit: int = 200,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        clauses: list[str] = []
        params: list = []
        if rejected_decision_id is not None:
            clauses.append("rejected_decision_id = ?")
            params.append(rejected_decision_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM counterfactual_records {where} "
            f"ORDER BY scored_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [_record_to_dict(_row_to_record(r)) for r in rows]
    finally:
        conn.close()


def verify_record(record_id: str, db_path: str | None = None) -> bool:
    rec = get_record(record_id, db_path=db_path)
    if rec is None:
        return False
    return rec.verify()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _row_to_record(row: sqlite3.Row) -> CounterfactualRecord:
    d = dict(row)
    return CounterfactualRecord(
        id=d["id"],
        rejected_decision_id=d["rejected_decision_id"],
        alternative_chosen_id=d.get("alternative_chosen_id"),
        observed_alternative_outcome_ids=json.loads(
            d["observed_alternative_outcome_ids"]
        ),
        kind=d["kind"],
        inferred_counterfactual_score=d["inferred_counterfactual_score"],
        confidence=d["confidence"],
        reasoning=d["reasoning"],
        scored_at=d["scored_at"],
        scored_by=d.get("scored_by") or "system",
        hmac=d["hmac"],
        evidence_metadata=json.loads(d.get("evidence_metadata") or "{}"),
        schema_version=d.get("schema_version") or "v1",
    )


def _record_to_dict(record: CounterfactualRecord) -> dict:
    return {
        "id": record.id,
        "rejected_decision_id": record.rejected_decision_id,
        "alternative_chosen_id": record.alternative_chosen_id,
        "observed_alternative_outcome_ids": list(
            record.observed_alternative_outcome_ids
        ),
        "kind": record.kind,
        "inferred_counterfactual_score": record.inferred_counterfactual_score,
        "confidence": record.confidence,
        "reasoning": record.reasoning,
        "scored_at": record.scored_at,
        "scored_by": record.scored_by,
        "hmac": record.hmac,
        "evidence_metadata": dict(record.evidence_metadata),
        "schema_version": record.schema_version,
    }
