# BFT State Vector — Variable Reference

> Status: v0 — effective with PR landing this doc.
> Anchors: `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` §5.19 (Business Field Theory);
> CRIT-010 (`state_vector_substitution`); MAJ-016 (`decision_without_state_estimate`).

## What

The canonical 9-variable state vector that BFT (Framework 5.19) operates over.
Each variable is normalized `[0, 1]` and clipped on every update. The set is
binding: substitution, addition, or removal of variables requires an
amendment under triad sign-off (CRIT-010 enforces this).

This document is the operational reference for *how* each variable is
defined, measured, and updated. It is the canonical lookup that
`ppeme/docs/data_mapping.md` and the PPEME `state_estimator` reference.

## Why

§5.19 lists the 9 variables as the binding set but does not operationalize
them. Without per-variable definitions, two implementations of a state
estimator will diverge silently — same name, different math. This doc
forces convergence.

A second purpose: when a drift-sentinel finding mentions `state_vector`,
this doc is the authority readers and downstream LLMs consult.

## Where

- **This file**: `decision-engine/drift_sentinel/specs/bft_state_vector_reference.md`
- **Canonical doctrine**: `decision-engine/drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md` §5.19
- **Engine implementations**: PPEME `api/state_estimator.py`,
  `engine/simulation.py`; consumers in decision-engine, HME, sales-os.

## When

- **Effective**: at this PR's merge
- **Read frequency**: every state estimator invocation (`POST /v1/state/estimate-from-events`)
- **Update cadence**: variable definitions are doctrine; changes are
  amendments. Operational measurement protocols (signal sources, weights)
  may evolve without doctrine amendment but must be versioned by the
  state estimator (see `state_estimator_versioning.md`).

## How — Variable definitions

All variables are normalized to `[0, 1]`. The interpretation:
- `0.0` = absence of the quality
- `0.5` = neutral / typical / median observed
- `1.0` = saturation / extreme presence

### 1. `trust` — confidence that the entity is reliable and honest

- **Operational definition**: probability that the user/org would
  recommend or repeat-purchase given the current relationship state
- **Primary signals**: review ratings, repeat-purchase rate, refund rate
  (negative), support sentiment (NLP), referral count, NPS responses
- **Baseline**: `0.40` (cold-start, no prior interaction)
- **Update characteristics**: slow-moving; accumulates over multiple
  interactions. A single negative event can drop by `~0.15`; building
  back requires multiple positive events.

### 2. `attention` — current cognitive engagement with this entity/offer

- **Operational definition**: probability that the user is actively
  processing information about the entity right now
- **Primary signals**: CTR, dwell time, open rate, page depth, session
  duration, recency of last interaction
- **Baseline**: `0.30`
- **Update characteristics**: fast-moving; decays without reinforcement.
  Decay constant ≈ 0.05/day baseline; faster if competing signals exist.

### 3. `clarity` — extent to which the offer/value is understood

- **Operational definition**: probability that the user could describe
  what the entity offers and why it matters
- **Primary signals**: bounce rate (negative), FAQ usage, support
  confusion tags (negative), form-completion rate, dwell-to-action ratio
- **Baseline**: `0.30`
- **Update characteristics**: medium-moving; benefits from explicit
  education events (demo, walkthrough). Confusion events drop quickly.

### 4. `desire` — wanting / intent to obtain the offered value

- **Operational definition**: probability that the user is currently
  motivated to take the action the entity offers
- **Primary signals**: add-to-cart, saved items, demo requests,
  high-intent page visits (pricing, integrations, case studies)
- **Baseline**: `0.20`
- **Update characteristics**: spiky; can rise rapidly with relevant
  trigger, decays without reinforcement.

### 5. `urgency` — time pressure on the decision

- **Operational definition**: probability that the user perceives a
  cost to delay
- **Primary signals**: time-to-convert (negative correlation),
  deadline response, promo response, page visits to pricing during
  countdown periods
- **Baseline**: `0.10`
- **Update characteristics**: external — driven by promo/deadline
  injection. Pure organic urgency is rare.

### 6. `value` — perceived ROI of the offer

- **Operational definition**: probability that the user believes
  benefit exceeds cost
- **Primary signals**: pricing-page dwell, objection tags (negative),
  discount dependency (negative), willingness-to-pay signals,
  comparison-page visits
- **Baseline**: `0.40`
- **Update characteristics**: anchored by trust + clarity; weak
  movement without those.

### 7. `friction` — operational resistance in the user journey

- **Operational definition**: probability that the user will abandon
  due to process pain
- **Primary signals**: checkout dropoff, form abandonment, payment
  failures, support ticket volume, retry count
- **Baseline**: `0.50` (assume moderate friction by default)
- **Update characteristics**: **NOTE: in conversion equation
  (P(convert) = sigmoid(β₀ + β · S)), friction has a NEGATIVE
  coefficient.** Higher friction reduces conversion. Per §5.19 core
  equations.

### 8. `social_proof` — endorsement signal from the user's reference network

- **Operational definition**: probability that the user perceives
  others-like-them as having endorsed the entity
- **Primary signals**: referral traffic, review-page visits, case-study
  engagement, testimonial dwell, social-link clicks
- **Baseline**: `0.20`
- **Update characteristics**: slow-moving; benefits from explicit
  proof events. Acts as multiplier on trust + value.

### 9. `context_fit` — match between offer and user's situation

- **Operational definition**: probability that the user's
  segment/ICP/use-case aligns with what the entity offers
- **Primary signals**: ICP-segmentation match, geo/industry/use-case
  signals, employer match, persona-attribute match
- **Baseline**: `0.50`
- **Update characteristics**: structural — set by persona attributes;
  changes mostly via persona updates rather than per-interaction.

## Update rule (canonical)

```python
def update_state(S_t: dict, delta_i: dict, noise_sigma: float = 0.01) -> dict:
    """Per-interaction state update — §5.19 canonical equation.
    
    S(t+1) = clip(S(t) + ΔI + ε, 0, 1)
    
    delta_i keys MUST be the canonical 9. Extras are doctrine drift.
    """
    import random
    canonical_keys = {
        "trust", "attention", "clarity", "desire", "urgency",
        "value", "friction", "social_proof", "context_fit",
    }
    assert set(delta_i.keys()) <= canonical_keys, "non-canonical state variable"
    S_next = {}
    for var in canonical_keys:
        eps = random.gauss(0, noise_sigma)
        raw = S_t.get(var, 0.0) + delta_i.get(var, 0.0) + eps
        S_next[var] = max(0.0, min(1.0, raw))
    return S_next
```

## Conversion equation (canonical)

```
P(convert | S) = sigmoid(β₀ + β₁·trust + β₂·attention + β₃·clarity
                      + β₄·desire + β₅·urgency + β₆·value
                      - β₇·friction               # NOTE: negative
                      + β₈·social_proof + β₉·context_fit)
```

Coefficients `β₀..β₉` are decision-class-specific and held in PPEME's
calibration table (see `state_estimator_versioning.md`).

## Cross-reference protocol

When citing a state vector value in a memo, decision certificate, or
artifact:

1. State the value source: `state_vector_at_decision` from a registered
   state estimator (per MAJ-016)
2. State the estimator version: `estimator_version` field
3. State calibration status: `pre_mtheory` flag if the decision class is
   not yet within p50 ≤ 15% variance (per MAJ-018)

Example certificate fragment:

```yaml
state_vector_at_decision:
  trust: 0.62
  attention: 0.51
  clarity: 0.40
  desire: 0.55
  urgency: 0.10
  value: 0.48
  friction: 0.30
  social_proof: 0.22
  context_fit: 0.70
estimator_version: "v0-rules-from-events"
calibration_status: pre_mtheory   # decision class not yet calibrated
```

## Context

- **Substrate dependency**: this state vector is *the* signal SMEN
  (§5.18) provides to BFT (§5.19). Without SMEN, the variables have
  no source; without BFT, the variables have no use.
- **Amendment process**: any change to the 9-variable set is governed
  by `governance_signoff_bootstrap_protocol`; requires Founder + Owner
  + Admin sign-off via amendment file under
  `drift_sentinel/governance/amendments/`
- **Implementation status**: PPEME `state_estimator.py` returns the 9
  variables today via `v0-rules-from-events` (see versioning spec)
