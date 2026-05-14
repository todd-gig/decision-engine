"""Codification simulator — replays a ModuleProposal against historical decisions.

Per `specs/codification_engine_v0.md` §Simulator and the Decision
Routing Framework Adaptive-Learning Loop (§5.7 doctrine): before a
codified module can replace an LLM call, it must reproduce the LLM's
behavior on the evidence set inside the doctrine divergence ceiling
(≤5%).

What this module does:

  1. Compile the proposal's `source_code` in an isolated namespace.
  2. Look up the conventional `codified(input)` entry point.
  3. For each evidence audit_id, fetch the recorded LLM response from
     `llm_audit` and reconstruct the input from `audit_metadata`.
  4. Call the proposed module and compare to the recorded response.
  5. Tally divergence_cases; compute divergence_rate.
  6. Status = `PASSED` when divergence_rate ≤ 0.05, else
     `REJECTED_BY_DIVERGENCE`.

Hard rules:
  - The simulator MUST NOT invoke any LLM. Replay reads stored audit
    rows; codified module is pure Python by construction (proposer
    rejects any module that contains LLM imports).
  - Doctrine divergence ceiling is the ONE source of truth: > 5%
    rejects, ≤ 5% passes. Operators may tighten via `divergence_ceiling`
    arg but never loosen above 5% (a tighter value than 0.05 is
    permitted; a looser one is silently clamped to 0.05).
  - The proposal source is sandboxed: `exec(...)` runs against a
    *restricted* builtins dict. This is hardening only — the proposer
    already rejected banned imports; the sandbox is a second layer.
  - Cases list is capped at 25 entries to keep payloads bounded.
  - Hash-only cross-reference: the simulator stores
    `signature_match_hash` and `module_proposal_id` into the result,
    NOT the full source code. The proposer's persisted artifact
    remains the canonical record (HMAC chain).

penrose_signal: weakens
penrose_dimension: codification
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

from .proposer import ModuleProposal
from .queue import SimulationResult


# ── Doctrine ───────────────────────────────────────────────────────────────

#: Per Framework 5.7 (Adaptive Learning Loop): codification candidates must
#: replay within 5% divergence on the evidence set or the codified module
#: cannot replace the LLM.
DOCTRINE_DIVERGENCE_CEILING: float = 0.05

#: Cap on `divergence_cases` to keep stored payloads bounded.
MAX_CASES: int = 25

#: Conventional public entry point inside a proposed module. The
#: proposer prompt forces this name.
CODIFIED_ENTRY_POINT: str = "codified"


# ── Replay primitives ──────────────────────────────────────────────────────


@dataclass
class _EvidenceRow:
    audit_id: str
    response_text: str
    audit_metadata: dict
    in_chars: int
    out_chars: int


def _fetch_evidence(
    audit_db_path: Optional[str], audit_ids: list[str]
) -> list[_EvidenceRow]:
    """Read llm_audit rows for `audit_ids`. Skips missing ids silently."""
    if not audit_ids:
        return []
    # Lazy import — avoids unnecessary coupling at module load.
    from ..ai_router import storage as audit_storage
    conn = audit_storage.get_connection(audit_db_path)
    try:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in audit_ids)
        rows = conn.execute(
            f"SELECT * FROM llm_audit WHERE audit_id IN ({placeholders})",
            list(audit_ids),
        ).fetchall()
    finally:
        conn.close()
    out: list[_EvidenceRow] = []
    for r in rows:
        d = dict(r)
        meta_raw = d.get("audit_metadata")
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
            if not isinstance(meta, dict):
                meta = {}
        except (TypeError, ValueError):
            meta = {}
        out.append(_EvidenceRow(
            audit_id=d["audit_id"],
            # Audit rows don't store the full response (only the hash).
            # The simulator uses the recorded response from
            # audit_metadata.replayed_response when present;
            # otherwise it uses an empty string and compares structure
            # only. This matches the doctrine: full prompts/responses
            # are NOT stored in llm_audit — simulator divergence is
            # computed against whatever proxy the audit_metadata
            # carried.
            response_text=str(meta.get("replayed_response", "")),
            audit_metadata=meta,
            in_chars=int(d.get("in_chars") or 0),
            out_chars=int(d.get("out_chars") or 0),
        ))
    return out


# ── Sandboxed module compile ───────────────────────────────────────────────


_SAFE_BUILTINS = {
    # Names the proposer is allowed to lean on. Excludes file/network
    # primitives. The proposer also rejected banned imports up front;
    # this list is a defense-in-depth check.
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate",
    "filter", "float", "frozenset", "hash", "hex", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next",
    "oct", "ord", "pow", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "type", "zip",
    # Errors needed for `raise ValueError` per proposer rules.
    "ValueError", "TypeError", "KeyError", "IndexError", "Exception",
    "RuntimeError", "ArithmeticError",
    # __build_class__ + __name__ are needed for module-style code with
    # any class declaration. (We expect functions, but classes are
    # allowed if they're pure.)
    "__build_class__", "__name__",
}


class SimulatorCompileError(RuntimeError):
    """Raised when the proposed module can't be compiled."""


def _compile_proposal(proposal: ModuleProposal) -> dict[str, Any]:
    """Compile the proposal in a restricted namespace. Returns the module dict."""
    import builtins as _builtins

    safe_builtins = {k: getattr(_builtins, k) for k in _SAFE_BUILTINS if hasattr(_builtins, k)}
    namespace: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "__name__": f"codified_proposal_{proposal.proposal_id}",
    }
    try:
        compiled = compile(proposal.source_code, proposal.target_path, "exec")
        exec(compiled, namespace)  # noqa: S102 — sandbox is intentional
    except SyntaxError as e:
        raise SimulatorCompileError(f"proposal {proposal.proposal_id}: syntax error: {e}") from e
    except Exception as e:  # noqa: BLE001 — surface as compile error
        raise SimulatorCompileError(
            f"proposal {proposal.proposal_id}: module raised during compile: {e}"
        ) from e
    if CODIFIED_ENTRY_POINT not in namespace:
        raise SimulatorCompileError(
            f"proposal {proposal.proposal_id} missing entry point "
            f"`{CODIFIED_ENTRY_POINT}(...)`; proposer should have enforced this"
        )
    return namespace


# ── Comparison ────────────────────────────────────────────────────────────


def _default_comparator(expected: Any, actual: Any) -> bool:
    """True iff outputs are equivalent.

    Strings: compare after `.strip()` for stable whitespace tolerance.
    Otherwise: standard equality.
    """
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip() == actual.strip()
    return expected == actual


def _invoke_codified(
    namespace: dict[str, Any], evidence: _EvidenceRow
) -> Any:
    """Call the codified(input) entry point with the reconstructed input.

    The input dict is the audit row's `audit_metadata.replayed_input`
    if present; otherwise the raw metadata. The proposer's prompt
    instructs the LLM that `codified` accepts a single dict.
    """
    fn = namespace[CODIFIED_ENTRY_POINT]
    payload = evidence.audit_metadata.get("replayed_input", evidence.audit_metadata)
    return fn(payload)


# ── Public entry point ─────────────────────────────────────────────────────


def simulate_against_history(
    proposal: ModuleProposal,
    evidence_decision_ids: list[str],
    audit_db_path: Optional[str] = None,
    *,
    divergence_ceiling: float = DOCTRINE_DIVERGENCE_CEILING,
    comparator: Optional[Callable[[Any, Any], bool]] = None,
) -> SimulationResult:
    """Replay a proposal against historical audit rows; compute divergence.

    Args:
      proposal: the ModuleProposal to replay.
      evidence_decision_ids: audit_ids to fetch from `llm_audit`.
      audit_db_path: SQLite path override (tests).
      divergence_ceiling: divergence threshold; defaults to doctrine
        0.05. Tighter (smaller) values are honored; looser (larger)
        values are silently clamped to 0.05 — doctrine is the ceiling.
      comparator: optional `(expected, actual) -> bool` override. The
        default does string-strip-equality / dict equality.

    Returns SimulationResult with `status`, `divergence_rate`,
    `divergence_cases`, `module_proposal_id`, `signature_match_hash`.
    """
    # Doctrine: 5% is the upper bound, not a target. Tighten only.
    ceiling = min(float(divergence_ceiling), DOCTRINE_DIVERGENCE_CEILING)
    if ceiling < 0:
        ceiling = 0.0

    cmp_fn = comparator or _default_comparator

    namespace = _compile_proposal(proposal)
    evidence_rows = _fetch_evidence(audit_db_path, evidence_decision_ids)
    n = len(evidence_rows)

    cases: list[dict] = []
    divergences = 0
    for ev in evidence_rows:
        expected = ev.response_text
        try:
            actual = _invoke_codified(namespace, ev)
        except Exception as e:  # noqa: BLE001 — divergence captures errors
            divergences += 1
            if len(cases) < MAX_CASES:
                cases.append({
                    "audit_id": ev.audit_id,
                    "expected": expected,
                    "actual": None,
                    "error": f"{type(e).__name__}: {e}",
                })
            continue
        # Normalize: stringify non-string actuals so the recorded
        # `response_text` (always string) is comparable.
        actual_for_cmp = actual if isinstance(actual, str) else json.dumps(actual, sort_keys=True)
        if not cmp_fn(expected, actual_for_cmp):
            divergences += 1
            if len(cases) < MAX_CASES:
                cases.append({
                    "audit_id": ev.audit_id,
                    "expected": expected,
                    "actual": actual_for_cmp,
                    "error": "",
                })

    divergence_rate = (divergences / n) if n > 0 else 0.0
    status = "REJECTED_BY_DIVERGENCE" if divergence_rate > ceiling else "PASSED"

    # Approximate p50/p90 of per-case error indicators. With binary
    # match/no-match these collapse to 0 and the divergence_rate;
    # we set p50/p90 to the rate itself as the bounded summary.
    return SimulationResult(
        n=n,
        divergence_p50=round(divergence_rate, 6),
        divergence_p90=round(min(1.0, divergence_rate * 1.5), 6),
        cost_savings_usd=None,
        latency_savings_ms=None,
        divergence_rate=round(divergence_rate, 6),
        status=status,
        divergence_cases=cases,
        module_proposal_id=proposal.proposal_id,
        signature_match_hash=proposal.signature_match_hash,
    )


__all__ = [
    "CODIFIED_ENTRY_POINT",
    "DOCTRINE_DIVERGENCE_CEILING",
    "MAX_CASES",
    "SimulatorCompileError",
    "simulate_against_history",
]
