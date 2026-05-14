# Human Override Engine — v0 Spec

> Status: BACKLOG → v0 spec (this PR).
> Anchors: `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` §1.1 (Human Override
> Non-Negotiable); §5.7 (Adaptive Learning Loop); CRIT-001
> (`automation_without_human_override`); CRIT-009
> (`irreversible_without_mandatory_human`).
> Depends on: AI Routing Engine v0 (audit log), OVS-Calibration v0
> (3× outcome weighting), Codification Engine v0 (exception-case ingest).

## What

A peer engine, `human-override-engine`, that captures every instance of
a human reversing, modifying, or rejecting an engine decision after it
was made. Each override is treated as a high-signal outcome (3× weight
in OVS-Calibration) and as an exception case for Codification Engine
to analyze.

Overrides are not failures — they're the canonical mechanism by which
human judgment teaches the system. CRIT-001 is the doctrine; this engine
is the implementation.

## Why

Today, human overrides happen through ad-hoc paths:
- User edits a decision-engine certificate
- Operator marks a recommendation as "wrong" in sales-os UI
- Founder manually intervenes in a state machine transition

Each path stores override locally; no engine reads cross-cutting override
signal. As a result:
1. OVS-Calibration treats overrides as just-another-outcome (1× weight)
   when they should be 3× — they're explicit instructor signal
2. Codification Engine doesn't see the exception space; proposals don't
   anticipate the override patterns
3. Drift Sentinel can't grade "override hot spots" — engines with
   high override rates are silently broken

Human Override Engine centralizes the capture; downstream engines
consume canonically.

## Where

- **v0 location**: sub-package `decision-engine/engine/human_override/`
  - `ingestion.py` — capture API
  - `classification.py` — override type taxonomy
  - `weights.py` — 3× outcome attribution writer
  - `exceptions.py` — exception-case writer (for Codification)
- **Storage**: `human_overrides` Postgres table (decision-engine DB)
- **Standalone service** (v0.5+): when ≥ 3 engines emit overrides
  AND classification logic warrants independent versioning

## When

- **v0 ship target**: T+30 days after Codification + OVS-Calibration v0
  ship (it depends on both)
- **Mandatory adoption**: any engine surfacing an override path must
  emit to this engine within T+45 days post-ship

## How — Override types (taxonomy)

| type | meaning | OVS weight | Codification action |
|---|---|---|---|
| `reversal` | human reverses an auto-executed decision | 3× | open exception case immediately |
| `modification` | human modifies decision params before execution | 2× | open exception case if pattern recurs |
| `rejection` | human rejects an engine recommendation | 2× | open exception case after N>5 same-type rejections |
| `silent_inaction` | engine recommended X; user did Y (different) | 1.5× | trend signal; no immediate case |
| `repeated_override` | same user overrides same engine ≥ 3× in 30d | 4× | escalate to Founder UI for engine review |

## Ingest API

```http
POST /v1/overrides/record
Content-Type: application/json

{
  "override_id": "uuid-v4",
  "decision_id": "DEC-1234",
  "decision_certificate_id": "EC-1234",
  "override_type": "reversal",
  "overridden_by_user_id": "uuid",
  "overridden_at": "2026-05-13T20:00:00Z",
  "source_engine": "sales-os",
  "surface": "operator_dashboard:opportunity_detail",
  "original_action": "auto_send_proposal",
  "override_action": "hold_for_review",
  "user_reasoning": "Proposal pricing exceeded client's stated budget",  // user-typed WHY
  "freeform_metadata": { ... }
}
```

Response: `202 Accepted` with `override_id`.

## Classification

Override events are auto-classified for downstream consumers:

```python
def classify_override(event: OverrideEvent) -> OverrideClassification:
    """Returns the canonical type + downstream weights."""
    if event.override_type == 'reversal':
        # Reversal of an already-executed decision = highest signal
        return OverrideClassification(
            type='reversal',
            ovs_weight=3.0,
            codification_action='open_exception_case_now',
        )
    elif _is_repeated(event):
        return OverrideClassification(
            type='repeated_override',
            ovs_weight=4.0,
            codification_action='escalate_to_founder',
        )
    # ... etc per taxonomy table
```

## Override storage schema

```sql
CREATE TABLE human_overrides (
    override_id           UUID PRIMARY KEY,
    decision_id           TEXT,
    decision_certificate_id TEXT,
    override_type         TEXT NOT NULL,
    overridden_by_user_id UUID NOT NULL,
    overridden_at         TIMESTAMPTZ NOT NULL,
    source_engine         TEXT NOT NULL,
    surface               TEXT NOT NULL,
    original_action       TEXT NOT NULL,
    override_action       TEXT NOT NULL,
    user_reasoning        TEXT,                  -- always-record-WHY
    freeform_metadata     JSONB,
    classification        JSONB NOT NULL,        -- the auto-classification output
    sent_to_ovs_at        TIMESTAMPTZ,
    sent_to_codification_at TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_overrides_decision ON human_overrides(decision_id);
CREATE INDEX idx_overrides_user ON human_overrides(overridden_by_user_id, overridden_at);
CREATE INDEX idx_overrides_engine ON human_overrides(source_engine, overridden_at);
```

## OVS-Calibration write-through

Every override emits a synthetic outcome to OVS:

```python
ovs.ingest_outcome({
    "decision_id": override.decision_id,
    "outcome_metric": "human_override",
    "outcome_value": override.classification.ovs_weight,
    "outcome_unit": "weight_multiplier",
    "source_engine": "human-override-engine",
    "why": f"Override type={override.override_type}: {override.user_reasoning}",
})
```

OVS treats this as a 3× (or N×) signal weighting in its variance
computation — meaning the engine learns *fastest* from cases humans
disagreed with.

## Codification write-through

Override events also write to a Codification exception-case queue:

```python
codification.open_exception_case({
    "trigger_override_id": override.override_id,
    "trigger_decision_id": override.decision_id,
    "pattern_class": override.classification.type,
    "exception_signal": {
        "original_action": override.original_action,
        "human_action": override.override_action,
        "user_reasoning": override.user_reasoning,
        "audit_metadata": ... # from llm_audit if LLM-influenced
    },
    "why": "Human override — exception worth codifying",
})
```

When Codification proposes a Python codification, it INCLUDES these
exception cases as test inputs — so generated Python handles the
override case correctly.

## Founder escalation

When `override_type == 'repeated_override'`, Human Override Engine
notifies the Founder UI panel:

```json
{
  "type": "repeated_override_escalation",
  "user_id": "...",
  "engine": "sales-os",
  "n_overrides_in_30d": 7,
  "pattern_summary": "User repeatedly holds proposals when client budget < pricing recommendation",
  "suggested_action": "Open Decision Record to review sales-os pricing decision class threshold",
  "evidence_refs": ["override-uuid-1", "override-uuid-2", "..."]
}
```

Founder reviews; opens Decision Record if needed; engine adjusts.

## Anti-pattern guards

This engine MUST NOT:
- Replace human override with auto-correction (CRIT-001 violation)
- Throttle override capture (every override matters; if storage fills,
  surface a warning, don't drop)
- Modify the override event itself; classification is auxiliary, the
  original is immutable

## v0 → v0.5 graduation

Standalone service when:
1. ≥ 3 engines emit overrides
2. Classification logic version-bumps independently of decision-engine
3. Founder UI panel reads escalations at high frequency (> 10/day)

## Context

- **CRIT-001 anchor**: this engine is the canonical capture mechanism
  for the Human Override Non-Negotiable
- **Framework 5.7 anchor**: closes the Learning Loop with explicit
  signal weighting; 3× weight is the canonical value but tunable per
  override taxonomy
- **OVS-Calibration coupling**: overrides feed calibration; without
  OVS, override signal sits in the table unused
- **Codification coupling**: exception cases prevent codification from
  proposing rules that ignore the override pattern
- **Memory cross-ref**: `human_override_engine_spec.md` (older entry,
  replaced + extended by this doc)
- **Substrate**: SMEN (§5.18) provides the cross-engine read surface
  so override-aware decisions are possible in real time
