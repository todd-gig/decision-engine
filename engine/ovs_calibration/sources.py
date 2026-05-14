"""OutcomeSource registry.

Per outcome_calibration_engine_spec.md §OutcomeSource (decision #1 — explicit
registry table). Sources must be registered before they can ingest; registration
includes schema, owner, ingestion contract, and the decision-class -> metric
mappings used by the attribution daemon.

WHY: silent ingestion of new outcome streams produces unattributable noise;
explicit registration forces clarity on what each metric means and which
decisions it can attribute to (matches the `undefined_ownership` anti-pattern
prevention pattern from the canonical doctrine).

penrose_signal: weakens
penrose_dimension: variance
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import storage


_VALID_KINDS = {"revenue", "conversion", "operational", "satisfaction", "external"}
_VALID_CONTRACTS = {"pubsub", "webhook", "polling"}
_VALID_HEALTH = {"healthy", "degraded", "offline", "unknown"}


@dataclass
class OutcomeSource:
    """Registry row for an outcome ingestion source.

    Fields per spec line 58 + §6 registration data model.
    """
    name: str
    kind: str  # revenue | conversion | operational | satisfaction | external
    entity: str
    ingestion_contract: str  # pubsub | webhook | polling
    schema: dict  # JSON schema for OutcomeEvent payloads from this source
    owner: str
    health_status: str = "unknown"
    decision_class_metric_map: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"src-{uuid.uuid4().hex[:12]}")
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(_VALID_KINDS)}; got {self.kind!r}"
            )
        if self.ingestion_contract not in _VALID_CONTRACTS:
            raise ValueError(
                f"ingestion_contract must be one of {sorted(_VALID_CONTRACTS)}; "
                f"got {self.ingestion_contract!r}"
            )
        if self.health_status not in _VALID_HEALTH:
            raise ValueError(
                f"health_status must be one of {sorted(_VALID_HEALTH)}; "
                f"got {self.health_status!r}"
            )
        if not self.name or not self.entity or not self.owner:
            raise ValueError("name, entity, and owner are required (non-empty)")


def register_source(source: OutcomeSource, db_path: str | None = None) -> dict:
    """Insert a new outcome source into the registry.

    Raises sqlite3.IntegrityError on duplicate id.
    """
    conn = storage.get_connection(db_path)
    try:
        now = datetime.now(tz=timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO outcome_sources (
                id, name, kind, entity, ingestion_contract, schema_json,
                owner, health_status, decision_class_metric_map,
                schema_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.name,
                source.kind,
                source.entity,
                source.ingestion_contract,
                json.dumps(source.schema),
                source.owner,
                source.health_status,
                json.dumps(source.decision_class_metric_map),
                source.schema_version,
                now,
                now,
            ),
        )
    finally:
        conn.close()
    return get_source(source.id, db_path=db_path)  # type: ignore[return-value]


def get_source(source_id: str, db_path: str | None = None) -> Optional[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM outcome_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def list_sources(
    kind: str | None = None,
    entity: str | None = None,
    db_path: str | None = None,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        clauses: list[str] = []
        params: list = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if entity is not None:
            clauses.append("entity = ?")
            params.append(entity)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM outcome_sources {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_health(
    source_id: str,
    health_status: str,
    db_path: str | None = None,
) -> dict:
    if health_status not in _VALID_HEALTH:
        raise ValueError(
            f"health_status must be one of {sorted(_VALID_HEALTH)}; "
            f"got {health_status!r}"
        )
    conn = storage.get_connection(db_path)
    try:
        now = datetime.now(tz=timezone.utc).isoformat()
        cur = conn.execute(
            """
            UPDATE outcome_sources SET health_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (health_status, now, source_id),
        )
        if cur.rowcount == 0:
            raise LookupError(f"source {source_id!r} not found")
    finally:
        conn.close()
    return get_source(source_id, db_path=db_path)  # type: ignore[return-value]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "schema_json" in d:
        d["schema"] = json.loads(d.pop("schema_json"))
    if d.get("decision_class_metric_map"):
        d["decision_class_metric_map"] = json.loads(d["decision_class_metric_map"])
    else:
        d["decision_class_metric_map"] = {}
    return d
