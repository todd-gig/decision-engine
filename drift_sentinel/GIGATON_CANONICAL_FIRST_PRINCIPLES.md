# Gigaton Canonical First Principles & Methodology

**Purpose:** Single source of truth that the Drift Sentinel cross-references against. Every codebase, repo, doc, ClickUp item, and Drive asset is scored against this document. Drift = deviation from what is here.

**Built from convergent extraction across:**
- 4 code stacks (Carmen Beach Properties, Gigaton + Gigaton-Engine + Gigaton-UI, Decision Engine + Intelligence Silo + Claude Decision Logic Pack, Sales Operating System)
- MD Files knowledge bundles (claude-automation v3.2, decision-logic-and-rtql, intelligence-engine, sales-operating-system-agentic)
- Master Knowledge Base, Braintrust KB, Transcript KB
- Downloads philosophy artifacts (Sovereign Influence Engine, Gigaton Custom Language Repo v3, SIE First Production Bundle v1)
- Source-of-truth anchor: [`MASTER_FIRST_PRINCIPLES_REFERENCE.md`](../MASTER_FIRST_PRINCIPLES_REFERENCE.md)

**Operating Law:** *Claude discovers logic. Python scales it profitably.*

---

## 0. THE PHILOSOPHY IN ONE SENTENCE

A **recursive trust-qualified, evidence-centered decision culture** that preserves human agency, codifies stable logic into deterministic execution, compounds value through closed-loop learning, and remains auditable from first-principles axiom to outcome variance.

### Why → How → What
| Layer | Statement |
|-------|-----------|
| **Why** | Empower human-centered transformation through ethical technology, fair value creation, and scalable intelligence |
| **How** | First-principles reasoning, value-centric decision systems, trust certification, recursive learning loops |
| **What** | Tools, systems, agreements, and operating structures that convert intelligence into predictable profitable performance |

**Mantra:** Connect. Create. Thrive. Evolve.

---

## 1. THE 7 NON-NEGOTIABLES

These are hard stops. Any artifact (code, doc, decision, plan, prompt) that violates these is **drift**, not difference.

| # | Non-Negotiable | Engine Enforcement |
|---|---|---|
| 1 | Human agency first | Automation requires human override path; D5/D6 mandatory human |
| 2 | Ethical technology use | `ethical_misalignment` weight = 3.0× (highest); `ethical_conflict` → BLOCK |
| 3 | Truth-seeking over politics | RTQL strips authority bias (Gates 8-11 causal checks) |
| 4 | Compounding long-term value over vanity | `compounding_potential` = 1.8×; `strategic_alignment` = 2.0× |
| 5 | Clarity over ambiguity | DecisionObject requires 22+ explicit fields; QC enforces completeness |
| 6 | Evidence over assumption | `evidence_quality` is promotion guard at every trust tier |
| 7 | Reusable systems over one-off effort | Learning loop codifies patterns; `knowledge_asset_creation` is positive dimension |

---

## 2. THE 15 CORE FIRST PRINCIPLES

| # | Principle | Category |
|---|---|---|
| 1 | Reality before preference | TRUTH |
| 2 | Value is relational (stakeholder × objective × time horizon) | VALUE |
| 3 | All resources are finite (time, capital, attention, trust, bandwidth) | CONSTRAINTS |
| 4 | Speed matters when opportunity decays | SPEED |
| 5 | Trust is earned through repeated validated outcomes | TRUST |
| 6 | Every system has incentives — identify before deciding | ALIGNMENT |
| 7 | Risk is asymmetrical (downside ≠ upside) | RISK |
| 8 | Compounding dominates isolated wins (prefer flywheels) | COMPOUND |
| 9 | Clarity reduces entropy (structured language → execution quality) | CLARITY |
| 10 | Evidence quality determines decision quality ceiling | EVIDENCE |
| 11 | Reversible decisions deserve speed; irreversible deserve care | SPEED/RISK |
| 12 | Humans adopt what they understand and trust | ADOPTION |
| 13 | Goodhart risk — metrics gamed if detached from reality | INTEGRITY |
| 14 | Ethics are a system constraint, not a branding layer | ETHICS |
| 15 | The map is not the territory — models update from outcomes | LEARNING |

---

## 3. THE 8 ORGANIZATIONAL ETHOS FILTERS

| # | Filter | Mechanism |
|---|---|---|
| 1 | Build what creates durable value | `strategic_alignment` weight = 2.0× |
| 2 | Default to transparency in logic and rationale | 12+ audit entries per decision |
| 3 | Respect local context while maintaining universal principles | `context_fit` trust dimension |
| 4 | Prioritize systems that get smarter with use | LVI 10→90 maturity; calibration engines |
| 5 | Protect sovereignty, authorship, fair compensation | Human override always available |
| 6 | Favor practical execution over performative sophistication | `execution_drag` penalty = 1.2× |
| 7 | Align tools, teams, and incentives with core Why | Alignment composite ≥ 0.3 minimum |
| 8 | Treat language as infrastructure for thinking | Structured DecisionObject; YAML frontmatter |

---

## 4. ANTI-PATTERNS (HARD STOPS)

These are the **drift signatures** the scanner looks for explicitly.

| Anti-Pattern | Detection Rule | Consequence |
|---|---|---|
| `optics_over_substance` | `ethical_misalignment > 3` | Gate 1 BLOCK |
| `complexity_without_leverage` | `execution_drag > 3` AND `compounding_potential < 2` | Alignment violation |
| `short_term_extraction_harms_trust` | Ethos alignment scoring | Logged |
| `undefined_ownership` | `owner` field missing/empty | QC certificate DENIED |
| `decisions_without_auditability` | `evidence_refs` empty | TC certificate DENIED |
| `action_without_qualification` | D3-D6 without `required_approvals` | Gate 6 FAIL |
| `automation_without_human_override` | R3/R4 without `rollback_trigger` | Gate 4/5 FAIL |
| `provider_lock_in` | AI call without `provider`/`model` field | Architectural drift |
| `partial_capability_shipment` | UI without API, or API without schema | Phase gate violation |
| `fake_market_data` | Pricing/score without `assumptions[]` populated | Doctrine violation |
| `prompt_without_versioning` | Prod LLM call without `prompt_version` | Runtime governance fail |
| `unaudited_state_change` | DB mutation outside Job/WorkflowEvent envelope | Event-sourcing violation |

---

## 5. THE CANONICAL FRAMEWORKS

The Gigaton stack is a layered set of frameworks. Each one is **doctrine** — drifting from any of them is detectable.

### 5.1 RTQL — Recursive Trust Qualification Loop
9 trust stages (`noise → weak → echo → qualified → cert_gap → certified → research_grade → first_principles → axiom`) gated by 11 checkpoints. **Rule:** No input materially influences decisions until qualified.
**Source:** `decision-logic-and-rtql/Recursive_Trust_Qualification_Loop_RTQL_standalone.md`, `MASTER_FIRST_PRINCIPLES_REFERENCE.md` §8

### 5.2 Value Matrix (8 + 4 dimensions, asymmetric weights)
Positive: `revenue_impact 1.5×, cost_efficiency 1.2×, time_leverage 1.3×, strategic_alignment 2.0×, customer_human_benefit 1.4×, knowledge_asset_creation 1.1×, compounding_potential 1.8×, reversibility 1.0×`
Penalty: `downside_risk 2.0×, execution_drag 1.2×, uncertainty 1.5×, ethical_misalignment 3.0×`

### 5.3 Trust Matrix (7 dimensions, T0-T4 tiers)
`evidence_quality, logic_integrity, outcome_history, context_fit, stakeholder_clarity, risk_containment, auditability`. Promotion guards prevent skipping tiers.

### 5.4 Decision Taxonomy (D0-D6 + R1-R4)
Class × Reversibility determines auto-execute eligibility. D5/D6 always mandatory human; R3/R4 escalate.

### 5.5 Certificate Chain (QC → VC → TC → EC)
HMAC-SHA256 signed; matching MD file required on disk; tamper-evident. **Hard rule:** No EC without valid QC + VC + TC.

### 5.6 7-Gate Authorization
Doctrine → Trust Tier → Value → Reversibility → Risk Containment → Approval Routing → Monitoring. Gates 1-3 fail → BLOCK; Gates 4-7 fail → ESCALATE.

### 5.7 Learning Loop + 4 Calibration Engines
Causal Model • OVS Projection • Decision Velocity • Authority Calibration. **Core rule:** A repeated decision class should get easier, faster, and safer over time.

### 5.8 Decision Routing Framework (Python vs Claude vs Hybrid)
Python = certainty (structured, deterministic, high-volume, audited). Claude = ambiguity (unstructured, interpretive, exploratory). Codification trigger: ≥50 executions, <5% exception rate.

### 5.9 Sovereign Influence Engine (SIE)
7-layer closed loop: `ingest → resolve → trust/authority → score/decide → execute → outcome → calibrate`. **Rule:** Decision logic, memory, calibration, and authority remain operator-owned.

### 5.10 Data Value Matrix (DVM) — People × Process × Technology × Learning
**Multiplicative**, not additive. Weakness in ANY system multiplicatively degrades total value. Health Score = `P × Pr × T × L`.

### 5.11 Conical Proof Methodology (12 steps)
Goal → Why → Axioms → Constraints → Assumptions → Options → Criteria → Comparative → Decision → Proof of Superiority → Execution Requirements → Risk Controls. **Rule:** No decision defaults to convention; all justified from axioms.

### 5.12 Causal Chain Mapping (4-Layer Propagation)
Layer 1 (0-7d, 100%) → Layer 2 (7-30d, 70%) → Layer 3 (30-90d, 35%) → Layer 4 (90+d, track only). Cascade multiplier: 1 system 1.0× → 4 systems 2.2×.

### 5.13 Three-Apex Knowledge Architecture
Apex A (Patents/Theory) × Apex B (Mathematics) × Apex O (Implementation). Every high-stakes decision must map across all three.

### 5.14 3-Phase Platform Build Methodology
Phase 1 (Core Vertical Slice — no placeholders, reject shallow scaffolding) → Phase 2 (Intelligence + Automation Layer) → Phase 3 (GCP Hardening). Capabilities ship only when **schema + API + UI** are all present.

### 5.15 Gigent Value Matrix (Build Quality Audit)
`functionality > capabilities > human super abilities enabled`. Every PR/release auditable against this chain. If you cannot name the super-ability surfaced, the design is not yet at gigent quality.

### 5.16 Gigaton Value Matrix (Strategy Quadrants)
BI Control × Brand Control. Quadrant IV (high BI + high Brand) = vertically integrated profit engine. **Thesis:** Predictable profitability = Brand demand + Proprietary intelligence + Conversion optimization → controlled margin expansion.

### 5.17 Attractor Dynamix Constitution (IP Governance)
Geometric/causal memory architecture as shared substrate; equal 25% Founder shares (Foster, Guarino, Jeschke, Nelson); operating ethos: do not harm each other, help when possible, learn through transparency, protect substrate, preserve sovereignty.

### 5.18 Symbiotic Memory-Experience Network (SMEN)
**Definition (canonical):** A persistent, bi-directional intelligence layer that unifies human memory, digital history, contextual signals, and AI cognition into a single causal experience fabric, enabling continuous co-evolution between individuals, communities, and machine systems. Memory becomes an asset; experience becomes a computation; cognition becomes a partner.

**3-Layer Architecture:**
- **Memory Layer** — Life logs, digital exhaust, domain-specific histories, permissioned embeddings
- **Experience Layer** — State tracking, preference modeling, relationship graphs, contextual continuity
- **Symbiotic Cognition Layer** — Causal inference (SCMs, do-calculus, counterfactual mapping), predictive simulation, adaptive reasoning, evolutionary learning

**Mantra alignment:** Operationalizes Connect–Create–Thrive–Evolve at the network scale.

**Sovereign ownership model:** Each human owns their canonical intelligence + their personal agent. Network entities (Gigaton platform + verticals) lease access via cryptographically-enforced permissioning, revocable access, and zero-knowledge boundaries. Memory + experience are appreciating assets belonging to the user; the platform is steward, not owner.

**Network value foundation (falsifiable):** Super-additive value emerges from data flywheel + network effects + cost-to-intelligence efficiency + causal inference compounding. The network produces super-additive value or it doesn't — measurable, not aspirational.

**Engine implementation map:**
- Memory Layer → `intelligence-silo` + canonical persona row in `user-access-engine`
- Experience Layer → persona/org digital twins + CxGuy Trust×Value×Priority graph + Network Intelligence Layer in `decision-engine`
- Symbiotic Cognition Layer → `decision-engine` + `cxguy-methodology` + `human-management-engine` + Network Intelligence product-dev pipeline

**Network participants (eventual goal):** Humans + their personal agents + TI experts + Gigaton platform + network entities (Carmen Beach, Ti Solutions, LiquiFex, InContekst). All four engines (`user-access-engine`, `human-management-engine`, `decision-engine`, `intelligence-silo`) plus Gignet Local Node are sub-components of the SMEN implementation.

**Why this is binding doctrine:** Anchors every architectural decision to a measurable network outcome. Without SMEN as canonical doctrine, engine specs drift toward platform-owns-data assumptions that contradict User Sovereignty. Promoted to canonical 2026-05-08 by Todd; previously formalized 2025-12-02 (v1.0 2026-01-08) but not yet binding.

**Source:** `MD Files/chatgpt-gigaton/research-and-concepts/ChatGPT MD -Symbiotic Memory-Experience Network origin.md` (v1.0, 2026-01-08). Memory cross-references: `smen_doctrine.md`, `gigaton_guest_invite_persona_capture.md`, `human_management_engine.md`.

---

### 5.19 Business Field Theory (BFT / Mtheory Math)

**Definition (canonical):** A predictive operating model that treats a business as a high-dimensional state system whose observable outputs (revenue, conversion, churn, growth, enterprise value) are emergent projections of a 9-variable normalized hidden state. Every interaction is a transformation function on that state; every decision is an input to a transformation; outcomes are simulated forward before capital commits. The physics M-theory analogy is structural, not metaphorical: as M-theory unifies fundamental forces into a single higher-dimensional structure, BFT unifies brand, interaction, decision, and revenue into a single business field-theoretic system. **State + Interaction → Emergent Outcome.**

**Core insight:** There is no such thing as an isolated decision. Every decision changes the state of the business system. Brand is not identity — brand is a state field that encodes expectations, trust, meaning, and perceived value.

**State vector (canonical, 9 variables, all normalized 0–1):**
```
S(t) = [trust, attention, clarity, desire, urgency, value, friction, social_proof, context_fit]
```
The 9 variables are the binding set. Substitution, addition, or removal of variables requires a new amendment under triad sign-off. Variables are bounded `0 ≤ S_i(t) ≤ 1` and clipped on every update.

**Core equations:**
- Interaction update: `S(t+1) = clip(S(t) + ΔI + ε, 0, 1)`
- Conversion: `P(convert) = sigmoid(β₀ + β · S(t))` with friction sign flipped (negative coefficient — friction reduces conversion)
- Revenue: `Revenue = Traffic × P(convert) × AOV`
- LTV: `LTV = AOV × PurchaseFrequency × RetentionMultiplier` where `RetentionMultiplier = 1 + α₁·trust + α₂·value + α₃·context_fit − α₄·friction`
- Monte Carlo: repeat scenario N times with stochastic noise → return mean, p10, p50, p90 revenue + risk bands

**4-Layer execution model:**
- **State Model** — hidden-variable digital twin for user, org, and platform-aggregate scope; estimated from real signal via state_estimator
- **Interaction Model** — every touchpoint (landing page, pricing surface, sales call, gamification event, gignet local-node behavioral capture, support contact, etc.) registered in an interaction catalog with measured `ΔI` effect vector, estimated cost, and confidence
- **Transformation Engine** — deterministic application of `(state, interaction) → new_state` under governed decision-engine certificates; auditable provenance
- **Simulation Layer** — Monte Carlo / probabilistic forecasting predicting how the system evolves under proposed interactions before committing capital. **This is the PPEME Master Calculator.**

**Engine implementation map:**
- State Model → `user-access-engine` (canonical persona + org persona) + `intelligence-silo` (memory partitions) + PPEME `state_estimator`
- Interaction Model → `gignet-local-node` (behavioral capture) + Carmen Beach engagement surfaces + gamification event stream consumed by `human-management-engine` + PPEME `interaction_catalog`
- Transformation Engine → `decision-engine` (decision certificates with QC→VC→TC→EC chain) + `cxguy-methodology` (Trust × Value × Priority ranker)
- Simulation Layer → **`ppeme` Master Calculator** (Cloud Run service in `gigaton-platform`, `/v1/scenarios/simulate` + `/v1/forecasts`)

**Mantra alignment:** Operationalizes the Connect–Create–Thrive–Evolve cycle by making "Thrive" mathematically forward-simulatable rather than retrospectively measured.

**Substrate dependency:** BFT operates on the SMEN substrate (§5.18). The persistent bi-directional intelligence layer SMEN defines provides the state signal BFT estimates against. Without SMEN, BFT has nothing to read; without BFT, SMEN has no forward-simulation surface. They are paired.

**Falsifiability + production-grade threshold:** The doctrine is correct iff Master Calculator predictions converge on observed outcomes. Production-grade is reached when predicted-vs-actual variance has `p50 ≤ 15%` over a 30-day window for a calibrated decision class. Decision classes below threshold are flagged as *pre-Mtheory* and must not be cited as forecast authority.

**Anti-patterns it rules out (drift-sentinel rule additions):**
- `decision_without_state_estimate` — any decision certificate of class D2–D6 produced without an attached state vector estimate from a registered state_estimator → MAJOR drift
- `interaction_without_effect_vector` — any production interaction surfaced to users without a registered entry in the interaction catalog → MINOR drift on first sight, MAJOR if >30 days uncatalogued
- `forecast_without_confidence_bands` — any forecast cited in a decision certificate that lacks `{p10, p50, p90}` distribution → MAJOR drift
- `state_vector_substitution` — any code or spec asserting a state vector that does not match the canonical 9 variables → CRITICAL drift (requires amendment)
- `uncalibrated_forecast_as_authority` — a forecast from a decision class still in pre-Mtheory status (variance > p50 15% over 30 days) cited as authoritative input → MAJOR drift
- `interaction_without_cost` — interaction entry missing `estimated_cost` field; recommendation panel cannot rank without it → MINOR drift

**How to audit conformance:**
1. Every Decision Certificate of class D2–D6 should expose `state_vector_at_decision` (9 floats, 0–1) and, where forecast-attached, `forecast: {p10, p50, p90, distribution_method, model_version, confidence}`
2. Every interaction surface in `gigaton-ui-system` should resolve to an `interaction_id` in PPEME's interaction catalog with a non-null `delta_i` and `estimated_cost`
3. PPEME's calibration table should carry versioned weight history with WHY (per always-record-WHY); each version tagged with calibration window and decision class
4. Drift Sentinel weekly scan walks decision-engine certificates + interaction catalog + calibration history + gigaton-ui-system touchpoints; emits anti-pattern signals above
5. Sunday weekly initiative report includes a "Forecast accuracy" line per calibrated decision class (predicted vs actual, current variance)

**Why this is binding doctrine:** Anchors §5.16's predictable-profitability thesis to a falsifiable, measurable mechanism. Without BFT as canonical doctrine, decision certificates drift toward retrospective scoring (which we already have via §5.2 Value Matrix and §5.3 Trust Matrix) without forward simulation. The platform's strategic claim is that we can predict outcomes — that claim is correct only if there is a doctrinally-required forward-simulation step. Promoted to canonical 2026-05-13 by Todd / Matt / Bella triad sign-off; previously articulated 2026-05-09 (mtheory_business_field_theory.md) and operationalized 2026-05-12 (BFT package ingest) but not yet binding.

**Source:** `claude_business_field_theory_package/docs/business_field_theory.md`, `ppeme/docs/{business_field_theory.md, equations.md, data_mapping.md}`, working Python at `claude_business_field_theory_package/code/business_field_theory_simulation.py`. Memory cross-references: `mtheory_business_field_theory.md`, `bft_package_integration_plan.md`, `predictably_profitable_experience_management_engine.md`, `framework_5_19_bft_amendment.md`.

---

## 6. RUNTIME GOVERNANCE (REQUIRED FOR PRODUCTION)

Every production decision system must have:
1. **Versioned prompts** — `prompt_version` on every decision record
2. **Schema-versioned payloads** — `schema_version` attached
3. **Audit logging** — all decisions logged with inputs + outputs (12+ entries minimum)
4. **Exception analytics** — types tracked and classified; ≥3 recurrences → codification candidate
5. **Release governance** — approval gate before prompt activation in prod
6. **HMAC trust certificates** — disk-backed `.md` audit trail; signature validated on every load

---

## 7. ARCHITECTURAL COMMITMENTS (DOCTRINE-BACKED STACK CHOICES)

These choices ARE the philosophy made physical. Deviating from them without explicit reason = drift.

| Layer | Commitment | Why |
|---|---|---|
| API | FastAPI | Structured, auto-documented, async-native |
| DB | PostgreSQL (prod) / SQLite (local) | ACID + relational + cheap local dev |
| Frontend | Next.js 14 (App Router, RSC, streaming) | SEO-first SSR, colocated API routes |
| ORM | Prisma (TS) | Declarative, no raw SQL drift |
| Monorepo | pnpm + Turborepo | Workspace coherence, build ordering |
| Container | Docker (multi-stage) | Reproducible deploys |
| Cloud | GCP (Cloud Run, Cloud SQL, GCS, Secret Manager, Artifact Registry, Cloud Build) | Single-vendor coherence |
| CI | GitHub Actions + Cloud Build | Declarative, auditable |
| Type Safety | TypeScript strict mode (no `any`) | Clarity reduces entropy (Principle #9) |
| Lang (intel) | Python 3.11+ | Determinism, governance, scale |
| Storage | Provider abstraction always (local→GCS swap) | No vendor lock |
| AI Provider | `provider` + `model` fields required | Provider-agnostic interface |
| Style | Prettier (single quotes, no semi, trailing comma all, 100 char) | Non-negotiable for merge |
| Testing | Local dev must always work without cloud credentials | Sovereignty |

---

## 8. DECISION ROUTING DECISION TREE

For every recurring decision, the operator must classify:

```
input_structure ∈ {structured, semi, unstructured}
logic_clarity ∈ {explicit, partial, ambiguous}
rule_stability ∈ {stable, evolving, unknown}
decision_volume ∈ {low, medium, high}
latency_sensitivity ∈ {low, medium, high}
auditability_requirement ∈ {none, preferred, required}
error_cost ∈ {low, medium, high}
exception_frequency ∈ {rare, occasional, frequent}
codification_readiness ∈ {ready, partial, not-ready}
```

Routing:
- **Python-First:** structured + explicit + stable + high volume + audit required
- **Claude-First:** ambiguous + interpretive + exploratory + edge-case-heavy
- **Hybrid (preferred for prod):** Claude parses → Python decides; Python defaults → Claude fallback

**Codification trigger:** ≥50 executions of same decision type with stable outcomes AND <5% exception rate → migrate to Python.

---

## 9. THE COMMAND HIERARCHY

When principles conflict (and they will), this is the precedence order:

1. **Non-negotiable doctrine** (the 7)
2. **Safety, legality, ethics, human agency**
3. **First principles** (the 15)
4. **Org ethos** (the 8 filters)
5. **Value matrix score**
6. **Trust certificate status**
7. **Tactical speed / convenience**

Higher beats lower. Always. No exceptions.

---

## 10. THE OUTCOME ESTIMATION FORMULA

```
Priority Score = Base × Time_Leverage × Strategic_Alignment × Ethos_Alignment × Trust_Multiplier × RTQL_Multiplier

Base = (Expected_Value − Total_Cost − Risk_Penalty) × Probability_of_Success
Trust_Multiplier ∈ {T0: 0.2, T1: 0.5, T2: 0.8, T3: 1.0, T4: 1.2}
RTQL_Multiplier  ∈ {noise: 0.0, weak: 0.35, echo: 0.5, qualified: 1.0 ... axiom: 2.0}
```

Outcome confidence by verdict: `AUTO_EXECUTE 85-95% | ESC_T1 70-85% | ESC_T2 55-75% | ESC_T3 40-65% | BLOCK <30%`.

---

## 11. WHAT THE DRIFT SENTINEL CHECKS AGAINST THIS DOC

The Drift Sentinel runs **recursive checks** across:
- Local codebases (`/Users/admin/Documents/GitHub/`)
- GitHub remote (gig-todd account + ti-cx + entity orgs)
- Google Drive (4 accounts mapped in Entity Registry)
- Local docs (`/Users/admin/Downloads/`, `/Users/admin/Documents/`)
- ClickUp (workspace tasks, lists, docs)

For each source, it asks:
1. Does this artifact reference the **canonical frameworks** correctly (no contradiction, no rebuild-from-scratch)?
2. Does it violate any of the **anti-patterns** listed in §4?
3. Does it satisfy **runtime governance** requirements (§6) if it's a production system?
4. Does it conform to **architectural commitments** (§7) if it's code?
5. Does it follow the **command hierarchy** (§9) when principles conflict?
6. If a decision/plan/PR — is it **auditable from axiom to outcome** per the conical proof method (§5.11)?

**Drift severity:**
- **CRITICAL** — violates a non-negotiable or hard-stop anti-pattern → block deployment / require remediation
- **MAJOR** — drifts from a core principle or framework → flag for review
- **MINOR** — stylistic or tactical deviation from architectural commitment → log and track
- **INFO** — documents an intentional exception (must reference an approved override)

---

## 12. SOURCES OF TRUTH (REFERENCED, NOT DUPLICATED)

| Topic | Authoritative File |
|---|---|
| Full doctrine + thresholds | [`MASTER_FIRST_PRINCIPLES_REFERENCE.md`](../MASTER_FIRST_PRINCIPLES_REFERENCE.md) |
| Decision schema | [`schemas/decision_schema.yaml`](../schemas/decision_schema.yaml) |
| RTQL standalone | `MD Files/decision-logic-and-rtql/Recursive_Trust_Qualification_Loop_RTQL_standalone.md` |
| Claude automation v3.2 | `MD Files/claude-automation-thread-package/` |
| Sales OS agentic | `MD Files/sales-operating-system-agentic/` |
| SIE bundle | `Downloads/gigaton_sie_first_production_bundle_v1/` |
| Gigaton language repo | `Downloads/gigaton_claude_custom_language_repo_v3/` |
| Attractor Dynamix | `MD Files/chatgpt-gigaton/gigaton-and-liquifex/ChatGPT MD -Attractor Dynamix Constitution.md` |
| Gigaton Value Matrix | `MD Files/chatgpt-gigaton/gigaton-and-liquifex/ChatGPT MD -Gigaton Value Matrix.md` |
| Symbiotic Memory-Experience Network (SMEN) | `MD Files/chatgpt-gigaton/research-and-concepts/ChatGPT MD -Symbiotic Memory-Experience Network origin.md` |
| Carmen Beach platform | `Carmen-Beach-Properties/` |

If any of these files **contradict** this canonical doc, the canonical doc wins until the contradiction is resolved by explicit governance review (§19 of the Master Reference).

---

*Last reconciled: 2026-05-13 (added Framework 5.19 Business Field Theory / Mtheory Math — promoted from canonical methodology + working implementation to binding canonical doctrine per Todd/Matt/Bella triad sign-off under governance bootstrap protocol v0; previously articulated 2026-05-09 in `mtheory_business_field_theory.md` and operationalized 2026-05-12 via `claude_business_field_theory_package` ingest). Prior reconciliation 2026-05-08 (Framework 5.18 SMEN). Re-run synthesis after any major framework version bump (Claude automation thread package version, MASTER_FIRST_PRINCIPLES_REFERENCE schema version).*
