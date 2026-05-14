# AI Routing / Provider-Abstraction Engine — v0 Spec

> Status: BACKLOG → v0 spec (this PR).
> Anchors: `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` CRIT-003 (prompt
> versioning), CRIT-007 (provider abstraction), §6 (Runtime Governance);
> existing remediation pattern in `decision-engine/engine/_invoke_llm()`,
> `sales-os/app/services/claude_reasoning.py` `_call()`.

## What

A single chokepoint Python package, `engine/ai_router/`, that every
production LLM call in the ecosystem invokes. It enforces:

- `provider` + `model` parameters on every call
- `prompt_version` + `schema_version` audit envelope
- Provider routing (Anthropic / OpenAI / Gemini) with fallback
- Token + cost accounting per call
- Rate-limit + retry orchestration
- Audit log emission (signed, append-only)

The package starts as a sub-package within `decision-engine` (lowest
deployment-cost path); it graduates to a standalone Cloud Run service
when call volume × latency-sensitivity × cross-engine reuse justify the
network hop. Definition of "v0 done" is the sub-package version.

## Why

Tonight's session shipped CRIT-003/007 remediation to sales-os
`claude_reasoning.py` (PR #3) — adding `prompt_version`,
`schema_version`, `provider`, `model` to `_call()`. The same pattern
needs to be in every engine that touches an LLM. Without a shared
abstraction, every engine reinvents the audit envelope, each subtly
different. Drift Sentinel rules CRIT-003 + CRIT-007 fire on any
non-conformant call site — which means every engine ends up paying
the same cost.

A single chokepoint also:
- centralizes provider failover (when Anthropic is down, route to GPT
  with audit trail of the fallback)
- centralizes rate-limit enforcement (per-provider quota, per-engine
  budget)
- centralizes cost accounting (one source of truth for AI spend)
- enables future Codification Engine's call-pattern analysis (it reads
  the audit log)

## Where

- **v0 location**: `decision-engine/engine/ai_router/`
  - `__init__.py` — exports `invoke()`
  - `router.py` — provider routing + fallback
  - `providers/anthropic.py` — Anthropic adapter
  - `providers/openai.py` — OpenAI adapter
  - `providers/gemini.py` — Gemini adapter
  - `audit.py` — audit envelope construction + emission
  - `accounting.py` — token/cost tracking
- **Audit log**: append-only table `llm_audit` in decision-engine's
  Postgres; one row per call
- **Consumed by**: every engine — initial integration list below
- **Standalone service** (v0.5+): graduates when consumed by ≥ 5 engines
  OR call volume > 10K/day, whichever first

## When

- **v0 ship target**: after Codification + Persona Engine specs reach
  parity (currently this PR; sub-package code lands as follow-up)
- **Mandatory adoption deadline**: all production LLM calls in
  decision-engine, sales-os, intelligence-silo, gigaton-engine,
  PPEME via this router by T+30 days post-package-ship
- **Drift-sentinel CRIT-003/007 enforcement**: pre-existing; the router
  is what makes those rules trivially satisfiable everywhere

## How — Public API

```python
from engine.ai_router import invoke, InvokeResult, ProviderUnavailable

result: InvokeResult = invoke(
    prompt="...",
    *,
    provider="anthropic",                  # required: 'anthropic'|'openai'|'gemini'
    model="claude-opus-4-7",               # required
    prompt_version="explain_recs.v1.0",    # required: human-versioned prompt id
    schema_version="coaching_prose.v1",    # required: response schema id
    caller_engine="sales-os",              # required: emitting engine name
    caller_function="explain_recommendations",  # required: function/route slug
    max_tokens=1024,                       # optional
    temperature=0.0,                       # optional
    fallback_chain=["anthropic", "openai"],  # optional: provider failover order
    timeout_seconds=30,                    # optional
    audit_metadata={                       # optional free-form
        "user_id": "...",
        "org_id": "...",
        "decision_id": "DEC-1234",
    },
) -> InvokeResult
```

`InvokeResult`:

```python
@dataclass
class InvokeResult:
    text: str                              # the model output
    provider_used: str                     # which provider actually served (may differ via fallback)
    model_used: str
    prompt_version: str
    schema_version: str
    in_tokens: int
    out_tokens: int
    cost_usd: float                        # provider-billed cost in USD
    latency_ms: int
    audit_id: str                          # UUID for the llm_audit row
    fallback_chain_taken: list[str]        # e.g. ['anthropic'] (no fallback) or ['anthropic', 'openai'] (fallback)
```

## Audit table schema

```sql
CREATE TABLE llm_audit (
    audit_id           UUID PRIMARY KEY,
    invoked_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    caller_engine      TEXT NOT NULL,
    caller_function    TEXT NOT NULL,
    provider_requested TEXT NOT NULL,
    provider_used      TEXT NOT NULL,
    model_requested    TEXT NOT NULL,
    model_used         TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    schema_version     TEXT NOT NULL,
    in_chars           INTEGER NOT NULL,
    out_chars          INTEGER NOT NULL,
    in_tokens          INTEGER,
    out_tokens         INTEGER,
    cost_usd           NUMERIC(10, 6),
    latency_ms         INTEGER NOT NULL,
    fallback_chain_taken JSONB NOT NULL,
    audit_metadata     JSONB,
    error              TEXT,                   -- null on success; provider error class on failure
    prompt_hash        TEXT NOT NULL,          -- SHA-256 of prompt; full prompt NOT stored
    response_hash      TEXT NOT NULL,          -- SHA-256 of response
    audit_signature    TEXT NOT NULL           -- HMAC-SHA256 over canonicalized row
);
CREATE INDEX idx_llm_audit_caller ON llm_audit(caller_engine, caller_function, invoked_at);
CREATE INDEX idx_llm_audit_pv ON llm_audit(prompt_version, schema_version);
CREATE INDEX idx_llm_audit_cost ON llm_audit(invoked_at) WHERE cost_usd IS NOT NULL;
```

Full prompts + responses are NOT stored — privacy + storage cost.
Hashes provide tamper-evidence. Full bodies can be retrieved from
provider's own logs using the audit row's identifiers.

## Provider routing logic

```python
def route(provider_requested, fallback_chain):
    """Returns the first provider available, with fallback."""
    chain = fallback_chain or [provider_requested]
    if provider_requested not in chain:
        chain.insert(0, provider_requested)
    for provider in chain:
        if is_provider_available(provider):
            return provider
    raise ProviderUnavailable(f"All providers in {chain} unavailable")
```

Provider availability checked via:
- Recent error rate (>50% errors in last 60s → unavailable)
- Rate-limit window (per-provider concurrent-request semaphore)
- Explicit kill-switch env var (`AI_ROUTER_DISABLE_<PROVIDER>=1`)

## Cost accounting

Each provider's pricing table is held in `providers/<name>.py`:

```python
PRICING = {
    "claude-opus-4-7":     {"in_per_1k": 0.015, "out_per_1k": 0.075},
    "claude-sonnet-4-6":   {"in_per_1k": 0.003, "out_per_1k": 0.015},
    "gpt-4-turbo":         {"in_per_1k": 0.010, "out_per_1k": 0.030},
    # ...
}
```

Pricing tables are versioned; tests assert non-decreasing prices (we
never silently undercharge against the audit log). Cost is computed at
invoke-time and stored on the audit row.

## Failover audit trail

When a fallback triggers, the audit row records the full chain
attempted:

```json
"fallback_chain_taken": [
  {"provider": "anthropic", "outcome": "rate_limited", "elapsed_ms": 250},
  {"provider": "openai", "outcome": "success", "elapsed_ms": 1100}
]
```

This is critical: if a Codification Engine analysis later asks "did
Anthropic outage on 2026-05-13 affect outcome X?" the audit log can
answer authoritatively.

## v0 → v0.5 graduation criteria

The package promotes from in-process sub-package of decision-engine to
standalone Cloud Run service when ANY of:

1. ≥ 5 engines integrated (cross-import friction outweighs network hop)
2. > 10K calls/day across ecosystem (deployment isolation benefit)
3. Provider-failover decision latency starts impacting calling engine
   SLO (split the deploy)
4. A non-decision-engine team needs to deploy router changes
   independent of decision-engine release cycle

## Integration plan (engines to migrate)

| engine | current LLM surface | migration size |
|---|---|---|
| decision-engine | `engine/_invoke_llm()` (already has the envelope) | trivial |
| sales-os | `app/services/claude_reasoning.py` `_call()` (PR #3, just shipped) | small |
| intelligence-silo | TBD | medium |
| gigaton-engine | pricing reasoning calls | small |
| ppeme | none yet | n/a |
| HME | initiative reasoning, coaching prose | medium |

## Context

- **CRIT-003 + CRIT-007 enforcement**: this package is the answer to
  both. With it adopted, the rules become trivially satisfied
  ecosystem-wide.
- **Codification Engine dependency**: Codification reads the audit
  log to identify codification candidates (prompts that are
  high-volume, low-variance, deterministic → promote to Python rules).
  Without the audit table, Codification has no signal.
- **OVS-Calibration Engine dependency**: ditto for decision attribution.
- **SMEN substrate**: the audit log is one of SMEN's read surfaces
  (read-only from peer engines).
- **Implementation note**: existing per-engine `_call()` / `_invoke_llm()`
  patterns become thin proxies that forward to `ai_router.invoke()` —
  no breaking change for call sites.
