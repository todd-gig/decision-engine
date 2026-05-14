"""Codification proposer — turns a ready Candidate into a draft Python module.

Per `specs/codification_engine_v0.md` §Scaffold flow: once readiness clears,
the proposer asks Claude (through `engine.ai_router.invoke`) to draft a
deterministic Python module that replaces the LLM call entirely.

Hard rules (enforced HERE, not at the LLM layer):

  - Every LLM call routes through `engine.ai_router.invoke` with
    `provider`, `model`, `prompt_version`, `schema_version` populated.
    Banned: any direct `anthropic` / `openai` SDK import. This module
    follows that rule and so does the code it generates.
  - The PROPOSED module must be deterministic Python only — if the
    generated source contains `anthropic`, `openai`, `requests.post`,
    or the string `claude` (case-insensitive), the proposer raises
    `BannedImportError`. Codified modules cannot contain LLM calls;
    that is the whole point of Penrose-weakening codification.
  - Generated code must include a stateless pure function with type
    hints, docstring, and `raises ValueError` on invalid input. The
    prompt forces this; the validator double-checks the output.
  - Every proposal is content-hashed (SHA-256) for HMAC-chain
    compatibility with the simulator.
  - A `.md` artifact is persisted under `codification-proposals/<id>.md`
    so operators have a single grep-able review surface alongside
    the SQLite row.

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import storage
from .certificate import CodificationCertificate
from ..ai_router import invoke as _ai_invoke


# ── Constants ──────────────────────────────────────────────────────────────

PROPOSER_PROMPT_VERSION = "codification.proposer.v1"
PROPOSER_SCHEMA_VERSION = "codification.proposer.schema.v1"
PROPOSAL_TABLE_NAME = "codification_module_proposals"

# Defaults — operators may override per-call.
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-3-5-sonnet"

PROPOSAL_MD_DIRNAME = "codification-proposals"

# Banned substrings — case-insensitive grep over generated source.
# Codified modules MUST be deterministic Python. If any of these appear
# in the LLM output, the proposal is rejected (Penrose-weakening only
# works if the proposed code actually weakens the LLM dependency).
BANNED_SUBSTRINGS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "requests.post",
    "claude",
    "httpx.post",
    "urllib.request",
)


class BannedImportError(ValueError):
    """Raised when a generated module references an LLM SDK."""


# ── Data structure ─────────────────────────────────────────────────────────


@dataclass
class ModuleProposal:
    """A draft deterministic Python module proposed by the LLM proposer.

    Stored to DB + .md artifact. `source_code` is the literal text the
    proposer received from the LLM (banned-import-validated). The
    `signature_match_hash` lets the simulator cross-reference a
    proposal without re-storing the full body.
    """
    candidate_id: str           # references CodificationProposal.proposal_id
    module_name: str
    target_path: str
    source_code: str
    signature_match_hash: str
    prompt_version: str
    schema_version: str
    generated_at: str
    generated_by_provider: str
    generated_by_model: str
    proposal_id: str = field(default_factory=lambda: f"MP-{uuid.uuid4().hex[:12].upper()}")
    md_path: str = ""
    ai_audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Prompt construction ────────────────────────────────────────────────────


_PROPOSER_PROMPT_TEMPLATE = """You are the Codification Proposer for the Gigaton Decision Engine.

Your job: read the stable LLM-call pattern below and emit a deterministic
Python module that replaces the LLM. The module MUST satisfy every rule
in §RULES or it will be rejected.

§CONTEXT

prompt_version: {candidate_pv}
schema_version: {candidate_sv}
candidate_score:  {candidate_score}
executions observed: {executions}
evidence audit_ids: {evidence_ids}
governance certificate: {certificate_id}
decision class:  {decision_class}
why this was promoted: {why}

§RULES (non-negotiable)

1. Output ONLY valid Python source code. No prose, no fences, no commentary.
2. Module MUST define a single public function whose name and signature
   match the candidate pattern. The function MUST be:
     - stateless (no module-level mutable state)
     - pure (same inputs -> same outputs)
     - fully type-hinted on parameters AND return value
3. Include a docstring stating purpose, inputs, outputs.
4. Raise ValueError on invalid input. Never silently coerce.
5. NO LLM calls. NO `anthropic`, `openai`, `requests`, `httpx`, `urllib`
   imports. NO calls to Claude or any model. This module replaces the
   LLM; if it called one it would defeat the entire point.
6. Standard library only unless absolutely required. Prefer simple
   regex / arithmetic / dict logic.
7. Top-of-module docstring must end with the literal lines:
     penrose_signal: weakens
     penrose_dimension: codification

§OUTPUT
Emit the full module source. Begin with the module docstring.
"""


def _build_proposer_prompt(
    *,
    candidate_pv: str,
    candidate_sv: str,
    candidate_score: float,
    executions: int,
    evidence_ids: list[str],
    certificate_id: str,
    decision_class: str,
    why: str,
) -> str:
    return _PROPOSER_PROMPT_TEMPLATE.format(
        candidate_pv=candidate_pv,
        candidate_sv=candidate_sv,
        candidate_score=f"{candidate_score:.3f}",
        executions=executions,
        evidence_ids=", ".join(evidence_ids) or "(none)",
        certificate_id=certificate_id,
        decision_class=decision_class,
        why=why,
    )


# ── Banned import / LLM-call check ─────────────────────────────────────────


_IMPORT_PAT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)


def _scan_banned(source: str) -> list[str]:
    """Return banned tokens found in source. Empty = clean.

    Two layers:
      1. Word-boundary regex match (any usage)
      2. import-line check (catches aliased imports too)
    """
    found: set[str] = set()
    lowered = source.lower()
    for tok in BANNED_SUBSTRINGS:
        if tok.lower() in lowered:
            found.add(tok)

    for m in _IMPORT_PAT.finditer(source):
        mod = m.group(1).lower()
        # Surface the package root in the violation message.
        root = mod.split(".")[0]
        for tok in BANNED_SUBSTRINGS:
            if tok.lower() == root or tok.lower() == mod:
                found.add(tok)

    return sorted(found)


def _validate_source(source: str) -> None:
    """Raise BannedImportError if the generated source contains LLM tokens."""
    if not source or not source.strip():
        raise BannedImportError("proposer returned empty source")
    hits = _scan_banned(source)
    if hits:
        raise BannedImportError(
            f"generated module contains banned LLM token(s) {hits!r}; "
            "codified modules must be deterministic Python only"
        )


# ── Module name + target path derivation ───────────────────────────────────


_SAFE_NAME_PAT = re.compile(r"[^a-z0-9_]")


def _derive_module_name(candidate_pv: str, candidate_sv: str) -> str:
    """`pv.foo.v1` + `sv.bar.v1` → `codified_pv_foo_v1__sv_bar_v1`."""
    a = _SAFE_NAME_PAT.sub("_", candidate_pv.lower())
    b = _SAFE_NAME_PAT.sub("_", candidate_sv.lower())
    return f"codified_{a}__{b}".strip("_")


def _derive_target_path(module_name: str) -> str:
    """Default to `engine/codification/codified/<module>.py`.

    Reviewer can change this before approving; this is the proposed
    location, not the final one. Path is a string for portability.
    """
    return f"engine/codification/codified/{module_name}.py"


# ── Storage ────────────────────────────────────────────────────────────────


def _ensure_proposal_table(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {PROPOSAL_TABLE_NAME} (
            proposal_id            TEXT PRIMARY KEY,
            candidate_id           TEXT NOT NULL,
            module_name            TEXT NOT NULL,
            target_path            TEXT NOT NULL,
            source_code            TEXT NOT NULL,
            signature_match_hash   TEXT NOT NULL,
            prompt_version         TEXT NOT NULL,
            schema_version         TEXT NOT NULL,
            generated_at           TEXT NOT NULL,
            generated_by_provider  TEXT NOT NULL,
            generated_by_model     TEXT NOT NULL,
            ai_audit_id            TEXT NOT NULL,
            md_path                TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_module_proposals_candidate
            ON {PROPOSAL_TABLE_NAME}(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_module_proposals_hash
            ON {PROPOSAL_TABLE_NAME}(signature_match_hash);
    """)


def _get_proposal_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = storage.get_connection(db_path)
    _ensure_proposal_table(conn)
    return conn


def _md_dir() -> Path:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    target = repo_root / PROPOSAL_MD_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_md(proposal: ModuleProposal, md_dir: Optional[Path | str] = None) -> Path:
    base = Path(md_dir) if md_dir else _md_dir()
    base.mkdir(parents=True, exist_ok=True)
    safe_name = _SAFE_NAME_PAT.sub("_", proposal.module_name.lower())
    filename = f"proposal_{safe_name}_{proposal.proposal_id}.md"
    path = base / filename
    body = f"""---
proposal_id: {proposal.proposal_id}
candidate_id: {proposal.candidate_id}
module_name: {proposal.module_name}
target_path: {proposal.target_path}
prompt_version: {proposal.prompt_version}
schema_version: {proposal.schema_version}
generated_at: {proposal.generated_at}
generated_by_provider: {proposal.generated_by_provider}
generated_by_model: {proposal.generated_by_model}
ai_audit_id: {proposal.ai_audit_id}
signature_match_hash: {proposal.signature_match_hash}
penrose_signal: weakens
penrose_dimension: codification
---

# Module Proposal — `{proposal.module_name}`

**Proposal id:** `{proposal.proposal_id}`
**Candidate id:** `{proposal.candidate_id}`
**Target path:** `{proposal.target_path}`
**Generated by:** {proposal.generated_by_provider} / {proposal.generated_by_model}
**Generated at:** {proposal.generated_at}
**AI audit row:** `{proposal.ai_audit_id}`

## Source (SHA-256: `{proposal.signature_match_hash}`)

```python
{proposal.source_code}
```

---

*The codification engine refuses to recognize this proposal if the file
is missing or if `signature_match_hash` no longer matches the
stored `source_code`. The matching hash is the simulator's reference
into this proposal — see `engine/codification/simulator.py`.*
"""
    path.write_text(body, encoding="utf-8")
    return path


def _persist(
    proposal: ModuleProposal,
    *,
    db_path: Optional[str] = None,
    md_dir: Optional[Path | str] = None,
) -> ModuleProposal:
    md_path = _write_md(proposal, md_dir=md_dir)
    proposal.md_path = str(md_path)

    conn = _get_proposal_connection(db_path)
    try:
        conn.execute(
            f"""
            INSERT INTO {PROPOSAL_TABLE_NAME} (
                proposal_id, candidate_id, module_name, target_path,
                source_code, signature_match_hash, prompt_version,
                schema_version, generated_at, generated_by_provider,
                generated_by_model, ai_audit_id, md_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.proposal_id,
                proposal.candidate_id,
                proposal.module_name,
                proposal.target_path,
                proposal.source_code,
                proposal.signature_match_hash,
                proposal.prompt_version,
                proposal.schema_version,
                proposal.generated_at,
                proposal.generated_by_provider,
                proposal.generated_by_model,
                proposal.ai_audit_id,
                proposal.md_path,
            ),
        )
    finally:
        conn.close()
    return proposal


def get_module_proposal(
    proposal_id: str, db_path: Optional[str] = None
) -> Optional[ModuleProposal]:
    conn = _get_proposal_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"SELECT * FROM {PROPOSAL_TABLE_NAME} WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        return ModuleProposal(
            proposal_id=d["proposal_id"],
            candidate_id=d["candidate_id"],
            module_name=d["module_name"],
            target_path=d["target_path"],
            source_code=d["source_code"],
            signature_match_hash=d["signature_match_hash"],
            prompt_version=d["prompt_version"],
            schema_version=d["schema_version"],
            generated_at=d["generated_at"],
            generated_by_provider=d["generated_by_provider"],
            generated_by_model=d["generated_by_model"],
            ai_audit_id=d.get("ai_audit_id") or "",
            md_path=d.get("md_path") or "",
        )
    finally:
        conn.close()


def list_module_proposals_for_candidate(
    candidate_id: str, db_path: Optional[str] = None
) -> list[ModuleProposal]:
    conn = _get_proposal_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM {PROPOSAL_TABLE_NAME} "
            f"WHERE candidate_id = ? ORDER BY generated_at DESC",
            (candidate_id,),
        ).fetchall()
        return [
            ModuleProposal(
                proposal_id=r["proposal_id"],
                candidate_id=r["candidate_id"],
                module_name=r["module_name"],
                target_path=r["target_path"],
                source_code=r["source_code"],
                signature_match_hash=r["signature_match_hash"],
                prompt_version=r["prompt_version"],
                schema_version=r["schema_version"],
                generated_at=r["generated_at"],
                generated_by_provider=r["generated_by_provider"],
                generated_by_model=r["generated_by_model"],
                ai_audit_id=r["ai_audit_id"] or "",
                md_path=r["md_path"] or "",
            )
            for r in rows
        ]
    finally:
        conn.close()


# ── Candidate input contract ───────────────────────────────────────────────


@dataclass
class Candidate:
    """Minimal candidate shape the proposer needs.

    Intentionally separate from `engine.codification.analyzer.Candidate`
    so the proposer can be called against either an analyzer candidate
    or a stored proposal row (both have these fields).
    """
    candidate_id: str
    candidate_pv: str
    candidate_sv: str
    candidate_score: float
    executions: int
    evidence_ids: list[str]
    why: str
    decision_class: str = "new-module"


# ── Public entry point ─────────────────────────────────────────────────────


def propose_python_module(
    candidate: Candidate,
    certificate: Optional[CodificationCertificate] = None,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    db_path: Optional[str] = None,
    md_dir: Optional[Path | str] = None,
    invoke_fn: Any = None,
) -> ModuleProposal:
    """Draft a deterministic Python module for `candidate` via the AI router.

    Args:
      candidate: the readiness-cleared candidate to codify.
      certificate: optional signed CodificationCertificate. When present
        its id appears in the prompt + the persisted artifact. The
        proposer does NOT mint certificates; that stays with
        `approve_and_certify`. The certificate (if any) is binding
        context only.
      provider / model: which LLM to route through. Defaults are the
        canonical proposer model; operator override is allowed for
        staging or rate-limit reasons.
      db_path / md_dir: storage overrides for tests.
      invoke_fn: dependency-injection seam for tests. Defaults to
        `engine.ai_router.invoke`. Test callers pass a stub returning
        an `InvokeResult`-shaped object with `.text` and `.audit_id`.

    Returns ModuleProposal. Raises BannedImportError if the generated
    code references an LLM SDK; raises ValueError on empty / invalid
    candidate input.
    """
    if not candidate.candidate_id:
        raise ValueError("candidate.candidate_id is required")
    if not candidate.candidate_pv or not candidate.candidate_sv:
        raise ValueError("candidate.candidate_pv and candidate_sv are required")

    cert_id = certificate.id if certificate is not None else "(none)"
    decision_class = (
        certificate.decision_class if certificate is not None else candidate.decision_class
    )

    prompt = _build_proposer_prompt(
        candidate_pv=candidate.candidate_pv,
        candidate_sv=candidate.candidate_sv,
        candidate_score=candidate.candidate_score,
        executions=candidate.executions,
        evidence_ids=candidate.evidence_ids,
        certificate_id=cert_id,
        decision_class=decision_class,
        why=candidate.why,
    )

    # CRIT-003 + CRIT-007 — every call routes through ai_router.invoke
    # with provider/model/prompt_version/schema_version populated.
    call = invoke_fn or _ai_invoke
    result = call(
        prompt=prompt,
        provider=provider,
        model=model,
        prompt_version=PROPOSER_PROMPT_VERSION,
        schema_version=PROPOSER_SCHEMA_VERSION,
        caller_engine="codification",
        caller_function="proposer.propose_python_module",
        max_tokens=4096,
        temperature=0.0,
        audit_metadata={
            "candidate_id": candidate.candidate_id,
            "candidate_pv": candidate.candidate_pv,
            "candidate_sv": candidate.candidate_sv,
            "certificate_id": cert_id,
        },
    )

    source = (getattr(result, "text", "") or "").strip()
    _validate_source(source)

    sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    module_name = _derive_module_name(candidate.candidate_pv, candidate.candidate_sv)
    target_path = _derive_target_path(module_name)

    proposal = ModuleProposal(
        candidate_id=candidate.candidate_id,
        module_name=module_name,
        target_path=target_path,
        source_code=source,
        signature_match_hash=sha,
        prompt_version=PROPOSER_PROMPT_VERSION,
        schema_version=PROPOSER_SCHEMA_VERSION,
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        generated_by_provider=getattr(result, "provider_used", provider) or provider,
        generated_by_model=getattr(result, "model_used", model) or model,
        ai_audit_id=getattr(result, "audit_id", "") or "",
    )

    return _persist(proposal, db_path=db_path, md_dir=md_dir)


__all__ = [
    "BannedImportError",
    "Candidate",
    "ModuleProposal",
    "PROPOSER_PROMPT_VERSION",
    "PROPOSER_SCHEMA_VERSION",
    "get_module_proposal",
    "list_module_proposals_for_candidate",
    "propose_python_module",
]
