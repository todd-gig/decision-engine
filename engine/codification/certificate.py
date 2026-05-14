"""CodificationCertificate — HMAC-SHA256 governance seal for promoted proposals.

Mirrors the trust certificate pattern in `engine/trust_certificates.py`:
each issued certificate gets a matching `.md` file on disk so an absent
or tampered file invalidates the cert. Persisted alongside proposals in
`drift_sentinel/codification_proposals.db` so audit and replay are local
to the engine.

Mandatory fields enforced at construction (per always-record-WHY):
  id, candidate_id, signers[], decision_class, reasoning (≥20 chars),
  evidence_decision_ids[], proposed_spec, hmac, signed_at,
  schema_version, prompt_version.

Empty / short reasoning → ValueError. Missing signers → ValueError.

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import storage


# ── Constants ──────────────────────────────────────────────────────────────

MIN_REASONING_CHARS = 20
SECRET_KEY_ENV = "CERT_SECRET_KEY"
DEFAULT_SECRET_KEY = "dev-secret-change-in-prod"
CERT_MD_DIRNAME = "certificates/codification"
CERT_TABLE_NAME = "codification_certificates"


def _certs_md_dir() -> Path:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    target = repo_root / CERT_MD_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def _secret_key() -> str:
    return os.environ.get(SECRET_KEY_ENV, DEFAULT_SECRET_KEY)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ── Data structure ─────────────────────────────────────────────────────────


@dataclass
class CodificationCertificate:
    """Tamper-evident seal that a codification proposal has been approved."""
    candidate_id: str
    signers: list[str]
    decision_class: str
    reasoning: str
    evidence_decision_ids: list[str]
    proposed_spec: str
    prompt_version: str
    schema_version: str
    id: str = field(default_factory=lambda: f"CDC-{uuid.uuid4().hex[:12].upper()}")
    signed_at: str = field(default_factory=_now_iso)
    hmac: str = ""
    md_path: str = ""

    # ── Validation ─────────────────────────────────────────────────────────
    def validate(self) -> None:
        """Validate mandatory fields. Always raises on missing/short data.

        WHY: §always-record-WHY + governance rule — a certificate that
        doesn't carry the reason cannot ground future learning.
        """
        if not self.candidate_id:
            raise ValueError("candidate_id is required")
        if not self.signers:
            raise ValueError("at least one signer is required")
        if not all(isinstance(s, str) and s.strip() for s in self.signers):
            raise ValueError("signers must be non-empty strings")
        if not self.decision_class:
            raise ValueError("decision_class is required")
        if not self.reasoning or len(self.reasoning.strip()) < MIN_REASONING_CHARS:
            raise ValueError(
                f"reasoning must be at least {MIN_REASONING_CHARS} chars (always-record-WHY)"
            )
        if not isinstance(self.evidence_decision_ids, list):
            raise ValueError("evidence_decision_ids must be a list")
        if not self.proposed_spec:
            raise ValueError("proposed_spec is required")
        if not self.prompt_version:
            raise ValueError("prompt_version is required")
        if not self.schema_version:
            raise ValueError("schema_version is required")

    # ── Signing ────────────────────────────────────────────────────────────
    def _signable_payload(self) -> str:
        """Canonicalized JSON over fields that bind the certificate."""
        payload = {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "signers": sorted(self.signers),
            "decision_class": self.decision_class,
            "reasoning": self.reasoning,
            "evidence_decision_ids": list(self.evidence_decision_ids),
            "proposed_spec_sha256": hashlib.sha256(
                self.proposed_spec.encode("utf-8")
            ).hexdigest(),
            "signed_at": self.signed_at,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }
        return json.dumps(payload, sort_keys=True)

    def sign(self, secret_key: Optional[str] = None) -> "CodificationCertificate":
        key = secret_key or _secret_key()
        self.validate()
        self.hmac = hmac.new(
            key.encode("utf-8"),
            self._signable_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return self

    def verify(self, secret_key: Optional[str] = None) -> bool:
        """Recompute the HMAC and compare. Detects tampering."""
        key = secret_key or _secret_key()
        try:
            self.validate()
        except ValueError:
            return False
        expected = hmac.new(
            key.encode("utf-8"),
            self._signable_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.hmac, expected)

    # ── Serialization ──────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CodificationCertificate":
        return cls(
            id=row["id"],
            candidate_id=row["candidate_id"],
            signers=json.loads(row["signers"]),
            decision_class=row["decision_class"],
            reasoning=row["reasoning"],
            evidence_decision_ids=json.loads(row["evidence_decision_ids"]),
            proposed_spec=row["proposed_spec"],
            hmac=row["hmac"],
            signed_at=row["signed_at"],
            prompt_version=row["prompt_version"],
            schema_version=row["schema_version"],
            md_path=row.get("md_path", "") or "",
        )

    # ── MD file requirement ────────────────────────────────────────────────
    def md_file_exists(self) -> bool:
        return bool(self.md_path) and Path(self.md_path).exists()

    def md_file_matches(self) -> bool:
        """True iff the .md frontmatter `id` + `hmac` match this cert."""
        if not self.md_file_exists():
            return False
        try:
            text = Path(self.md_path).read_text(encoding="utf-8")
        except OSError:
            return False
        m = re.search(r"^id:\s*(\S+)\s*$", text, re.MULTILINE)
        h = re.search(r"^hmac:\s*(\S+)\s*$", text, re.MULTILINE)
        if not m or not h:
            return False
        return m.group(1) == self.id and h.group(1) == self.hmac


# ── Storage ────────────────────────────────────────────────────────────────


def _ensure_cert_table(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {CERT_TABLE_NAME} (
            id                     TEXT PRIMARY KEY,
            candidate_id           TEXT NOT NULL,
            signers                TEXT NOT NULL,             -- JSON array
            decision_class         TEXT NOT NULL,
            reasoning              TEXT NOT NULL,
            evidence_decision_ids  TEXT NOT NULL,             -- JSON array
            proposed_spec          TEXT NOT NULL,
            hmac                   TEXT NOT NULL,
            signed_at              TEXT NOT NULL,
            prompt_version         TEXT NOT NULL,
            schema_version         TEXT NOT NULL,
            md_path                TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_codification_certs_candidate
            ON {CERT_TABLE_NAME}(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_codification_certs_class
            ON {CERT_TABLE_NAME}(decision_class, signed_at);
    """)


def _get_cert_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Reuse the codification proposals SQLite file for cert rows.

    Single file simplifies operator UX: one place to look for proposals
    and their seals. The cert table is independent of the proposal table.
    """
    conn = storage.get_connection(db_path)
    _ensure_cert_table(conn)
    return conn


def persist_certificate(
    cert: CodificationCertificate,
    *,
    db_path: Optional[str] = None,
    md_dir: Optional[Path | str] = None,
) -> CodificationCertificate:
    """Write a row to the DB AND the matching .md file. Mutates cert.md_path."""
    if not cert.hmac:
        raise ValueError("certificate must be signed before persistence")

    md_path = _write_md(cert, md_dir=md_dir)
    cert.md_path = str(md_path)

    conn = _get_cert_connection(db_path)
    try:
        conn.execute(
            f"""
            INSERT INTO {CERT_TABLE_NAME} (
                id, candidate_id, signers, decision_class, reasoning,
                evidence_decision_ids, proposed_spec, hmac, signed_at,
                prompt_version, schema_version, md_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cert.id,
                cert.candidate_id,
                json.dumps(sorted(cert.signers)),
                cert.decision_class,
                cert.reasoning,
                json.dumps(list(cert.evidence_decision_ids)),
                cert.proposed_spec,
                cert.hmac,
                cert.signed_at,
                cert.prompt_version,
                cert.schema_version,
                cert.md_path,
            ),
        )
    finally:
        conn.close()
    return cert


def get_certificate(
    cert_id: str, db_path: Optional[str] = None
) -> Optional[CodificationCertificate]:
    conn = _get_cert_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"SELECT * FROM {CERT_TABLE_NAME} WHERE id = ?", (cert_id,)
        ).fetchone()
        return CodificationCertificate.from_row(dict(row)) if row else None
    finally:
        conn.close()


def list_certificates_for_candidate(
    candidate_id: str, db_path: Optional[str] = None
) -> list[CodificationCertificate]:
    conn = _get_cert_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM {CERT_TABLE_NAME} WHERE candidate_id = ? ORDER BY signed_at DESC",
            (candidate_id,),
        ).fetchall()
        return [CodificationCertificate.from_row(dict(r)) for r in rows]
    finally:
        conn.close()


# ── MD file writer ─────────────────────────────────────────────────────────


def _write_md(
    cert: CodificationCertificate, md_dir: Optional[Path | str] = None
) -> Path:
    base = Path(md_dir) if md_dir else _certs_md_dir()
    base.mkdir(parents=True, exist_ok=True)

    safe_class = re.sub(r"[^a-z0-9_-]", "_", cert.decision_class.lower())
    filename = f"cert_{safe_class}_{cert.id}.md"
    path = base / filename

    spec_sha = hashlib.sha256(cert.proposed_spec.encode("utf-8")).hexdigest()
    body = f"""---
id: {cert.id}
candidate_id: {cert.candidate_id}
decision_class: {cert.decision_class}
prompt_version: {cert.prompt_version}
schema_version: {cert.schema_version}
signed_at: {cert.signed_at}
hmac: {cert.hmac}
signers: {json.dumps(sorted(cert.signers))}
evidence_decision_ids: {json.dumps(list(cert.evidence_decision_ids))}
proposed_spec_sha256: {spec_sha}
---

# Codification Certificate — `{cert.id}`

**Candidate:** `{cert.candidate_id}`
**Decision class:** `{cert.decision_class}`
**Signed at:** {cert.signed_at}
**Signers:** {", ".join(sorted(cert.signers))}

## Reasoning (WHY)

{cert.reasoning}

## Evidence decision IDs

{chr(10).join(f"- `{d}`" for d in cert.evidence_decision_ids) or "- (none)"}

## Proposed spec (SHA-256: `{spec_sha}`)

```
{cert.proposed_spec}
```

## HMAC-SHA256 signature

`{cert.hmac}`

---

*Codification governance certificate. The codification engine refuses
to recognize this seal if the file is missing, renamed, or if `id` /
`hmac` no longer match the persisted certificate row.*
"""
    path.write_text(body, encoding="utf-8")
    return path


__all__ = [
    "CodificationCertificate",
    "MIN_REASONING_CHARS",
    "persist_certificate",
    "get_certificate",
    "list_certificates_for_candidate",
]
