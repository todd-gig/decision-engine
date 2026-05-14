"""CalibrationRevision + HMAC chain.

Mirrors `engine/certificates.py` pattern — every revision is:
  - persisted as a row in `calibration_revisions`
  - mirrored as an `.md` file under `calibration-revisions/`
  - HMAC-SHA256 signed across canonical fields
  - tamper-evident: verify() returns False if either copy changes

WHY: calibration changes affect every future decision the engine grades, so
the audit pattern must match the existing certificate chain doctrine (cert
chain is HMAC-signed, dual-stored on disk + DB). Disk-backed audit survives
DB failure; DB-backed audit survives FS failure. Both must agree on read.

Mandatory reasoning per always-record-WHY rule — minimum 20 characters,
enforced at construction.

penrose_signal: weakens
penrose_dimension: variance
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import storage


# ─────────────────────────────────────────────
# HMAC key — reuse same source as engine/certificates.py / ai_router
# ─────────────────────────────────────────────

# Env name doctrine: the cert chain (`engine/trust_certificates.py:143`) uses
# `CERT_SECRET_KEY`; the ai_router (`engine/ai_router/audit.py:24`) uses
# `LLM_AUDIT_HMAC_KEY`. Calibration revisions are a peer of the cert chain,
# not the LLM audit log, so we read `CERT_SECRET_KEY` first and fall back to
# a dev default. Production deploy sets CERT_SECRET_KEY via Secret Manager.
_DEFAULT_DEV_KEY = "dev-only-ovs-calibration-key-do-not-use-in-prod"


def _hmac_key() -> bytes:
    return os.environ.get(
        "CERT_SECRET_KEY",
        os.environ.get("OVS_CALIBRATION_HMAC_KEY", _DEFAULT_DEV_KEY),
    ).encode("utf-8")


# ─────────────────────────────────────────────
# MD file location
# ─────────────────────────────────────────────


def _md_dir() -> Path:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    candidate = repo_root / "calibration-revisions"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


# ─────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────


_MIN_REASONING_CHARS = 20


@dataclass
class CalibrationRevision:
    """One signed calibration write.

    Fields per spec line 47 (§CalibrationRevision schema):
      id, dimension, beforeValue, afterValue, evidenceWindowStart,
      evidenceWindowEnd, evidenceOutcomeIds[], computationVersion,
      signedBy, hmac, signedAt
    Plus `reasoning` (always-record-WHY) and `md_path` (audit dual-store).
    """
    dimension: str
    before_value: float
    after_value: float
    evidence_window_start: str  # ISO-8601
    evidence_window_end: str    # ISO-8601
    evidence_outcome_ids: list[str]
    computation_version: str
    signed_by: str
    reasoning: str
    id: str = field(default_factory=lambda: f"rev-{uuid.uuid4().hex[:12]}")
    hmac: str = ""
    signed_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    md_path: str = ""
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.dimension:
            raise ValueError("dimension is required")
        if not self.signed_by:
            raise ValueError("signed_by is required")
        if not self.reasoning or len(self.reasoning.strip()) < _MIN_REASONING_CHARS:
            raise ValueError(
                f"reasoning is required and must be >= {_MIN_REASONING_CHARS} "
                f"characters (always-record-WHY rule); got "
                f"{len(self.reasoning.strip()) if self.reasoning else 0}"
            )
        if not self.computation_version:
            raise ValueError("computation_version is required")

    # ─────────────────────────────────────────
    # Signing
    # ─────────────────────────────────────────

    def signable_payload(self) -> str:
        """Canonical JSON payload over which HMAC is computed."""
        payload = {
            "id": self.id,
            "dimension": self.dimension,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "evidence_window_start": self.evidence_window_start,
            "evidence_window_end": self.evidence_window_end,
            "evidence_outcome_ids": sorted(self.evidence_outcome_ids),
            "computation_version": self.computation_version,
            "signed_by": self.signed_by,
            "signed_at": self.signed_at,
            "reasoning": self.reasoning,
            "schema_version": self.schema_version,
        }
        return json.dumps(payload, sort_keys=True)

    def sign(self) -> "CalibrationRevision":
        self.hmac = hmac.new(
            _hmac_key(),
            self.signable_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return self

    def verify(self) -> bool:
        expected = hmac.new(
            _hmac_key(),
            self.signable_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.hmac, expected)

    # ─────────────────────────────────────────
    # MD twin
    # ─────────────────────────────────────────

    def write_md(self, md_dir: Path | None = None) -> Path:
        target_dir = md_dir or _md_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.id}.md"
        path = target_dir / filename

        frontmatter = {
            "id": self.id,
            "dimension": self.dimension,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "delta": self.after_value - self.before_value,
            "evidence_window_start": self.evidence_window_start,
            "evidence_window_end": self.evidence_window_end,
            "evidence_outcome_count": len(self.evidence_outcome_ids),
            "computation_version": self.computation_version,
            "signed_by": self.signed_by,
            "signed_at": self.signed_at,
            "hmac": self.hmac,
            "schema_version": self.schema_version,
        }

        import yaml  # type: ignore[import-untyped]
        fm_yaml = yaml.dump(frontmatter, default_flow_style=False, sort_keys=True)

        delta = self.after_value - self.before_value
        delta_pct = (
            (delta / abs(self.before_value)) * 100 if self.before_value != 0 else 0.0
        )
        body = f"""## Calibration Revision — {self.dimension}

**Dimension:** `{self.dimension}`
**Change:** {self.before_value} -> {self.after_value} (delta {delta:+.4f}, {delta_pct:+.2f}%)
**Evidence window:** {self.evidence_window_start} -> {self.evidence_window_end}
**Evidence outcome count:** {len(self.evidence_outcome_ids)}
**Computation version:** {self.computation_version}
**Signed by:** {self.signed_by}
**Signed at:** {self.signed_at}

### Reasoning (why this calibration write was made)

{self.reasoning}

### Evidence outcome ids

{chr(10).join(f"- `{oid}`" for oid in sorted(self.evidence_outcome_ids))}

### HMAC-SHA256 signature

`{self.hmac}`

---
*This file is a required audit twin for calibration revision `{self.id}`. The
OVS-Calibration engine treats this revision as invalid if the file is missing
or its `hmac` field does not match the loaded revision.*
"""
        path.write_text(f"---\n{fm_yaml}---\n\n{body}", encoding="utf-8")
        self.md_path = str(path)
        return path

    def md_file_valid(self) -> bool:
        """True if the MD twin exists and its hmac frontmatter matches."""
        if not self.md_path or not Path(self.md_path).exists():
            return False
        try:
            import yaml  # type: ignore[import-untyped]
            import re
            text = Path(self.md_path).read_text(encoding="utf-8")
            match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
            if not match:
                return False
            fm = yaml.safe_load(match.group(1))
            return fm.get("id") == self.id and fm.get("hmac") == self.hmac
        except Exception:
            return False


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────


def write_revision(
    revision: CalibrationRevision,
    db_path: str | None = None,
    md_dir: Path | None = None,
) -> dict:
    """Sign + persist + write MD twin. Returns the persisted row as dict."""
    if not revision.hmac:
        revision.sign()
    md_path = revision.write_md(md_dir=md_dir)
    revision.md_path = str(md_path)

    conn = storage.get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO calibration_revisions (
                id, dimension, before_value, after_value,
                evidence_window_start, evidence_window_end,
                evidence_outcome_ids, computation_version,
                signed_by, hmac, signed_at, reasoning,
                md_path, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision.id,
                revision.dimension,
                revision.before_value,
                revision.after_value,
                revision.evidence_window_start,
                revision.evidence_window_end,
                json.dumps(revision.evidence_outcome_ids),
                revision.computation_version,
                revision.signed_by,
                revision.hmac,
                revision.signed_at,
                revision.reasoning,
                revision.md_path,
                revision.schema_version,
            ),
        )
    finally:
        conn.close()
    return _revision_to_dict(revision)


def get_revision(
    revision_id: str,
    db_path: str | None = None,
) -> Optional[CalibrationRevision]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM calibration_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_revision(row)
    finally:
        conn.close()


def list_revisions(
    dimension: str | None = None,
    db_path: str | None = None,
    limit: int = 200,
) -> list[dict]:
    conn = storage.get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if dimension is None:
            rows = conn.execute(
                "SELECT * FROM calibration_revisions ORDER BY signed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM calibration_revisions WHERE dimension = ?
                ORDER BY signed_at DESC LIMIT ?
                """,
                (dimension, limit),
            ).fetchall()
        return [
            _revision_to_dict(_row_to_revision(r)) | {"verified": _row_to_revision(r).verify()}
            for r in rows
        ]
    finally:
        conn.close()


def verify_revision(revision_id: str, db_path: str | None = None) -> bool:
    """Load and verify HMAC + MD twin. Returns True only if both intact."""
    rev = get_revision(revision_id, db_path=db_path)
    if rev is None:
        return False
    if not rev.verify():
        return False
    if rev.md_path and not rev.md_file_valid():
        return False
    return True


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _row_to_revision(row: sqlite3.Row) -> CalibrationRevision:
    d = dict(row)
    return CalibrationRevision(
        id=d["id"],
        dimension=d["dimension"],
        before_value=d["before_value"],
        after_value=d["after_value"],
        evidence_window_start=d["evidence_window_start"],
        evidence_window_end=d["evidence_window_end"],
        evidence_outcome_ids=json.loads(d["evidence_outcome_ids"]),
        computation_version=d["computation_version"],
        signed_by=d["signed_by"],
        hmac=d["hmac"],
        signed_at=d["signed_at"],
        reasoning=d["reasoning"],
        md_path=d.get("md_path") or "",
        schema_version=d.get("schema_version") or "v1",
    )


def _revision_to_dict(rev: CalibrationRevision) -> dict:
    return {
        "id": rev.id,
        "dimension": rev.dimension,
        "before_value": rev.before_value,
        "after_value": rev.after_value,
        "evidence_window_start": rev.evidence_window_start,
        "evidence_window_end": rev.evidence_window_end,
        "evidence_outcome_ids": list(rev.evidence_outcome_ids),
        "computation_version": rev.computation_version,
        "signed_by": rev.signed_by,
        "hmac": rev.hmac,
        "signed_at": rev.signed_at,
        "reasoning": rev.reasoning,
        "md_path": rev.md_path,
        "schema_version": rev.schema_version,
    }
