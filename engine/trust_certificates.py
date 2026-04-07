"""
trust_certificates.py
Trust certificates define the scope and authority for autonomous decision execution.
Each certificate is HMAC-signed to prevent tampering.

MD File Requirement
-------------------
Every certificate MUST have a corresponding MD file in memory/certs/.
The MD file is created automatically on issue() and serves as the
human-readable, auditable record of the certificate.

The DecisionEngine refuses to load or execute against any certificate
whose MD file is missing, moved, or whose signature no longer matches
the file contents — ensuring no certificate can be silently tampered with.
"""

from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml

# Default location for cert MD files — relative to this file's package root
_PKG_ROOT = Path(__file__).parent.parent
CERTS_MD_DIR = _PKG_ROOT / "memory" / "certs"


class TrustLevel(IntEnum):
    OBSERVE   = 1   # log only, never execute
    SUGGEST   = 2   # propose actions, require human approval
    ASSIST    = 3   # execute low-risk actions, escalate medium/high
    DELEGATE  = 4   # execute medium-risk, escalate only high-risk
    AUTONOMOUS = 5  # execute all actions within domain constraints


@dataclass
class TrustCertificate:
    cert_id: str
    domain: str                          # e.g. "scheduling", "memory", "communication"
    trust_level: TrustLevel
    auto_execute_threshold: float        # confidence 0.0–1.0 required for auto-exec
    allowed_actions: list[str]           # action type names permitted
    constraints: dict[str, Any]          # key/value limits e.g. {"max_cost_usd": 50}
    issued_at: str
    expires_at: str
    issuer: str
    signature: str = ""
    md_path: str = ""                    # absolute path to the required MD file

    # ── Signing ────────────────────────────────────────────────────────────────
    def _signable_payload(self) -> str:
        payload = {
            "cert_id": self.cert_id,
            "domain": self.domain,
            "trust_level": int(self.trust_level),
            "auto_execute_threshold": self.auto_execute_threshold,
            "allowed_actions": sorted(self.allowed_actions),
            "constraints": self.constraints,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "issuer": self.issuer,
        }
        return json.dumps(payload, sort_keys=True)

    def sign(self, secret_key: str) -> "TrustCertificate":
        payload = self._signable_payload()
        self.signature = hmac.new(
            secret_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return self

    def verify(self, secret_key: str) -> bool:
        expected = hmac.new(
            secret_key.encode(), self._signable_payload().encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    # ── Validity ───────────────────────────────────────────────────────────────
    def is_expired(self) -> bool:
        expiry = datetime.fromisoformat(self.expires_at)
        return datetime.now(timezone.utc) > expiry

    def is_valid(self, secret_key: str) -> bool:
        return not self.is_expired() and self.verify(secret_key)

    def allows_action(self, action: str) -> bool:
        return action in self.allowed_actions or "*" in self.allowed_actions

    # ── MD file requirement ────────────────────────────────────────────────────
    def md_file_exists(self) -> bool:
        """True if the required MD file is present on disk."""
        return bool(self.md_path) and Path(self.md_path).exists()

    def md_file_valid(self) -> bool:
        """
        True if the MD file exists AND its embedded cert_id + signature
        match this certificate exactly. Detects tampering or file swap.
        """
        if not self.md_file_exists():
            return False
        try:
            text = Path(self.md_path).read_text(encoding="utf-8")
            match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
            if not match:
                return False
            fm = yaml.safe_load(match.group(1))
            return (
                fm.get("cert_id") == self.cert_id
                and fm.get("signature") == self.signature
            )
        except Exception:
            return False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trust_level"] = int(self.trust_level)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TrustCertificate":
        d = dict(d)
        d["trust_level"] = TrustLevel(d["trust_level"])
        return cls(**d)


class CertificateAuthority:
    """Issues and verifies trust certificates."""

    def __init__(
        self,
        secret_key: str | None = None,
        certs_dir: Path | str | None = None,
    ):
        self.secret_key = secret_key or os.environ.get("CERT_SECRET_KEY", "dev-secret-change-in-prod")
        self.certs_dir = Path(certs_dir or CERTS_MD_DIR)
        self.certs_dir.mkdir(parents=True, exist_ok=True)

    def issue(
        self,
        domain: str,
        trust_level: TrustLevel,
        allowed_actions: list[str],
        constraints: dict[str, Any] | None = None,
        issuer: str = "system",
        valid_days: int = 365,
        auto_execute_threshold: float | None = None,
    ) -> TrustCertificate:
        # Default threshold scales with trust level
        if auto_execute_threshold is None:
            thresholds = {1: 1.0, 2: 0.95, 3: 0.80, 4: 0.70, 5: 0.60}
            auto_execute_threshold = thresholds[int(trust_level)]

        now = datetime.now(timezone.utc)
        cert = TrustCertificate(
            cert_id=str(uuid.uuid4()),
            domain=domain,
            trust_level=trust_level,
            auto_execute_threshold=auto_execute_threshold,
            allowed_actions=allowed_actions,
            constraints=constraints or {},
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(days=valid_days)).isoformat(),
            issuer=issuer,
        )
        cert.sign(self.secret_key)

        # Write the required MD file — must exist before the cert is usable
        md_path = self._write_md(cert)
        cert.md_path = str(md_path)

        return cert

    def _write_md(self, cert: TrustCertificate) -> Path:
        """
        Write the canonical MD file for this certificate.
        The file is the human-readable audit record AND the on-disk
        presence check the decision engine uses before execution.
        """
        level_names = {1: "OBSERVE", 2: "SUGGEST", 3: "ASSIST", 4: "DELEGATE", 5: "AUTONOMOUS"}
        level_name  = level_names.get(int(cert.trust_level), str(cert.trust_level))

        frontmatter = {
            "cert_id":                 cert.cert_id,
            "domain":                  cert.domain,
            "trust_level":             int(cert.trust_level),
            "trust_level_name":        level_name,
            "auto_execute_threshold":  cert.auto_execute_threshold,
            "allowed_actions":         cert.allowed_actions,
            "constraints":             cert.constraints,
            "issued_at":               cert.issued_at,
            "expires_at":              cert.expires_at,
            "issuer":                  cert.issuer,
            "signature":               cert.signature,
        }
        fm_yaml = yaml.dump(frontmatter, default_flow_style=False, sort_keys=True)

        body = f"""## Trust Certificate — {cert.domain.title()}

**Domain:** `{cert.domain}`
**Trust level:** {int(cert.trust_level)} — {level_name}
**Auto-execute threshold:** {cert.auto_execute_threshold:.0%} confidence required
**Issuer:** `{cert.issuer}`
**Valid:** {cert.issued_at[:10]} → {cert.expires_at[:10]}

### Permitted actions
{chr(10).join(f"- `{a}`" for a in cert.allowed_actions)}

### Constraints
{chr(10).join(f"- `{k}`: {v}" for k, v in cert.constraints.items()) or "- None"}

### Certificate ID
`{cert.cert_id}`

### HMAC-SHA256 signature
`{cert.signature}`

---
*This file is a required trust certificate. The decision engine will refuse to
execute any decision in the `{cert.domain}` domain if this file is missing,
renamed, or if its `cert_id` / `signature` fields do not match the loaded certificate.*
"""

        filename = f"cert_{cert.domain}_{cert.cert_id[:8]}.md"
        path = self.certs_dir / filename
        path.write_text(f"---\n{fm_yaml}---\n\n{body}", encoding="utf-8")
        return path

    def verify(self, cert: TrustCertificate) -> bool:
        return cert.is_valid(self.secret_key)


# ── Default certificates for bootstrapping ─────────────────────────────────────
DEFAULT_CERTS = [
    {
        "domain": "memory",
        "trust_level": TrustLevel.AUTONOMOUS,
        "allowed_actions": ["read_memory", "write_memory", "update_memory", "create_memory", "index_memory"],
        "constraints": {"max_file_size_kb": 512},
    },
    {
        "domain": "scheduling",
        "trust_level": TrustLevel.DELEGATE,
        "allowed_actions": ["create_event", "update_event", "cancel_event", "suggest_time"],
        "constraints": {"max_duration_hours": 8, "no_weekends": False},
    },
    {
        "domain": "communication",
        "trust_level": TrustLevel.ASSIST,
        "allowed_actions": ["draft_message", "send_message", "create_summary"],
        "constraints": {"require_approval_above_trust": 3},
    },
    {
        "domain": "learning",
        "trust_level": TrustLevel.AUTONOMOUS,
        "allowed_actions": ["record_learning_event", "update_weights", "adjust_threshold"],
        "constraints": {"threshold_min": 0.50, "threshold_max": 0.99},
    },
    {
        "domain": "decision",
        "trust_level": TrustLevel.DELEGATE,
        "allowed_actions": ["evaluate_option", "select_option", "escalate", "log_decision"],
        "constraints": {"max_financial_impact_usd": 100},
    },
]


def bootstrap_certificates(ca: CertificateAuthority) -> list[TrustCertificate]:
    return [ca.issue(**cfg) for cfg in DEFAULT_CERTS]
