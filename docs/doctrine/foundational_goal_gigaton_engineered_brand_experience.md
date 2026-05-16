---
name: Foundational Goal — Gigaton Engineered Brand Experience (PPIM doctrine)
description: The single-sentence purpose every action across every entity must serve. "Facilitate predictably profitable interaction management of a gigaton engineered brand experience." Established 2026-05-16. Anchors goal→action chain at every layer.
type: feedback
established: 2026-05-16
status: ACTIVE — load-bearing on every decision artifact
originSessionId: 46573597-53b1-49ab-b43d-26dc9f6ff65e
---
# Foundational Goal — PPIM doctrine

## The sentence

> **Facilitate predictably profitable interaction management of a gigaton engineered brand experience.**

Abbreviation: **PPIM** (Predictably Profitable Interaction Management).

## Parsed

| Word | What it commits us to |
|---|---|
| **Facilitate** | The platform's role is enablement — not autonomous action without the human in the loop. Every system is a co-pilot for a human owner. |
| **Predictably** | Outcomes must be FORECASTABLE within bounded variance. Random or surprising results = a failure of the system, not the user. Pairs with PPEME (Predictably Profitable Experience Management Engine) + Master Calculator. |
| **Profitable** | Every interaction has unit economics that pencil. Revenue per touch − cost per touch > 0 in steady state. Loss-leader interactions exist but must be deliberate, attributed, and bounded. |
| **Interaction** | The ATOMIC unit. Every human-to-human, human-to-system, system-to-system event is an interaction with attribution + economics. Maps to OutcomeEvent in OVS-Calibration. |
| **Management** | Active stewardship — interactions are designed, instrumented, measured, and improved. Not laissez-faire. |
| **Gigaton engineered** | Engineered means deliberate + reproducible + governed. "Gigaton" stamps the brand commitment — every experience must reflect Gigaton's standard of intelligent, methodology-driven operation. |
| **Brand experience** | The OUTPUT. Every channel, every touchpoint, every artifact contributes to a coherent brand experience the customer perceives as differentiated, predictable, and worth paying for. |

## How to apply (every action checked against)

1. **Does this interaction have a known economics signature?** If you cannot answer "what does this cost us + what does it produce" → either measure it (instrument first) or kill it.
2. **Is the outcome predictable within bounds?** If variance is wider than the value spread, the system is leaking — either narrow the variance (better data + selection) or accept the loss explicitly.
3. **Is profit the natural consequence of value delivered, or extractive?** Profit must come from value delivered, not from friction, opacity, or coercion. The brand stops being defensible the moment that flips.
4. **Does this advance the brand experience?** Or is it a regression — a moment where the customer realizes "this isn't different from the alternative"?
5. **Is this engineered or improvised?** Improvised is fine for v0 discovery. But anything that's run twice should be engineered the second time.

## How to enforce (system-level)

- Every new code path / engine / surface declares its **PPIM signature** in module header:
  - `ppim_interaction:` what interaction class does this serve (booking, support, marketing-touch, etc.)
  - `ppim_economics:` cost_estimate_per_call (USD or staff-minutes) + revenue_attribution_path (which Penrose metric does it move)
  - `ppim_predictability:` what variance bound is acceptable
  - `ppim_brand_dimension:` which brand-experience axis it touches
- **Drift Sentinel rule** (proposed, to add): scan engines + services for `ppim_*` declarations. Any module that calls an external service or charges money without a PPIM signature = MAJ-severity drift.

## Why this is foundational, not aspirational

Every prior memory in this directory describes capabilities. This memory describes WHY any of those capabilities matter. Without the PPIM commitment:
- The Penrose Scoreboard is just metrics → useless without an outcome attribution loop
- The LLM cost log is just spend → useless without a revenue side
- The intelligence pipeline is just routing → useless without measuring whether the routed answer increased customer LTV
- The brand surfaces (UI, chat, emails, listings) are just channels → useless without coherence

Every memory below this line should be read as "X exists because PPIM requires Y." When that chain is unclear for a given memory, the memory needs revision.

## Concrete dimensions every Gigaton brand interaction tracks

Atomic schema every system that touches a customer must emit:

```
interaction_id      uuid
ts                  timestamptz
brand_id            (Carmen Beach Properties | Liquefex | Ti Solutions | InContekst | Gigaton-direct)
customer_id         (operator | guest | prospect | partner)
channel             (see channels_map.csv — Airbnb, Vrbo, direct-web, SMS, email, etc.)
sub_channel         (Airbnb Plus, Vrbo Premier, Instagram-DM-organic, etc.)
interaction_class   (awareness | inquiry | quote | booking | pre-arrival | check-in |
                     during-stay | check-out | post-stay | review | repeat | referral |
                     refund | dispute | support | upsell | partnership)
cost_minutes        decimal (staff time)
cost_usd            decimal (platform fees, ad spend, infra cost, LLM cost)
revenue_attribution decimal (direct revenue OR fractional credit toward later revenue)
predictability_score 0-1 (system confidence the outcome will fall within forecast)
brand_dimension     (responsiveness | quality | personalization | resolution | upgrade)
outcome_event_id    fk -> outcome_records (for OVS-Calibration replay)
penrose_signal      strengthens|weakens (which way did this interaction push the falsification scoreboard)
```

The current Carmen Beach booking-revenue backfill (PR cli.py `backfill-carmen-beach`) seeds only the BOOKING class. PPIM requires the rest of the lifecycle to also instrument — that's the gap the platform map you shared today only 15% addresses.

## Context

- Established by Todd 2026-05-16 alongside the STVR Platform_Map starter sheet.
- Paired with [PPEME memory](predictably_profitable_experience_management_engine.md) — PPEME is the engine that operationalizes PPIM.
- Paired with [Penrose Falsification Doctrine](penrose_falsification_doctrine.md) — Penrose is how we know whether PPIM is actually working.
- Paired with [Engine Artifact Doctrine](engine_artifact_doctrine.md) — every artifact must complete the equation `f(user, org, platform.intelligence, resources.available)` IN SERVICE OF PPIM.
- Anti-pattern: any system optimized for short-term revenue at cost of brand experience violates the doctrine. Any system optimized for brand experience at sustained loss also violates (must be a bounded, deliberate loss-leader, not unbounded).
