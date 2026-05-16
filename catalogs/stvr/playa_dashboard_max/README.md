# Playa STVR Dashboard MAX — auxiliary catalogs

Five CSVs that anchor the Carmen Beach / `playadelcarmen.homes` STVR (short-term vacation rental) intelligence model. Authored under the **Modular Replication via Input Substitution** doctrine — every row carries multi-axis tags so the SAME engine can serve a Tulum / Tamarindo / Canggu operator by swapping operator context, never by editing code.

## Files

| File | What | Row count |
|---|---|---|
| `01_Platform_Map.csv` | Every booking + acquisition + reputation surface (universe of inbound channels) | 59 |
| `02_Channels_Map.csv` | Broader: paid + organic + owned + B2B + reputation channels with funnel role | 39 |
| `03_Segmentation_Dimensions.csv` | Customer segmentation on 6 orthogonal axes (trip purpose / party / budget / stay duration / booking window / origin market / age / lifecycle) | 41 |
| `04_Interaction_Touchpoints.csv` | Lifecycle touchpoints across awareness → consideration → booking → pre-arrival → during-stay → post-stay → repeat → referral | 32 |
| `05_Economics.csv` | Geo-tagged, web-sourced benchmarks: OTA commissions, Mexico tax stack, Playa ADR/occupancy/seasonality, vendor cost models | 38 |

## Multi-axis tag schema (every row of every catalog)

Tags are semicolon-separated `key:value` pairs in the `tags` column. Designed to be loaded into a `tags JSONB` column when these are imported into Postgres (see `connectors_catalog` table from PR #218).

| Axis | Examples |
|---|---|
| `industry` | `hospitality` |
| `sub_vertical` | `short_term_rental`, `vacation_rental`, `medium_term_rental`, `executive_housing`, `event_stay` |
| `country` | `mexico` |
| `state` | `quintana_roo` |
| `city` | `playa_del_carmen` |
| `regime` | `mx_sat`, `mx_iva`, `mx_isr`, `mx_quintana_roo_ish`, `ota_commission`, `payment_processing`, `direct`, `referral`, `contract_or_commission` |
| `channel` | `ota`, `owned`, `paid`, `earned`, `direct`, `meta_aggregator`, `social`, `b2b` |
| `funnel_role` | `awareness`, `consideration`, `booking`, `retention`, `advocacy`, `brand`, `trust` |
| `audience` | `tourist`, `business_traveler`, `digital_nomad`, `family_with_kids`, `couple`, `solo`, `past_guests`, `corporate_relocation` |
| `lifecycle_stage` | `awareness`, `consideration`, `booking`, `pre_arrival`, `during_stay`, `post_stay`, `repeat`, `referral` |
| `source` | `vendor_doc`, `government_doc`, `industry_benchmark`, `operator_supplied`, `web_verified_2026_MM_DD` |
| `source_url` | `https://...` |
| `observed_at` | `YYYY-MM-DD` |
| `effective_from` / `effective_until` | `YYYY-MM-DD` for time-bounded validity |
| `modality` | `quantitative`, `qualitative`, `quantitative_estimated`, `qualitative_inferred`, `behavioral_observed` |
| `ppim_brand_dimension` | `responsiveness`, `quality`, `personalization`, `resolution`, `upgrade` (linked to `brand_dimensions` table — see Universal Connector Hub doctrine) |

## How a different operator reuses this

An operator in Tulum, MX:
- ✅ Reuses every row tagged `industry:hospitality;sub_vertical:short_term_rental;country:mexico;state:quintana_roo` (matches statewide regime)
- ❌ Skips rows tagged `city:playa_del_carmen` (substitutes their own city benchmarks)
- ✅ Reuses every row tagged `geography:global` (vendor commissions etc.)

An operator in Canggu, Bali:
- ✅ Reuses every row tagged `industry:hospitality;sub_vertical:short_term_rental;geography:global`
- ❌ Skips all `country:mexico` tagged rows (substitutes ID tax regime via their own Economics rows)

The engine doing this filtering is the same engine. Only the `operator_context.tags` input differs.

## Provenance + freshness

- **Operator-supplied** rows (`source:operator_supplied`) come from `Playa_STVR_Dashboard_MAX.xlsx` Params/Seasonality/Fees tabs (Drive doc `16bDJQU68Cl-TdpbbG-XvFYRfoWsZ-Bxv7cwunkmPYfU`, last modified 2025-11-05)
- **Web-verified** rows carry `source_url:` + `observed_at:2026-05-16` for refresh-ability
- **Operator/web conflict flagged:** `Playa_STVR_Dashboard_MAX.xlsx` Fees tab lists Airbnb at 14%; web-verified value is 15.5% (post Dec 2025 host-only fee model). `05_Economics.csv` uses the web value with citation; xlsx is stale.

## Downstream consumers

- `engine/ovs_calibration/adapters/carmen_beach_revenue.py` — attribution against the Channels + Touchpoints catalogs
- `scripts/backfill_carmen_beach_revenue.py` + `cli.py backfill-carmen-beach` — STVR CSV → revenue events
- `connectors_catalog` table (PR #218 in sovereign-influence-engine) — booking-OTA rows hydrate from `01_Platform_Map.csv`
- `brand_dimensions` table (PR #218) — `ppim_brand_dimension:*` tags link touchpoints to dimensions
- PPEME Master Calculator — `05_Economics.csv` rows feed the 9-var BFT state vector cost terms
- Penrose Falsification Scoreboard — `revenue_per_human_touch` metric numerator computed from booking touchpoints

## Doctrinal anchors

- [Foundational Goal — PPIM doctrine](~/.claude/projects/-Users-admin/memory/foundational_goal_gigaton_engineered_brand_experience.md)
- [Modular Replication via Input Substitution](~/.claude/projects/-Users-admin/memory/foundational_modular_replication_via_input_substitution.md)
- [Universal Connector Hub](~/.claude/projects/-Users-admin/memory/universal_connector_hub_architecture.md)
- [Web-search to backfill data](~/.claude/projects/-Users-admin/memory/feedback_web_search_for_data_backfill.md)

## Refresh cadence

Re-run web-search on `05_Economics.csv` rows monthly. Each row with `source:vendor_doc` or `source:industry_benchmark` carries `observed_at:` — flag any > 90 days stale for refresh.
