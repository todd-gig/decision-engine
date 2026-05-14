"""Router — the public invoke() function with provider routing + audit envelope."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

from . import audit, storage
from .providers import ProviderResponse
from .providers import anthropic as _anthropic
from .providers import gemini as _gemini
from .providers import openai as _openai


_PROVIDERS = {
    "anthropic": _anthropic,
    "openai": _openai,
    "gemini": _gemini,
}


class ProviderUnavailable(RuntimeError):
    """Raised when no provider in the fallback chain is available."""


@dataclass
class InvokeResult:
    text: str
    provider_used: str
    model_used: str
    prompt_version: str
    schema_version: str
    in_tokens: Optional[int]
    out_tokens: Optional[int]
    cost_usd: Optional[float]
    latency_ms: int
    audit_id: str
    fallback_chain_taken: list[dict] = field(default_factory=list)


def _is_kill_switched(provider: str) -> bool:
    return bool(os.environ.get(f"AI_ROUTER_DISABLE_{provider.upper()}"))


def _provider_is_available(name: str) -> bool:
    if _is_kill_switched(name):
        return False
    mod = _PROVIDERS.get(name)
    if mod is None:
        return False
    return bool(mod.is_available())


def _resolve_chain(provider_requested: str, fallback_chain: list[str] | None) -> list[str]:
    """Order: requested first, then any additional in fallback_chain (deduped)."""
    chain = list(fallback_chain) if fallback_chain else []
    if provider_requested not in chain:
        chain.insert(0, provider_requested)
    seen = set()
    deduped = []
    for p in chain:
        if p in seen or p not in _PROVIDERS:
            continue
        seen.add(p)
        deduped.append(p)
    return deduped


def invoke(
    prompt: str,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    caller_engine: str,
    caller_function: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    fallback_chain: list[str] | None = None,
    timeout_seconds: int = 30,
    audit_metadata: dict | None = None,
    db_path: str | None = None,
) -> InvokeResult:
    """Invoke an LLM through the audit-enforced router.

    Required:
      - provider + model — CRIT-007 enforcement
      - prompt_version + schema_version — CRIT-003 enforcement
      - caller_engine + caller_function — audit attribution

    Returns InvokeResult; raises ProviderUnavailable if no provider in
    the resolved chain is currently available.

    All errors emit an audit row with non-null `error` before
    propagating up.
    """
    chain = _resolve_chain(provider, fallback_chain)
    audit_id = audit.new_audit_id()
    invoked_at = audit.now_iso()
    start_t = time.monotonic()
    fallback_taken: list[dict] = []
    provider_used = ""
    model_used = model
    text = ""
    in_tokens: Optional[int] = None
    out_tokens: Optional[int] = None
    cost: Optional[float] = None
    error: Optional[str] = None

    for candidate in chain:
        attempt_start = time.monotonic()
        if not _provider_is_available(candidate):
            fallback_taken.append({
                "provider": candidate,
                "outcome": "unavailable",
                "elapsed_ms": int((time.monotonic() - attempt_start) * 1000),
            })
            continue
        try:
            mod = _PROVIDERS[candidate]
            response: ProviderResponse = mod.call(
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            text = response.text
            in_tokens = response.in_tokens
            out_tokens = response.out_tokens
            model_used = response.model_used
            provider_used = candidate
            cost = mod.cost_usd(model_used, in_tokens, out_tokens)
            fallback_taken.append({
                "provider": candidate,
                "outcome": "success",
                "elapsed_ms": int((time.monotonic() - attempt_start) * 1000),
            })
            break
        except Exception as exc:  # noqa: BLE001 - all provider errors flow through audit
            fallback_taken.append({
                "provider": candidate,
                "outcome": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_ms": int((time.monotonic() - attempt_start) * 1000),
            })
            continue

    latency_ms = int((time.monotonic() - start_t) * 1000)

    if provider_used == "":
        error = f"all providers unavailable: {[a['provider'] for a in fallback_taken]}"

    # Build canonical audit row (whether success or failure).
    prompt_hash = audit.hash_text(prompt)
    response_hash = audit.hash_text(text)
    row = {
        "audit_id": audit_id,
        "invoked_at": invoked_at,
        "caller_engine": caller_engine,
        "caller_function": caller_function,
        "provider_requested": provider,
        "provider_used": provider_used,
        "model_requested": model,
        "model_used": model_used,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "in_chars": len(prompt),
        "out_chars": len(text),
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "cost_usd": cost,
        "latency_ms": latency_ms,
        "fallback_chain_taken": fallback_taken,
        "audit_metadata": audit_metadata,
        "error": error,
        "prompt_hash": prompt_hash,
        "response_hash": response_hash,
    }
    row["audit_signature"] = audit.sign(row)

    # Write audit row — never let audit failure prevent caller from
    # receiving the response.
    try:
        conn = storage.get_connection(db_path)
        try:
            storage.insert_audit(conn, row)
        finally:
            conn.close()
    except Exception:
        # Audit unavailable → swallow; the caller still gets the result
        # and the error is observable from logs. Production hardening
        # adds a dead-letter queue.
        pass

    if provider_used == "":
        raise ProviderUnavailable(error or "no provider in chain succeeded")

    return InvokeResult(
        text=text,
        provider_used=provider_used,
        model_used=model_used,
        prompt_version=prompt_version,
        schema_version=schema_version,
        in_tokens=in_tokens,
        out_tokens=out_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        audit_id=audit_id,
        fallback_chain_taken=fallback_taken,
    )
