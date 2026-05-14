# OVS-Calibration Engine — v0 Spec

> Status: BACKLOG → v0 spec (this PR).
> Anchors: `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` Framework 5.7
> (Adaptive Learning Loop); §5.19 BFT calibration requirement.
> Depends on: AI Routing Engine v0 (audit log); HME (outcomes signal);
> PPEME state_estimator (predicted state); decision-engine certificates.

## What

The Outcome Validation + Scoring (OVS) Calibration Engine ingests
cross-entity outcome signal — what *actually happened* after each
decision — and writes calibration weights back into the engines that
need them. Specifically:

- PPEME `estimator_calibration` table (per `state_estimator_versioning.md`)
- decision-engine MASTER_FIRST_PRINCIPLES weight constants
- AI Routing Engine prompt-version effectiveness scores

Without OVS, every engine recalibrates in isolation. With OVS, the
ecosystem has a closed Learning Loop (Framework 5.7).

## Why

Framework 5.7 (Adaptive Learning Loop) is canonical doctrine but
currently only manifests as ad-hoc per-engine outcome ingestion. PPEME
defines its own outcome contract; decision-engine has its own
`outcomes/record` endpoint; sales-os tracks closed-won-revenue
separately. The data sits in silos.

OVS unifies the ingest, attributes outcomes back to decisions via
certificate-id chains, and writes attribution-weighted updates back to
the engines that learn.

§5.19 BFT explicitly depends on this: production-grade status for a
decision class requires `p50 ≤ 15%` variance over a 30-day window —
that variance is computed by OVS reading observed-vs-predicted.

## Where

- **v0 location**: sub-package `decision-engine/engine/ovs/`
  - `ingestion.py` — outcome event ingestion API
  - `attribution.py` — decision attribution chain walker
  - `weighting.py` — outcome → weight delta calculation
  - `writers/ppeme.py` — writes to PPEME `estimator_calibration`
  - `writers/decision_engine.py` — writes weight updates back
  - `writers/ai_router.py` — writes prompt-version effectiveness
- **Outcome ingest API**: `POST /v1/outcomes/ingest` (decision-engine)
- **Standalone service** (v0.5+): graduates when reading volumes
  cross-region or multi-tenant load requires dedicated scaling

## When

- **v0 ship target**: after AI Routing Engine v0 ships (depends on
  audit log)
- **Mandatory adoption**: any engine emitting `outcome` events must
  route through OVS by T+45 days post-ship
- **Drift activation**: MAJ-018 (uncalibrated forecast as authority)
  becomes enforceable once OVS produces variance-tracking signal

## How — Ingest API

```http
POST /v1/outcomes/ingest
Content-Type: application/json

{
  "outcome_id": "uuid-v4",
  "decision_id": "DEC-1234",                  # optional but strongly preferred
  "decision_certificate_id": "EC-1234",       # optional; falls back to decision_id lookup
  "subject_kind": "user",                     # 'user'|'org'|'opportunity'|'initiative'|'campaign'
  "subject_id": "user-uuid-or-equivalent",
  "outcome_metric": "revenue_usd_30d",        # standard metric name
  "outcome_value": 280.0,
  "outcome_unit": "usd",
  "observed_at": "2026-05-12T15:00:00Z",
  "observation_window_start": "2026-04-12T00:00:00Z",
  "observation_window_end": "2026-05-12T00:00:00Z",
  "source_engine": "sales-os",
  "why": "Closed-won opportunity from sales-os pipeline",
  "metadata": {
    "opportunity_id": "...",
    "stage_at_observation": "closed_won"
  }
}
```

Response: `202 Accepted` with `outcome_id` echoed. Idempotent on `outcome_id`.

## Attribution chain walker

For each ingested outcome, OVS attempts to trace back through the
decision-engine certificate chain:

```
outcome (subject=user-X, metric=revenue_30d=$280)
   ↑
decision_id=DEC-1234 → EC certificate
   ↑
inputs: state_vector_at_decision (from PPEME estimator v0-rules-from-events)
        forecast: {p10: 100, p50: 250, p90: 600}
        decision_class: D3
        prompt_version (if LLM-influenced): explain_recs.v1.0
```

Attribution outputs per-input:

```python
{
  "decision_id": "DEC-1234",
  "decision_class": "D3",
  "observed": 280.0,
  "predicted_p50": 250.0,
  "absolute_error": 30.0,
  "variance_p50": 30.0 / 280.0,  # ≈ 0.107
  "estimator_version": "v0-rules-from-events",
  "prompt_versions_used": ["explain_recs.v1.0"],
  "attributable_share": 1.0,                   # full attribution
}
```

When attribution shares < 1.0 (e.g., multiple decisions contributed),
weights are distributed proportionally to certificate timing recency
and intervention magnitude.

## Weighting + write-back

After attribution, OVS writes per-target:

### To PPEME `estimator_calibration`

```python
upsert(
    decision_class="D3",
    estimator_version="v0-rules-from-events",
    window_end=now(),
    sample_size += 1,
    predicted_p50_running_mean += ...,
    observed_p50_running_mean += ...,
    variance_p50 = abs(observed - predicted) / max(observed, predicted),
    # status transitions per state_estimator_versioning.md lifecycle
)
```

### To decision-engine weight updates

```python
# Per-gate effectiveness: did this gate's pass/fail correlate with outcome?
# Per-trust-tier accuracy: do T3-certified decisions outperform T2?
# Records: a Decision Record (DR) is opened when a weight bump would
# change a threshold by > 5%; never auto-applies without human approval.
```

Weight write-backs to decision-engine are gated behind a human-approval
queue. OVS proposes; founder/owner approves. This is canonical-doctrine
protection — weights are doctrine.

### To AI Routing Engine

```python
# prompt_version effectiveness = decision_outcomes_using_version / total
# When a prompt_version's effectiveness drops > 10% relative to its
# replacement candidate, OVS opens an analysis for Codification Engine
# (which may then promote the deterministic path to Python).
```

## Variance computation (canonical)

```python
def variance(observed: float, predicted: float) -> float:
    """Relative variance per §5.19 falsifiability threshold."""
    if observed == 0 and predicted == 0:
        return 0.0
    return abs(observed - predicted) / max(abs(observed), abs(predicted))
```

p50 variance for a decision class = median of per-outcome variance
values over the rolling 30-day window. Falsifiability threshold:
`p50 ≤ 0.15` sustained for 7 days promotes status to `calibrated`.

## Failure modes + recovery

- **Outcome ingest before decision exists**: queued in
  `outcomes_pending` table; replays attribution every hour for 30 days
  then archived as orphan
- **Attribution chain broken** (decision_certificate_id null and
  decision_id unknown): outcome stored, attribution marked
  `unattributable`, surfaced in weekly report for human triage
- **Multiple attribution candidates**: weights distributed by recency
  + intervention magnitude (default policy); per-engine policy override
  via outcome metadata

## v0 → v0.5 graduation

OVS promotes from sub-package to standalone service when:

1. Outcome ingest > 5K events/day
2. ≥ 3 engines depend on OVS write-backs for calibration
3. Attribution chain walks start to constitute majority of
   decision-engine's read load

## Context

- **Framework 5.7 anchor**: OVS is the concrete instantiation of the
  Adaptive Learning Loop; promotion to canonical doctrine confirmed
  2026-01-08
- **PPEME calibration dependency**: PPEME's
  `state_estimator_versioning.md` lifecycle states (`pre_mtheory →
  calibrated → drifted`) are driven by OVS's variance computation
- **Human-in-loop guard**: weight updates to decision-engine are
  proposed by OVS, approved by humans. OVS never silently moves the
  goalposts.
- **Substrate dependency**: SMEN (§5.18) provides the read substrate
  for cross-engine outcome attribution
- **Memory cross-ref**: `outcome_calibration_engine_spec.md` (older
  memory entry — this doc replaces and extends it)
