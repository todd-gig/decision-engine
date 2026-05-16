---
name: Foundational Doctrine — Modular Replication via Input Substitution
description: Every solution must be (1) catalogued + multi-axis tagged, (2) accessible across ALL integrated systems, (3) modular so elements compose into alt-systems for alt-user/alt-org, (4) replicable automatically by swapping inputs. Established 2026-05-16. Anchors how every dataset + engine + capability is built going forward.
type: feedback
established: 2026-05-16
status: ACTIVE — foundational; load alongside PPIM
serves: foundational_goal_gigaton_engineered_brand_experience (PPIM)
originSessionId: 46573597-53b1-49ab-b43d-26dc9f6ff65e
---
# Modular Replication via Input Substitution

## The principle

> Engineer every solution so it can be **easily replicated with inputs automatically**.

Each capability we build for one operator (Carmen Beach, Liquefex, Ti Solutions, InContekst, etc.) must be authored so that the SAME ENGINE serves a different operator by changing only the inputs — never the engine itself.

A solution that requires code changes to serve a different user is not modular. It is bespoke. Bespoke does not produce log-function improvement (per [Gigent Value Matrix](gigent_value_matrix_doctrine.md)) — modular does.

## What "modular replication via input substitution" requires

### 1. Multi-axis tagging on every datum

Every row in every table (Economics, Market_Benchmarks, Platform_Map, Connectors_Catalog, Brand_Dimensions, Vendor_Pricing, Customer_Segments, Tax_Regimes, etc.) carries tags across multiple orthogonal axes:

| Axis | Examples |
|---|---|
| **Industry vertical** | `real_estate`, `hospitality`, `tourism`, `e_commerce`, `legal_services`, `wealth_management` |
| **Sub-vertical** | `short_term_rental`, `vacation_rental`, `hotel`, `executive_housing`, `corporate_relocation` |
| **Geography** | `country:mexico`, `state:quintana_roo`, `city:playa_del_carmen`, `region:latam`, `region:caribbean` |
| **Regulatory regime** | `mx_sat`, `mx_isr`, `mx_iva`, `mx_quintana_roo_ish`, `us_irs`, `eu_vat` |
| **Customer segment** | `tourist`, `business_traveler`, `digital_nomad`, `family`, `couples`, `solo`, `group` |
| **Lifecycle stage** | `awareness`, `consideration`, `booking`, `pre_arrival`, `during_stay`, `post_stay`, `repeat`, `referral` |
| **Time validity** | `effective_from:2026-01-01`, `effective_until:null` |
| **Source provenance** | `web_verified_2026_05_16`, `operator_supplied`, `synthetic_via_master_calculator`, `cited:<url>` |
| **Modality** | `quantitative`, `qualitative`, `qualitative_inferred`, `behavioral_observed` |

A row tagged `[hospitality, short_term_rental, country:mexico, state:quintana_roo, ota_commission, effective_from:2026-01-01]` is automatically discoverable by:
- Any system filtering on `hospitality` (broadest)
- Any system filtering on `short_term_rental` (narrower)
- A Spain-Costa-Brava-STVR operator's view that filters by sub-vertical and SWAPS in their own geography/regulatory tags

### 2. Tags are JSONB / flexible — never hardcoded enums (except for stable doctrine)

The `brand_dimensions` table from PR #218 already uses this pattern (data-driven, extensible). Apply the same shape to:
- `connectors_catalog.tags` — JSONB column (extends the existing `category` enum)
- `economics_catalog.tags` — JSONB
- `market_benchmarks.tags` — JSONB
- All future "catalog"-shaped tables

### 3. Engines accept inputs that describe the operator context — never bake operator identity in

A `compute_net_revenue(booking, operator_context)` function works for Carmen Beach AND a Liquefex client in Spain because `operator_context` carries:
- The applicable tax regime tags
- The connected platform list
- The local currency
- The cultural-context flags (e.g., siesta-friendly response windows)

The function body never knows it's serving Carmen Beach specifically. Same function, different inputs, different output. Adding a new operator = adding rows to `operators`, `user_connections`, and `org_context` — never editing the engine.

### 4. The engine catalog is itself a multi-axis-tagged data structure

When the platform onboards a new operator (e.g., a new Liquefex client), it queries the engine catalog filtered by `operator_context.tags` → returns the subset of engines + datasets that apply → instantiates them with operator-specific inputs.

A NEW operator's intelligence system is constructed by the system from existing modular parts; nobody writes new code.

## Application to current STVR work

The Economics + Market_Benchmarks I'm cataloguing from this session's web research are tagged like:

```yaml
- key: airbnb_host_service_fee_pct
  value: 0.155
  tags:
    - industry: hospitality
    - sub_vertical: short_term_rental
    - sub_vertical: vacation_rental
    - geography: global
    - regime: ota_commission
    - source: vendor_doc_airbnb
    - source_url: https://www.airbnb.com/resources/hosting-homes/a/simplifying-airbnb-service-fees-746
    - effective_from: 2025-12-01
    - modality: quantitative
  notes: "Host-only fee model since Dec 2025; +2% for Super Strict 30/60"

- key: mx_quintana_roo_lodging_tax_pct
  value: 0.05
  tags:
    - industry: hospitality
    - sub_vertical: short_term_rental
    - country: mexico
    - state: quintana_roo
    - regulatory_regime: mx_sat
    - regulatory_regime: mx_quintana_roo_ish
    - source: government_doc
    - source_url: https://thelatinvestor.com/blogs/news/mexico-rental-income-taxes-keep
    - effective_from: 2026-01-01
    - modality: quantitative
  notes: "ISH lodging tax; Airbnb collects 6% (1% delta noted)"

- key: playa_del_carmen_avg_adr_usd
  value: 135
  range: [74, 140]
  tags:
    - industry: hospitality
    - sub_vertical: short_term_rental
    - country: mexico
    - state: quintana_roo
    - city: playa_del_carmen
    - segment: tourist
    - benchmark_type: market_average
    - source: industry_benchmark
    - source_url: https://www.airroi.com/airbnb-data/mexico/quintana-roo/playa-del-carmen
    - observed_at: 2026-05-16
    - modality: quantitative
  notes: "Range $74-$140 across data aggregators; $135 is AirROI 2026 figure"
```

Now a different operator (say, Liquefex in Tulum, or a new client in Bali) reuses everything tagged `short_term_rental` and SWAPS in their own `country`/`state`/`city` tags. The Mexico-specific rows don't match; the global rows do.

## Application to engines

When the system asks "compute net revenue for this booking," the engine:

1. Reads `operator_context.tags` (e.g., `[hospitality, short_term_rental, country:mexico, state:quintana_roo, city:playa_del_carmen]`)
2. Queries `economics_catalog` for rows matching ANY of those tags
3. Picks the most-specific applicable row per key (e.g., `mx_quintana_roo_lodging_tax_pct` over a Mexico-wide default)
4. Composes the net-revenue formula from the matched rows

Result: the same engine serves Carmen Beach (MX/QR/PDC) AND a future Costa Rica client (CR/Guanacaste/Tamarindo) AND a Bali client (ID/Bali/Canggu) — without editing the engine.

## Anti-patterns

- ❌ Hardcoding "Carmen Beach" anywhere outside of an operator profile row
- ❌ Single-axis category enums when JSONB tags would compose better
- ❌ A column named `tax_pct` without geography/regime tags — useless for any other context
- ❌ Engines that import operator-specific config at module-import time
- ❌ Data captured for one operator stored where another operator's engine can't read it (data silos by accident)
- ❌ "Operator-specific" engines or services that are 90% the same as another operator's — these MUST be one engine + two operator_context rows

## Enforcement (drift-sentinel candidates)

- Any new table with a `category VARCHAR` enum-style column WITHOUT a paired `tags JSONB` column = flag
- Any new engine module whose imports include operator-name strings (`carmen_beach`, `liquefex`, etc.) outside of test fixtures = flag
- Any datum row missing the source-provenance tag = flag
- Any engine catalog entry without multi-axis applicability tags = flag

## How this composes with prior doctrine

- **[PPIM doctrine](foundational_goal_gigaton_engineered_brand_experience.md)** — modular replication is HOW the platform serves predictably-profitable interaction management across multiple operators simultaneously
- **[Universal Connector Hub](universal_connector_hub_architecture.md)** — connectors are already catalog-driven; this doctrine generalizes to all data + engines
- **[Gigent Value Matrix](gigent_value_matrix_doctrine.md)** — modular replication is what produces log-function improvement (one engine serving N operators >> N bespoke engines)
- **[Web-search data backfill](feedback_web_search_for_data_backfill.md)** — web-sourced rows MUST carry source-provenance tags so they're refresh-able + auditable
- **[Auto-complete preventive tasks](feedback_auto_complete_preventive_tasks.md)** — when adding a new row to any catalog, AUTO-derive the obvious tags from context (industry, geography, regime) — don't ask

## Context

- Anchors how the STVR Economics + Market_Benchmarks sheets are structured (and by extension all future "knowledge base" sheets)
- Anchors how the Connectors_Catalog table (PR #218) evolves (add `tags JSONB` in a follow-up migration)
- Anchors how every new engine accepts `operator_context` and queries catalogs by tag
- Established by Todd 2026-05-16: "Engineer all solutions so they're able to be easily replicated with inputs automatically"
