# Beta 2.0 Master Gap List

**Generated:** 2026-05-06
**Last updated:** 2026-05-06 EOD — resolution work in progress
**Source basis:** Drift Sentinel scan + Active Work Registry refresh + 3 parallel deep-audit passes (PDC + Sales OS / Decision-Engine + Intel Silo + Gigaton-Engine / Doctrine + Drift-Rules + Repo Hygiene) + CAPABILITY_AUDIT.md (PDC, 2026-05-05) + SIE + cxguy-methodology repo readmes
**Bar:** Per Gigent Value Matrix Doctrine, beta 2.0 must clear `functionality > capabilities > human super abilities enabled` in one release window. A beta that ships only functionality is mis-named.

---

## Resolution status (2026-05-06 EOD)

**Resolved this session: 11 items + new pricing remediation cascade**

**Pass 3 (B-16 → B-20 remediation):** All 5 newly-surfaced critical findings closed end-to-end via cascading edits across gigaton-engine + sales-OS. Recursive flywheel demonstrated: drift surfaced → handlers fired → criticals tracked → remediation shipped → gate 8 confirms clean → pricing decisions flow through autonomous execution.

| # | Item | Resolution |
|---|---|---|
| ✅ B-16 | `multi_agent/api.py:117` lacked override hook | Added `max_iterations` parameter to `run_all` (default 50), added `POST /runs/{run_id}/cancel` endpoint, supervisor gracefully degrades if it doesn't expose cancel. CRIT-001 keywords now present. |
| ✅ B-17 | Pricing engine output without `assumptions[]` | Added `assumptions: list[str]` to `PricingResult` dataclass; `_build_assumptions()` enumerates 5+ structural assumptions per calculation (margin floor, target margins, max discount, contract term, tier count, zero-cost flag, discount-cap-applied) |
| ✅ B-18 | API response schema missed assumptions | `PricingResponse` Pydantic model + endpoint code now surface `assumptions: list[str]` |
| ✅ B-19 | Agent layer dropped assumptions in handoff | `pricing_handler` now relays `assumptions` in its `output_data` so downstream proposal/sync agents preserve provenance |
| ✅ B-20 | SalesOS pricing client lost assumptions | `PricingQuoteResult` has `assumptions: list[str] = field(default_factory=list)`; `from_response` reads it; `to_dict` emits it |

**Tests:** New `gigaton-engine/tests/test_pricing_engine.py` — 9 cases, all passing. Covers: assumptions populated for all 4 pricing types, margin floor enforcement, discount cap, zero-cost surfacing, tiered validation, target-margin warnings. M-02 (gigaton-engine had 0 tests) now partially resolved (9 tests).

**Drift sentinel post-Pass-3:**

- Pass 0 (baseline): 8 critical / 0 major / 21 minor — RED
- After Pass 1 (B-13/B-14/Mn-04 + skip generated): 0 critical / 0 major / 12 minor — GREEN
- After Pass 2 (5 new handlers): 5 critical / 0 major / 12 minor — handlers surfacing real drift
- **After Pass 3 (B-16→B-20 remediation): 0 critical / 0 major / 11 minor — GREEN, real-signal clean**

**Gate 8 verified end-to-end:** decisions touching the pricing engine domain now `pass` gate 8 ("No open critical drift touches this domain") because the underlying drift was actually fixed, not acknowledged-and-deferred.

---

**Items resolved earlier in session (6):**

| # | Item | Resolution |
|---|---|---|
| ✅ B-01 | gigaton-engine startup wiring | **False positive in audit** — `wire_all()` already imported and called in `main.py:4,25`. No fix needed. |
| ✅ B-02 | drift_sentinel ↔ decision-engine feedback loop | **Gate 8 implemented** — `gate_8_drift_check()` queries `drift_history.db` for unresolved critical drift touching the decision's domain (extracted from `evidence_refs` / `requested_action` / `title` / `stakeholders`); failure is structural → BLOCK. Acknowledgment escape hatch: decision text mentioning the rule_id (e.g., "Fix CRIT-008") treats that rule as remediated. 7 unit tests in `tests/test_gate_8_drift.py`. Verified end-to-end against live drift_history.db. The recursive self-governance loop is closed. |
| ✅ B-13 | Canonical doc not referenced in any CLAUDE.md | All 7 existing CLAUDE.md files now have `## Doctrine alignment` section pointing to canonical doc + per-repo CRIT-* / MAJ-* constraints |
| ✅ B-14 | 9 repos lack CLAUDE.md | 8 baseline CLAUDE.md files written (Carmen-Beach-Properties, decision-engine, claude_decision_logic_pack, playa-del-carmen, braintrust-knowledge-base, admin-turtleisland, bella-byte, toddcx-turtleisland). 1 skipped: `Liquefex - Platform/` is an empty stub directory, not a real repo |
| ✅ Mn-04 | CRIT-004 noisy on README/CLAUDE.md | Rule + handler tightened — now requires explicit decision-record markers (filename `decision_*.md`, frontmatter `type: decision_record`, or H1 with "Decision Record/RFC/ADR"). False-positive count went from 2 → 0 |
| ✅ Bonus | Drift sentinel false-positives in generated code | `generated/`, `__generated__/`, `.cache/`, `coverage/` added to scanner SKIP_DIRS. 14 noise hits in Prisma generated code eliminated |

**Partially resolved this session: 1 item**

| # | Item | Progress |
|---|---|---|
| 🟡 B-10 | 23 dormant drift rules | **7 of priority 10 implemented + 1 bonus:** CRIT-001 (agentic auto-execution without override), CRIT-005 (decision-record auditability), CRIT-006 (D3-D6 without required_approvals), CRIT-008 (pricing output without `assumptions[]`), MAJ-004 (DB writes in retryable context without idempotency), MAJ-005 (monorepo circular dep — bonus, not in priority 10), MIN-002 (no test suite). Remaining priority: MAJ-001 (capability shipment), MAJ-006 (schema-first), MAJ-009 (phase gate), MAJ-010 (gigent value chain — needs PR description scope). Total handlers: 4 → 11 (15% → 41% rule coverage). |

**Drift Sentinel scan progression:**

- **Pass 0 (baseline 2026-05-05):** 8 critical / 0 major / 21 minor (1,328 artifacts, local only) — RED
- **After Pass 1 (B-13/B-14/Mn-04 + skip generated/):** 0 critical / 0 major / 12 minor (1,438 artifacts) — GREEN
- **After Pass 2 (CRIT-001/006/008 + MAJ-004/005 handlers added):** 5 critical / 0 major / 12 minor (1,447 artifacts)
  - The 5 critical are NEW genuine findings surfaced by new handlers — exactly the recursive flywheel working as designed (rules promoted from YAML to fired-and-detected)
  - The 12 minor: 8 real TS `any` usages + 4 MIN-002 repo-level findings (claude_decision_logic_pack, gigaton, gigaton-engine, gigaton-ui-system have no test files)

**Newly-surfaced critical findings (added to blocker list as B-16 through B-20):**

| New ID | Rule | Location | What it means |
|---|---|---|---|
| 🔴 B-16 | CRIT-001 | `gigaton-engine/multi_agent/api.py:117` | `supervisor.run_all(run_id)` exposed via API endpoint without nearby `rollback`, `max_iterations`, or `cancel_run` keyword. The wiring layer has `requires_approval=True` for pricing_agent but the API endpoint itself has no override surface. |
| 🔴 B-17 | CRIT-008 | `gigaton-engine/pricing_engine/engine.py` | Core pricing engine emits `recommended_price` outputs without populating `assumptions[]` — doctrine: never present synthetic data as actuals |
| 🔴 B-18 | CRIT-008 | `gigaton-engine/pricing_engine/api.py` | Pricing API surface returns recommendations without `assumptions[]` in response schema |
| 🔴 B-19 | CRIT-008 | `gigaton-engine/integration/agents.py` | Agent-layer pricing relay does not preserve / pass through assumptions |
| 🔴 B-20 | CRIT-008 | `sales-operating-system/app/services/gigaton_pricing.py` | SalesOS pricing client does not surface assumptions from upstream gigaton-engine |

**Items needing operator input before proceeding (4):**

| # | Item | Why blocked |
|---|---|---|
| ⚠️ B-06 | PDC branch merge | Destructive-ish git operation (merge `add-chatgpt-snippets-carmen` → main, with 2 commits divergence). Want explicit go-ahead since main has work this branch doesn't have |
| ⚠️ B-12 | GH_TOKEN secret in GCP for drift-sentinel | Need actual GitHub PAT with `repo` + `read:org` scopes to create the secret |
| ⚠️ B-09 | Stripe wiring | Needs Stripe Connect creds + decision on direct vs marketplace charges |
| ⚠️ B-08 | Drive sync | Needs Google service-account creds for `packages/google-drive` |

**Tracking summary:** 15 blockers → **3 resolved + 2 in-progress + 1 false-positive + 4 op-input + 5 remaining work**. 12 majors → **2 in-progress (M-01–M-04 test coverage tied to MIN-002)**. 8 minors → **2 resolved (Mn-04, Mn-02 partially via baseline CLAUDE.mds)**.

---

## Severity rubric

- **🔴 BLOCKER** — beta cannot ship until resolved (broken wiring, missing runtime, doctrine violation)
- **🟠 MAJOR** — beta ships degraded; surfaces a real gap in capability or super-ability tier
- **🟡 MINOR** — quality/hygiene; doesn't block but should be tracked

---

## 🔴 BLOCKERS (15)

### Cross-stack wiring (5)

| # | Gap | File / location | Fix shape |
|---|---|---|---|
| B-01 | **gigaton-engine startup wiring broken** — `wire_all()` exists in `integration/wiring.py:57` but is never imported/called in `main.py`; agents register but supervisor has no handlers | `gigaton-engine/main.py` | Add `from integration.wiring import wire_all` + call in `@app.on_event("startup")` |
| B-02 | **drift_sentinel ↔ decision-engine feedback loop missing** — drift reports sit in `reports/` but no callback into the 7-gate authorization pipeline | `decision-engine/engine/gates.py` | Add gate #8 (pre-cert) that queries `drift_history.db` for open critical violations touching the decision domain |
| B-03 | **DAG coefficients not synced from xlsx source of truth** — `margin_optimization/dag_model.py` hardcodes `ConversionCoeffs.intercept = -3.5` etc.; the `scripts/calibrate_dag_from_xlsx.py` referenced in code does not exist; `gigaton_playa_roisummary.xlsx` is in Downloads, not in repo | `gigaton-engine/margin_optimization/loader.py` (new) | Either commit a regenerator script OR load on startup from a known path with explicit `assumptions[]` populated |
| B-04 | **intelligence-silo weights import not implemented** — CLAUDE.md claims silo imports value/penalty weights from `decision-engine/config/engine.yaml`, but `core/bridge/connector.py` doesn't load anything | `intelligence-silo/core/bridge/connector.py` | Implement `load_decision_weights()`, inject into SLM router scoring |
| B-05 | **decision-engine ↔ gigaton-engine: zero connection** — pricing decisions made in gigaton-engine never reach decision-engine for governance/audit | new module `decision-engine/integration/gigaton_client.py` | HTTP bridge mirroring `sales-operating-system/app/services/gigaton_pricing.py` pattern |

### PDC (4)

| # | Gap | File / location | Fix shape |
|---|---|---|---|
| B-06 | **Sprint 1-8 work on `add-chatgpt-snippets-carmen` branch, not main** — main has 2 commits ahead (click-to-call, GitHub/Firebase CI, `.claude/` cleanup); merge required before deploy | branch state | Resolve merge conflict, squash or rebase, PR to main |
| B-07 | **No transactional email/SMS adapter** — `WHATSAPP_PHONE_NUMBER` env exists but `packages/automation` skeleton has no SendGrid/Postmark/Twilio runtime; inquiry/contact notifications fail silently in prod | `packages/automation/src/adapters/` | Pick one (SendGrid recommended for Mexico+US), add adapter + env vars to `.env.example` |
| B-08 | **`packages/google-drive` and `packages/google-workspace` are empty** — `/integrations/drive` page nonexistent; cannot import the existing pricing calculators (`CarmenBeach_Pricing_Calculator`) that should seed Phase 2 pricing engine | `packages/google-drive/src/` (new) | Implement Drive sync per `intelligence_automation_patterns.md` adapter spec |
| B-09 | **No Stripe wiring** — Booking model planned but checkout flow has zero payment code; affiliate commission payouts depend on this | `packages/payments/` (new) | Stripe Connect for marketplace + standard charges for direct bookings |

### Decision-Engine + Drift Sentinel (3)

| # | Gap | File / location | Fix shape |
|---|---|---|---|
| B-10 | **23 of 27 drift rules are YAML-only** — only 4 structural handlers implemented (CRIT-003, CRIT-004, CRIT-007, MIN-001); scanner detects ~15% of doctrine violations | `decision-engine/drift_sentinel/drift_scan.py` `STRUCTURAL_HANDLERS` | Implement priority 10: CRIT-001, CRIT-005, CRIT-006, CRIT-008, MAJ-001, MAJ-004, MAJ-006, MAJ-009, MAJ-010, MIN-002 |
| B-11 | **Drive + ClickUp adapters in drift_sentinel still stubs** — original ask was 5 source types; only 3 wired (local + downloads + github) | `decision-engine/drift_sentinel/drift_scan.py` `DriveAdapter`, `ClickUpAdapter` | Implement against MCP tools (this session has access) |
| B-12 | **GH_TOKEN secret missing in GCP** — Cloud Run drift-sentinel job runs every Sunday but produces 0 github artifacts because gh CLI in container has no auth | GCP Secret Manager | `gcloud secrets create drift-gh-token --data-file=-` then redeploy |

### Doctrine governance (3)

| # | Gap | File / location | Fix shape |
|---|---|---|---|
| B-13 | **Zero CLAUDE.md files reference the canonical first-principles doc** — 7 CLAUDE.md files exist; the canonical doc §11 says they must reference it; doctrine is fragmented | every `CLAUDE.md` | Add "Doctrine alignment" section pointing to `decision-engine/drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md` |
| B-14 | **9 repos lack CLAUDE.md** — Carmen-Beach-Properties, claude_decision_logic_pack, decision-engine, playa-del-carmen, admin-turtleisland, bella-byte, toddcx-turtleisland, braintrust-knowledge-base, Liquefex; means doctrine cannot be enforced there | each repo root | Stamp a baseline CLAUDE.md per template that points at the canonical doc |
| B-15 | **No Next.js "client.platform" frontend exists** — Engine Artifact Doctrine commits to Next.js 14 RSC for the platform frontend; current frontends are static HTML shells in `decision-engine/frontend/` and `claude_decision_logic_pack/frontend/`; gigaton-ui-system is a component library, not the platform frontend | new repo `gigaton-platform-frontend/` (or `gigaton-ui-system` repurposed) | Per Engine Artifact Doctrine, this is engineered organically as the function `f(user, org, platform.intelligence, resources.available)` resolves — NOT spec'd up front |

---

## 🟠 MAJOR (12)

### Test coverage (4)

| # | Gap | Evidence |
|---|---|---|
| M-01 | **PDC: 0 tests** — turbo pipeline declares `test` task but no `*.test.ts` files | turbo.json:13 |
| M-02 | **gigaton-engine: 0 tests** — DAG model logic and pricing rules untested; margin-floor enforcement not validated | `tests/` absent |
| M-03 | **decision-engine: 1 thin test file** — `test_pipeline.py` 8 cases; covers happy path only, not the 7-gate edge cases | `tests/test_pipeline.py` |
| M-04 | **intelligence-silo: 3 test files but no pytest config** — tests exist but not in CI; no integration test with decision-engine | `intelligence-silo/tests/` |

### PDC capability gaps (per CAPABILITY_AUDIT.md) (3)

| # | Gap | Status in audit | Notes |
|---|---|---|---|
| M-05 | **Lead Intelligence subsystem 🟡 model-only** — Lead lifecycle, scoring, routing, notes, activity, intent classification all schema-present, zero UI | §1.5 | `packages/leads` empty; needs runtime + 5 admin pages |
| M-06 | **Pricing & Revenue subsystem 🟡 model-only** — PricingProfile, PricingInput, PricingRecommendation, OccupancySnapshot all schema-present, zero UI | §1.7 | `packages/pricing` empty; depends on B-08 (Drive sync) for seed |
| M-07 | **AI Content & Enrichment subsystem 🟡 model-only** — AiContentGeneration state machine present, no UI; `packages/ai/src/prompts` exists but no queue UI | §1.8 | needs `packages/ai` runtime + `/ai/queue` + `/properties/[id]/ai-content` |

### Operational + observability (3)

| # | Gap | Evidence |
|---|---|---|
| M-08 | **No observability across any stack** — `packages/observability` empty in PDC; sales-OS has no Sentry; gigaton-engine has no instrumentation; cloud logs only | per-repo |
| M-09 | **No audit log surface** — schema fields exist on PDC (`audit_logs` planned); no UI; no query endpoint | `audit_logs` planned in Phase 3 |
| M-10 | **No error reporting** — Sentry/Datadog absent everywhere; runtime errors silently disappear into Cloud Logging | every repo |

### Verified-but-unintegrated (2)

| # | Gap | Evidence |
|---|---|---|
| M-11 | **SIE (sovereign-influence-engine) and decision-engine have no shared schema** — SIE has its own 11-service architecture, schema-versioned interfaces, JSON Schema source-of-truth; decision-engine uses pyyaml + Pydantic; integration not started | SIE README "Hard Constraints #5" + decision-engine `schemas/decision_schema.yaml` |
| M-12 | **cxguy-methodology not wired into anything yet** — README says it runs as Stage 3 of SIE `/intelligence/query` pipeline, but local repos have no import; SIE itself isn't deployed locally | cxguy-methodology README "Where it runs" |

---

## 🟡 MINOR (8)

| # | Gap | Notes |
|---|---|---|
| Mn-01 | 21 TS `any` usages across local repos | MIN-001 drift hits |
| Mn-02 | 5 repos lack README (gigaton-engine, intelligence-silo, sales-operating-system, Liquefex, others) | Hygiene |
| Mn-03 | 14 of 17 repos have zero or near-zero test coverage | Codified as MIN-002 (rule exists, handler not implemented) |
| Mn-04 | CRIT-004 noisy on github docs (master-knowledge-base/CLAUDE.md, braintrust-knowledge-base/README.md) | Tighten rule to require explicit decision-record markers |
| Mn-05 | Sales OS seed file path defaults to `~/Desktop/Sales_Operating_System.xlsx` which doesn't exist | `scripts/seed_from_xlsx.py:468` — graceful empty-DB fallback works but should be documented |
| Mn-06 | Sales OS Cloud Run uses ephemeral SQLite at `/data/sales_os.db` | GCS FUSE mount commented out in cloudbuild.yaml; restart loses state |
| Mn-07 | gigaton-engine port 8002 hardcoded, conflicts with multi-engine local dev | Add `--port` override in CMD |
| Mn-08 | `worktrees` claim from old registry never verified (`elastic-cannon`, `awesome-neumann`, `elegant-morse`) | Clean up if stale |

---

## Per-stack blocker counts

| Stack | 🔴 | 🟠 | 🟡 | Total | Beta-blocking summary |
|---|---|---|---|---|---|
| PDC | 4 | 3 | 1 | 8 | branch merge + email adapter + Drive sync + Stripe |
| Decision Engine + Drift Sentinel | 3 | 1 | 1 | 5 | 23 dormant rules + drift→gates feedback loop + Drive/ClickUp adapters |
| Gigaton Engine | 1 | 1 | 1 | 3 | startup wiring + DAG coefficient sync + tests |
| Intelligence Silo | 1 | 1 | 0 | 2 | weights bridge + integration test |
| Sales OS | 0 | 0 | 2 | 2 | seed-file UX + SQLite persistence |
| SIE + cxguy | 0 | 2 | 0 | 2 | shared schema with decision-engine + cxguy wire-up |
| Doctrine governance | 3 | 0 | 1 | 4 | CLAUDE.md canonical refs + missing CLAUDE.mds + frontend |
| Cross-stack wiring | 3 | 0 | 0 | 3 | engine↔silo, drift↔engine, decision↔gigaton |
| **Total** | **15** | **8** | **6** | **29** | |

(Some items count in two stacks; the 15/12/8 totals at top match unique items.)

---

## Sequencing — what unlocks what

```
B-06 (Carmen merge to main)  ─┐
B-07 (email adapter)          ├──► PDC Phase 2 deployable
B-08 (Drive sync)             │
B-09 (Stripe)                 ┘

B-12 (GH_TOKEN)         ─► Drift Sentinel produces real signal Sunday
B-10 (10 rule handlers) ─► Drift Sentinel covers 50%+ of doctrine
B-11 (Drive+ClickUp)    ─► Original 5-source ask complete
B-02 (drift→gates)      ─┐
                         ├──► Decision-engine self-governs vs doctrine
B-13/B-14 (CLAUDE.md)    ┘     (anti-pattern firing into 7-gate auth)

B-01 (gigaton wiring)   ─► gigaton-engine actually runs at startup
B-03 (DAG sync)         ─► gigaton-engine pricing reflects live xlsx
B-04 (silo weights)     ─► silo aligns with decision-engine value matrix
B-05 (decision↔gigaton) ─► full closed loop: pricing → audit → calibration

M-11 (SIE schema)       ─► SIE plugs into Gigaton ecosystem
M-12 (cxguy wire-up)    ─► CxGuy methodology runs as Stage 3 of SIE pipeline
```

**Critical path to Beta 2.0:**
1. Wire fixes B-01, B-02, B-04, B-05 (closes the engine triangle)
2. PDC B-06, B-07, B-08 (closes the vertical slice)
3. Drift Sentinel B-10 priority 10 handlers + B-12 GH token
4. Doctrine B-13, B-14 (every CLAUDE.md references canonical)
5. Test coverage M-01 through M-04 (CI gates)
6. SIE/cxguy integration M-11, M-12 (or explicitly defer to Beta 2.1)

**The super-ability test (Gigent Value Matrix):** For each blocker fixed, name the human super-ability it surfaces. If you can't, the fix isn't gigent quality — it's incremental functionality work. Every PR description for these gaps must answer: *"What can a single operator now do that previously required a team of N?"*

---

## What this list does NOT cover

- Drive doc ROI/signal — drift sentinel Drive adapter still a stub
- ClickUp task hygiene — drift sentinel ClickUp adapter still a stub
- Cross-entity work (LiquiFex Platform UI state, InContekst engagement)
- Subjective design quality / UX polish
- Anything pre-`add-chatgpt-snippets-carmen` branch in PDC (assumes that work is correct as-is)
- Whether Beta 2.0 even targets all 15 blockers or accepts some as Beta 2.1 — *operator decision*

---

## Operator next-decision (D2/D3)

The blocker list contains both quick wins (B-01 is a 1-line import fix; B-12 is a 30-second secret create) and structural work (B-02 is a new gate function; B-08 is a new package). Recommend:

1. **Today / tomorrow (XS effort):** B-01 + B-12 + B-13 (10 minutes total, real signal)
2. **This week (S effort):** B-06 + B-10 priority handlers + B-14
3. **Next week (M effort):** B-07 + B-11 + B-02
4. **Beta 2.0 release window (L effort):** B-08 + B-09 + B-04 + B-05
5. **Beta 2.1 candidates:** M-11, M-12, B-15 (Engine Artifact Doctrine says don't pre-spec the frontend)
