---
name: Universal Connector Hub — the Gigaton product
description: Gigaton is the universal platform where users log in, CONNECT EVERYTHING (every 3rd-party service, every channel, every data source), and use Gigaton intelligence to build → manage → maximize profit. Established 2026-05-16. THIS is the product; engines + dashboard + chat are surfaces of it.
type: project
established: 2026-05-16
status: ACTIVE — this reframes every prior product description
serves: foundational_goal_gigaton_engineered_brand_experience (PPIM)
originSessionId: 46573597-53b1-49ab-b43d-26dc9f6ff65e
---
# Universal Connector Hub — the actual Gigaton product

## The reframe

Until 2026-05-16, internal documents described Gigaton as a collection of engines (decision-engine, intelligence-silo, HME, PPEME, UAE, etc.) accessed via the chat + operator surfaces.

**That was the architecture, not the product.** Todd clarified the product:

> The goal is for the user to be able to log into gigaton, connect everything, and then use the gigaton intelligence to build → manage everything → maximum profit.

Gigaton is **a universal connector + intelligence layer**. The user shows up once, connects every third party they use (booking platforms, payment processors, communication tools, ad platforms, CRMs, accounting, etc.), and Gigaton's intelligence drives the whole business toward maximum profit per the PPIM doctrine.

The engines + chat + dashboard are SURFACES of this product, not the product itself.

## What "connect everything" means concretely

Every 3rd-party listed in the platform map (Carmen Beach Properties' 60-row `01_Platform_Map.csv`) — and the longer universe of integrations across every Gigaton entity — is a CONNECTOR. Each connector:

1. **Captures cost** (commissions, API fees, subscription tiers, per-message rates)
2. **Captures inbound events** (bookings, payments, messages, leads, transactions)
3. **Enables outbound actions** (send messages, post listings, charge cards, update inventory)
4. **Feeds the intelligence layer** (every event becomes substrate for the next decision)

Connectors span:
- **Booking platforms** (Airbnb, Vrbo, Booking.com, Expedia, etc. — for STVR + travel businesses)
- **Payment processors** (Stripe, PayPal, wire, Mexican peso processors for CB)
- **Communication** (Twilio SMS, WhatsApp Business, SendGrid email, Slack, Intercom)
- **Marketing** (Google Ads, Meta Ads, TikTok Ads, etc. — all the paid channels)
- **CRM / customer data** (HubSpot, Salesforce, Pipedrive)
- **Accounting** (QuickBooks, Xero, FreshBooks)
- **Productivity** (Google Workspace, Microsoft 365)
- **Cloud storage** (Google Drive, Dropbox, OneDrive)
- **Calendar** (Google Calendar, Outlook, iCal — for STVR + scheduling)
- **Reviews & reputation** (Google My Business, Yelp, Tripadvisor)
- **Analytics** (Google Analytics, Mixpanel, Amplitude)
- **Project management** (Linear, Jira, Asana, ClickUp)
- **Code / repos** (GitHub, GitLab, Bitbucket)
- **AI providers** (Anthropic, OpenAI, Gemini — already in `llm_call_cost`)
- **Other Gigaton entities** (Carmen Beach ↔ Liquefex ↔ Ti Solutions ↔ InContekst cross-referrals)

There is NO short list. Every third party is on the connector hub. Some are first-class (already instrumented); most are roadmap.

## What the "intelligence" promises

Once everything is connected, the user gets:

1. **Unified observability** — every cost, every revenue, every interaction in one timeline
2. **Cross-vendor analytics** — "this customer touched 9 channels before booking" without manual ETL
3. **Automated profit optimization** — Gigaton intelligence proposes the next-best-action per customer per channel
4. **Predictability** — outcomes forecasted in advance with bounded variance (PPEME Master Calculator)
5. **Continuous calibration** — outcomes feed back into selection (OVS-Calibration loop)
6. **Brand coherence** — every channel speaks the same Gigaton-engineered voice
7. **Compounding intelligence** — every new connection adds substrate that improves every prior connection's decisions

## Architectural implications

### A. Connector catalog (data-driven, not hardcoded)

`connectors_catalog` table — extensible roster of all supported connectors. Per row:

```
connector_id          (airbnb | vrbo | stripe | twilio | google_ads | hubspot | ...)
category              (booking_ota | payment | communication | marketing | crm | ...)
name                  (display name)
description           (one-liner)
auth_type             (oauth2 | api_key | webhook | manual_csv)
auth_scopes           (list)
docs_url              (vendor's API docs)
status                (live | beta | roadmap | deprecated)
required_for_brand    (list of brands that need it: carmen_beach | liquefex | ...)
estimated_cost_model  (per_request | per_message | percentage_of_volume | subscription)
ppim_economics        (how this connector's cost + revenue tie to PPIM)
```

The Connector Hub UI renders from this catalog. New connectors = new row + adapter implementation; the UI updates automatically.

### B. Per-user connection state

`user_connections` table — what each user has connected.

```
user_id
connector_id
status             (connected | pending_oauth | error | disconnected)
secret_ref         (link to SecretStore for credentials; never store raw)
metadata           (account info, scopes granted, last_sync_at, etc.)
connected_at
disconnected_at
```

### C. Universal cost telemetry

Extends the `llm_call_cost` pattern to every connector. New table:

```
third_party_call_cost
  id, created_at, operator_id, operator_event_id, org_id,
  connector_id, vendor_call_type (api_request | webhook | sms | etc.),
  units (request count | tokens | message count | $$ commission),
  cost_estimate_usd, latency_ms, error
```

Every connector adapter writes to this table on every external call. The dashboard sums + groups by anything.

### D. Brand-dimension extensibility (NOT a hardcoded enum)

Original PPIM doctrine proposed 5 brand dimensions (responsiveness / quality / personalization / resolution / upgrade). Todd's correction 2026-05-16:

> This is OK to start, but should automatically be adjusted, expanded, optimized as systems gain intelligence.

Therefore:

`brand_dimensions` table (data-driven, system-proposable, governance-gated):

```
dimension_id          (slug)
name                  (display)
description           (what this dimension measures)
status                (active | proposed_pending_review | retired | merged_into:<other>)
introduced_by         (system_proposed | operator_manual | merged_from:<list>)
introduced_at
evidence_count        (how many interactions tagged with this dimension since introduction)
related_dimensions    (clusters)
penrose_link          (which Penrose metric this contributes to)
ppim_brand_dimension_signature (used by drift sentinel)
```

Seed with the 5 originals. As the platform accumulates evidence, the **Codification Engine** + **OVS-Calibration** can propose new dimensions emerging from interaction clusters; user approves/rejects via the governance flow already established. Drift-sentinel rule: any module declaring `ppim_brand_dimension:` with a value not in the `active` set of this table = drift.

### E. Connector security model

Per Gigaton's data-trust commitments:
- Every credential lives in SecretStore (`gcp:` backend in prod, `file:` in dev)
- OAuth refresh handled at the connector adapter level (not in the user's session)
- Per-connector scope minimization (request the LEAST permissions sufficient for the connector's promised functionality)
- Per-user disconnect = secret deletion + audit row
- All connector activity audited (every call, every cost, every error) in the third_party_call_cost table

### F. Cross-vendor identity resolution

A single customer may show up across multiple connectors:
- As a guest_id in Airbnb
- As an email in Stripe
- As a phone number in Twilio
- As a record_id in HubSpot
- As an Instagram username in DM history

The intelligence layer needs a **Customer Identity Resolution** capability that joins these into one identity. This is its own engine (or a capability of decision-engine's entity-resolution-service). For v0, manual mapping is acceptable; for v1, automatic via fuzzy match + ML.

## Why every prior memory needs to be re-read through this lens

Every engine spec in this directory describes a capability. Each capability has VALUE only when connected to:

1. Specific user-connected 3rd-party data sources (without connections, the engine has no substrate)
2. Specific user-visible outcomes via the Connector Hub UI (without the surface, the engine is invisible)
3. Specific PPIM economics (without cost+outcome attribution, the engine is unaccountable)

**The Connector Hub is THE product. Engines are dependencies.**

## Concrete build order (revised — parallel, not sequential)

Parallel agents launching now (2026-05-16 session):

| Track | Repo | What |
|---|---|---|
| 1 — Data backbone | sovereign-influence-engine | Migrations for `third_party_call_cost` + `brand_dimensions` + `connectors_catalog` + `user_connections`; `vw_action_trace` view; `shared/third_party_cost.py` helper |
| 2 — Connector Catalog seed | sovereign-influence-engine | YAML seed `data/connectors/{connector_id}.yaml` for ~30 highest-priority connectors; loader job that hydrates `connectors_catalog` from seed at deploy |
| 3 — Vendor telemetry | sovereign-influence-engine | Wrap Stripe + Twilio + OTA-commission + Slack + SendGrid call sites with cost-logging using the new `third_party_cost.py` helper |
| 4 — Connector Hub UI | Gigaton-UI-Platform | `/connectors` page: catalog grid (filter by category + status), per-connector connect button (OAuth or API-key flow), connection-state display, disconnect with audit confirmation |
| 5 — Dashboard endpoint + UI | operator-api + Gigaton-UI-Platform | `/operator/dashboard/influence` endpoint (Level 1 atomic table query); `/dashboard` page rendering it with filters |

(PPEME counterfactual sim, OVS-Calibration outcome→event linking, AI Routing Engine prompt registry, identity resolution, etc. are subsequent waves.)

## Context

- Pairs with [foundational_goal_gigaton_engineered_brand_experience](foundational_goal_gigaton_engineered_brand_experience.md) — universal-connector is the WHAT; PPIM is the WHY
- Pairs with [user_influence_vs_cost_dashboard_spec](user_influence_vs_cost_dashboard_spec.md) — the dashboard is one of several surfaces of the universal hub
- Pairs with [engine_artifact_doctrine](engine_artifact_doctrine.md) — every engine completes the equation `f(user, org, platform.intelligence, resources.available)`; the Connector Hub is where the user wires `resources.available`
- Pairs with [predictably_profitable_experience_management_engine](predictably_profitable_experience_management_engine.md) — PPEME is the engine that turns connected substrate into predictably profitable outputs
- Anti-pattern: hardcoded connector list. New connectors must require only a YAML seed + adapter; no UI code change.
- Anti-pattern: storing credentials anywhere but SecretStore.
- Anti-pattern: a connector whose costs don't write to `third_party_call_cost` — invisible cost = PPIM violation.
