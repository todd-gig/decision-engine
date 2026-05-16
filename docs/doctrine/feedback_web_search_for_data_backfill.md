---
name: Web-search to backfill missing data (STVR + adjacent domains)
description: When any data field is missing, stale, or has only operator-supplied seed values, search the web for authoritative public sources (vendor docs, industry stats, government data, peer-reviewed) and cite. Apply to STVR vendor commissions, Mexican tax rates, market benchmarks, and any field where a defensible public number exists. Established 2026-05-16.
type: feedback
established: 2026-05-16
originSessionId: 46573597-53b1-49ab-b43d-26dc9f6ff65e
---
# Web-search to backfill any missing data

When building a data model and a field is empty / stale / a placeholder / "TODO from operator," default to **searching the web for the authoritative public source first** before asking the user.

## Why

- Operator time is the constraint — not platform speed. A 60-second web search saves 30 minutes of "what's Airbnb's commission rate?" back-and-forth.
- Public data is auditable. Operator-supplied values without a source become untrustable over time. Web-sourced fields carry a citation.
- Many fields ARE in the public record (vendor pricing, government tax rates, industry surveys, market benchmarks) — using them is the difference between a credible data model and one that looks like guesses.
- The PPIM doctrine demands "every value has a counterparty" — a citation IS the counterparty for public data.

## When to apply

- ✅ Vendor pricing / commissions / fee structures
- ✅ Government regulations / tax rates / compliance windows
- ✅ Industry benchmarks (e.g., average STVR occupancy, conversion rates, lead times)
- ✅ Platform API field schemas / webhook payload shapes
- ✅ Demographics / market segmentation when the segments are public
- ✅ Channel taxonomies (e.g., the canonical OTA list)
- ❌ Operator-private data (their specific revenue, their guests, their unit-level pricing) — that stays with the operator
- ❌ Strategy decisions (which channels to invest in) — surface options, let operator choose
- ❌ Anything where the public version is materially wrong and the operator's local truth differs

## How to apply

1. **Identify the gap** — what field is unknown / stale / "TODO"?
2. **Search** — vendor docs, industry reports, government sites, reputable news
3. **Capture both the value and the source URL + date observed** so it can be re-verified or refreshed later
4. **Mark "verified web 2026-MM-DD" in the data model's metadata** alongside the value
5. **Flag conflicts** — if web data conflicts with operator-supplied, surface both and ask which to trust

## Anti-pattern

- Asking the operator for data the web obviously has (commission rates, tax rates, currency conversions)
- Citing "general knowledge" without a URL — citation IS the credibility marker
- Letting stale web data drift — every field should carry an "observed at" timestamp; re-verify when stale-by-policy

## Connection to PPIM

PPIM requires every value to have a counterparty. For web-sourced fields, the counterparty is the public source. The doctrine of "no synthesized data" (Non-Negotiable #6) does NOT forbid citing public data; it forbids inventing facts the system has no evidence for. Public sourcing is the opposite of synthesis.

## Apply to STVR + Carmen Beach concretely

For the Playa STVR Dashboard auxiliary sheets being drafted:

- **Platform commissions** → search each OTA's published rates; cross-check with their merchant agreement docs
- **Mexican STVR tax structure** → search SAT, INEGI, Quintana Roo state lodging tax; verify ISR / IVA / 3% state lodging
- **Booking lead times** → industry surveys (AirDNA, Beyond Pricing reports, Skift/STR data)
- **Cancellation rate baselines** → vendor docs + industry averages
- **Channel-specific guest demographics** → AirDNA, Vrbo annual reports, Booking.com market data
- **Average review-to-booking conversion lift** → AirDNA, industry surveys
- **Currency conversion** → live rate at observation time for revenue normalization

## Context

- Paired with [foundational_goal_gigaton_engineered_brand_experience](foundational_goal_gigaton_engineered_brand_experience.md) — public sourcing makes "predictably profitable" empirically grounded, not aspirational
- Paired with [feedback_auto_complete_preventive_tasks](feedback_auto_complete_preventive_tasks.md) — web research IS a preventive task; auto-execute
- Anti-pattern alert: drift-sentinel rule candidate — flag any field in a public-source-eligible table that lacks a citation column populated within the last N days
