# Gigaton Platform — Master Architecture Document

> **One sentence:** A connected stack of four intelligence systems that converts raw decisions, market data, and customer interactions into compounding, margin-governed, auditable outcomes.

---

## TABLE OF CONTENTS

1. [System Overview Map](#1-system-overview-map)
2. [Decision Engine](#2-decision-engine)
3. [Intelligence Silo](#3-intelligence-silo)
4. [Gigaton Engine](#4-gigaton-engine)
5. [Sales Operating System](#5-sales-operating-system)
6. [Inter-System Connections](#6-inter-system-connections)
7. [Master First Principles Registry](#7-master-first-principles-registry)
8. [How Each Principle Applies to Each System](#8-how-each-principle-applies-to-each-system)

---

## 1. SYSTEM OVERVIEW MAP

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GIGATON PLATFORM STACK                              │
├──────────────────────┬─────────────────────────────┬────────────────────────┤
│   DECISION ENGINE    │    INTELLIGENCE SILO         │   GIGATON ENGINE       │
│   (Python, FastAPI)  │    (PyTorch, FastAPI)        │   (Python, FastAPI)    │
│   Port 8000          │    Port 8080                 │   Port 8001            │
│   CPU / Cloud Run    │    CPU / Cloud Run 4Gi       │   CPU / Cloud Run      │
│                      │                              │                        │
│  13-stage pipeline   │  Society of Minds + 6 SLMs   │  Pricing + Margin DAG  │
│  22-field schema     │  4-layer memory hierarchy     │  Multi-agent triggers  │
│  7-gate auth         │  57.2M params                │  Playa del Carmen ROI  │
│  RTQL classification │  FAISS semantic index        │  Real-time events      │
└──────────┬───────────┴──────────────┬──────────────┴────────────┬───────────┘
           │    weights / predictions  │                           │  pricing
           │◄─────────────────────────┤                           │  quotes
           │                          │                           │
           │          ┌───────────────▼───────────────────────────▼──────┐
           └─────────►│         SALES OPERATING SYSTEM                   │
                       │         (Python, FastAPI, SQLite)                │
                       │         Port 8003 / Cloud Run                    │
                       │                                                  │
                       │  Lead scoring · Opportunity pipeline             │
                       │  Pricing bridge · Interaction tracking           │
                       │  Score = (Interaction_Value×0.6)+(Mktg×0.4)     │
                       └──────────────────────────────────────────────────┘
```

| System | Role in Stack | Primary Output |
|--------|---------------|----------------|
| **Decision Engine** | Cognitive arbiter — evaluates every decision through ethical, value, and trust filters | `PipelineResult` with verdict, priority score, audit trail |
| **Intelligence Silo** | Long-term neural memory and pattern recognition | Learned weights, consensus signals, causal predictions |
| **Gigaton Engine** | Financial engine — governs pricing, margin, and market causality | Margin-compliant prices, ROI scenarios, agent triggers |
| **Sales Operating System** | Customer-facing pipeline — scores leads, tracks opportunities, routes to pricing | Scored leads, opportunity decisions, priced proposals |

---

## 2. DECISION ENGINE

### 2.1 Summary

The Decision Engine is the cognitive backbone of the platform. It enforces a structured, auditable methodology for every consequential decision — from a sales opportunity qualification to a resource allocation or strategic pivot. Nothing gets executed without passing through its 13-stage pipeline.

**Stack:** Python 3.12 · FastAPI · SQLite · YAML-configured weights  
**Deployment:** Cloud Run (port 8000) · `--no-allow-unauthenticated`  
**Scale:** CPU-only, ~512MB RAM  
**Config:** `config/engine.yaml` defines all weights, thresholds, multipliers  

### 2.2 Process Methodology — 13-Stage Pipeline

```
STAGE 1  → Input Validation
           Required: 22+ fields on DecisionObject. Missing critical fields = immediate reject.

STAGE 1.5→ Missing Data / Ethical Pre-Check
           has_missing_data flag routes to needs_data state.
           ethical_conflict flag routes to blocked state (no gate can override).

STAGE 2  → RTQL Pre-Filter (Recursive Trust Qualification Loop)
           Classifies input across 9 stages:
             noise → weak_signal → echo_signal → qualified → certification_gap
             → certified → research_grade → first_principles_candidate → axiom_candidate
           Trust multiplier applied to raw value score:
             noise=0.00, weak_signal=0.35, echo_signal=0.50, qualified=1.00,
             certified=1.15, research_grade=1.30, first_principles_candidate=1.50

STAGE 3  → Value Assessment
           Raw value computed across 8 dimensions with asymmetric weights:
             revenue_impact(1.5) · cost_efficiency(1.2) · time_leverage(1.3)
             strategic_alignment(2.0) · customer_benefit(1.4) · knowledge_creation(1.1)
             compounding_potential(1.8) · reversibility(1.0)
           Weighted value formula: Σ(dimension_score × weight) × rtql_multiplier
           Thresholds: execute ≥ 14.0 · escalate ≥ 8.0

STAGE 4  → Trust Assessment
           T0–T4 tier from trust dimensions:
             track_record · consistency · evidence_quality · skin_in_game
             stakeholder_clarity · communication_quality
           Trust multiplier: T0=0.2, T1=0.5, T2=0.8, T3=1.0, T4=1.2
           Thresholds: execute ≥ 3.5 · recommend ≥ 2.2

STAGE 5  → Authority Check
           Decision class (D1–D5) matched against authority_matrix.
           Minimum trust tier required per class; insufficient trust = escalate.

STAGE 6  → Alignment Check
           Ethos filter: checks stakeholder incentives, cultural alignment,
           anti-pattern detection (optics_over_substance, complexity_without_leverage,
           undefined_ownership, automation_without_human_override)

STAGE 7  → Certificate Chain
           4-certificate sequence: QC → VC → TC → EC
             QC (Quality Control)  — completeness, format, required fields
             VC (Value Certificate) — value score ≥ threshold
             TC (Trust Certificate) — trust tier ≥ threshold
             EC (Ethics Certificate) — no ethical conflict, alignment pass
           All 4 must pass. Any failure = block.

STAGE 8  → 7-Gate Authorization
           Gate 1: Value floor       — weighted_value ≥ execute_min
           Gate 2: Trust floor       — trust_tier ≥ execute_min
           Gate 3: Authority         — role can execute decision class
           Gate 4: Human override    — automation path has override mechanism
           Gate 5: Risk cap          — downside_risk ≤ 3 (hard cap)
           Gate 6: Alignment         — ethos filter passed
           Gate 7: Certificate       — all 4 certificates valid
           All 7 must pass for EXECUTE verdict. Partial pass → RECOMMEND or ESCALATE.

STAGE 9  → State Machine Transition
           Valid states: draft → under_review → approved → executing → completed
                        draft → rejected
                        approved → on_hold
           Transitions validated against state_machine config.

STAGE 10 → Priority Scoring
           Priority = Base × Time_Leverage × Strategic_Alignment
                      × Ethos_Alignment × Trust_Multiplier × RTQL_Multiplier
           Produces a sortable priority queue for execution routing.

STAGE 11 → ROI Assessment
           ROI = (Impact_Value / Total_Cost) × (1 + Leverage_Factor) × (1 - Risk_Factor)
           Pass threshold: ROI ≥ 1.5

STAGE 12 → Execution Routing
           Based on verdict: EXECUTE / RECOMMEND / ESCALATE / BLOCK / NEEDS_DATA
           Routes to appropriate handler, queues for intelligence silo auto-record.

STAGE 13 → Audit Trail Assembly
           Full AuditRecord per stage. Generates executive_summary.
           Persists to decision journal.
```

### 2.3 Key Subsystems

| Subsystem | File | Role |
|-----------|------|------|
| RTQL Classifier | `engine/rtql_classifier.py` | 9-stage trust qualification for every input |
| Weighted Scoring | `engine/weighted_scoring.py` | Asymmetric dimension scoring |
| OVS Engine | `engine/ovs_engine.py` | Organizational Vitality Score: `(People×0.30)+(Process×0.25)+(Technology×0.25)+(Learning×0.20)×100` |
| Learning Loop | `engine/learning_loop.py` | Captures outcome variance, updates trust tier, feeds patterns to silo |
| Gap Analysis | `engine/gap_analysis.py` | Identifies structural gaps between current and target state |
| Governance Gates | `engine/governance_gates.py` | 30/60/90-day review triggers |

---

## 3. INTELLIGENCE SILO

### 3.1 Summary

The Intelligence Silo is the platform's neural memory and inference layer. Where the Decision Engine applies explicit rules and weighted formulas, the Silo learns implicit patterns from decision history. It runs a Society of Minds architecture — 7 specialized cognitive agents orchestrating 6 small language models (SLMs) — and accumulates knowledge in a 4-layer memory hierarchy.

**Stack:** Python 3.11 · PyTorch 2.2 (CPU) · FAISS · FastAPI  
**Deployment:** Cloud Run (port 8080) · 4Gi RAM · 2 CPU · min-instances=0  
**Scale:** 57.2M parameters across 6 SLMs  
**Config:** `config/silo.yaml` — all memory, model, and bridge settings  

### 3.2 Process Methodology — Society of Minds Cycle

```
INPUT
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│                   SOCIETY OF MINDS ORCHESTRATOR              │
│                                                              │
│  1. Perceiver     — Structures raw input into typed context  │
│  2. Analyst       — Routes to SLM matrix, scores dimensions  │
│  3. Critic        — Challenges proposals, checks consistency │
│  4. Synthesizer   — Builds consensus from multi-model output │
│  5. Executor      — Plans concrete action steps              │
│  6. Memory Keeper — Consolidates new knowledge to memory     │
│  7. Sentinel      — Monitors for anomalies, trust drift      │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│                        SLM MATRIX                           │
│                                                              │
│  classifier      (256 hidden · 4L · 4H · 32 classes)        │
│    → Classifies input into one of 32 decision categories     │
│                                                              │
│  scorer          (256 hidden · 4L · 4H · 12 output dims)    │
│    → Predicts 8 value + 4 penalty scores                     │
│                                                              │
│  trust_assessor  (192 hidden · 3L · 4H · 5 classes)         │
│    → Assigns T0–T4 trust tier from context signals           │
│                                                              │
│  memory_encoder  (384 hidden · 6L · 6H · encoder)           │
│    → Produces 384-dim embeddings for memory storage          │
│                                                              │
│  pattern_detector(256 hidden · 4L · 4H · 64 classes)        │
│    → Detects one of 64 recurring patterns in decision history│
│                                                              │
│  causal_predictor(384 hidden · 6L · 6H · 16 output dims)    │
│    → Predicts 16-dim causal chain with downstream effects    │
│                                                              │
│  Router: attention-based, weighted_vote fusion               │
│  Confidence floor: 0.6 (below = defer to deliberate mode)   │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│                    MEMORY HIERARCHY                          │
│                                                              │
│  Working    — 128 active slots · tensor-backed · TTL 300s    │
│               4 attention heads for relevance scoring        │
│                                                              │
│  Episodic   — Max 10,000 episodes · 384-dim embeddings       │
│               Cosine similarity threshold: 0.72              │
│               Consolidation sweep every 60 seconds           │
│                                                              │
│  Semantic   — FAISS IVFFlat index · up to 1M vectors         │
│               384-dim · nprobe=16 · persisted to /data       │
│                                                              │
│  Procedural — Max 5,000 learned procedures                   │
│               Auto-execute threshold: 0.85 confidence        │
│               Learning rate: 0.001                           │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│                 AUTOMATED RETRAINING                         │
│                                                              │
│  Trigger: ≥50 new decisions AND ≥6 hours since last run     │
│  Epochs per triggered run: 60                               │
│  Synthetic samples per run: 1,000 (alongside real data)      │
│  Device: auto (MPS > CUDA > CPU)                             │
│  Checkpoints: /data/checkpoints                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 10 Intelligence Dimensions

The Silo tracks performance across 10 dimensions. Four require AUTO_EXEC confidence ≥ 0.5:

| Dimension | Weight | AUTO_EXEC Required |
|-----------|--------|--------------------|
| subject | 0.08 | No |
| training | 0.09 | No |
| education | 0.08 | No |
| science | 0.10 | No |
| **knowledge** | **0.12** | **Yes (≥ 0.5)** |
| **strategy** | **0.13** | **Yes (≥ 0.5)** |
| success | 0.10 | No |
| tools | 0.09 | No |
| **information** | **0.11** | **Yes (≥ 0.5)** |
| **experience** | **0.10** | **Yes (≥ 0.5)** |

### 3.4 Cloud Run Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SILO_DATA_DIR` | Redirects all data paths to mounted volume | `data/` |
| `VAULT_DISABLED` | Swaps `SecureVault` for `_NullVault` (reads from env) | `false` |
| `VAULT_PASSPHRASE` | Stable passphrase bypassing machine-bound derivation | — |
| `DECISION_ENGINE_URL` | Override bridge URL for Cloud Run service mesh | `http://localhost:8000` |
| `SILO_CONFIG_PATH` | Override config file path | `config/silo.yaml` |

---

## 4. GIGATON ENGINE

### 4.1 Summary

The Gigaton Engine is the financial reasoning layer. It governs how revenue is priced, how margins are protected, and how market causal relationships compound into ROI outcomes. Its margin constraints are the final word on whether a price is defensible — no sale goes through at a margin below the configured floor.

**Stack:** Python 3.x · FastAPI · Pydantic  
**Deployment:** Cloud Run (port 8001) · `--no-allow-unauthenticated`  
**Primary domain:** Playa del Carmen short-term rental property optimization  

### 4.2 Process Methodology — 4 Engines

#### Engine 1: Pricing Engine (`/pricing/*`)

```
Input: PricingRequest
  ├── pricing_type: flat | tiered | subscription | usage | hybrid
  ├── cost breakdown: 7 cost dimensions
  ├── margin targets: min_acceptable_margin (default 20%), target_gross_margin (50%)
  │                   target_contribution_margin (40%)
  └── discount rules + contract terms

Processing:
  1. Compute total cost from CostInputs
  2. Calculate floor price = total_cost / (1 - min_acceptable_margin)
  3. Apply pricing_type logic (tiers, subscriptions, usage-based)
  4. Apply discount rules respecting max_discount (default 30%)
  5. Validate final price ≥ floor price

Output: PricingResult
  ├── recommended_price
  ├── floor_price (never go below)
  ├── gross_margin, contribution_margin
  ├── margin_ok (bool — key guard for SalesOS)
  └── applied_discounts
```

#### Engine 2: Margin Optimization + DAG (`/margin/*`)

The Playa del Carmen Causal DAG implements 5 structural equations:

```
Equation 1 — Conversion Rate (logistic):
  log_odds = -3.5
            + 0.25 × lead_quality_score
            - 1.20 × listing_price_relative
            - 0.03 × response_time_min
            + 0.20 × media_quality_index
  conversion_rate = sigmoid(log_odds)

Equation 2 — Occupancy Rate (linear):
  occupancy = 0.40
            + 0.000008 × marketing_impressions
            + 0.60 × conversion_rate
            + 0.015 × avg_length_of_stay
            - 0.08 × market_supply_index

Equation 3 — Nightly Rate Realized:
  nightly_rate = base_nightly_rate × seasonality_index
                 × (1 + seasonality_premium) × (1 + quality_premium)

Equation 4 — Monthly Gross Revenue:
  monthly_revenue = occupancy × nights_per_month × nightly_rate_realized

Equation 5 — Net Profit:
  contribution_margin = monthly_revenue × (1 - variable_cost_rate)
  net_profit = contribution_margin - fixed_costs_monthly

Channel Scenario Uplift:
  Baseline (1 channel):              45% occupancy
  Manual multi-channel (3 channels): +5% per additional channel
  Gigaton orchestrated (6 channels): +10% AI coordination uplift
  Result: 70%+ occupancy under full Gigaton orchestration
```

#### Engine 3: Multi-Agent Coordination (`/agents/*`)

Agents respond to market signals, execute pricing recommendations, and coordinate channel-specific actions. Claude Enrichment provides AI-assisted lead enrichment and scoring via `claude_enrichment.py`.

#### Engine 4: Trigger Engine (`/events/*`)

Real-time event processing. Fires triggers on: occupancy thresholds, pricing drift, lead volume changes, margin compression. Feeds events back to the multi-agent coordinator and — via bridge — to the Decision Engine.

### 4.3 Margin Levers

| Dimension | Impact Speed | Risk Level |
|-----------|-------------|------------|
| Direct cost reduction | fast | low |
| Pricing optimization | fast | medium |
| Channel mix shift | medium | low |
| Occupancy rate lift | medium | medium |
| Average nightly rate lift | slow | medium |
| Fixed cost restructuring | slow | high |

---

## 5. SALES OPERATING SYSTEM

### 5.1 Summary

The Sales Operating System is the customer-facing intelligence layer. It manages the complete lead-to-close pipeline: scoring inbound leads, tracking opportunity stages, providing margin-governed pricing, and maintaining a searchable record of every interaction and decision. It consumes outputs from all three upstream systems.

**Stack:** Python 3.12 · FastAPI · SQLite (persistent at `/data/sales_os.db`)  
**Deployment:** Cloud Run (port 8003) · `--no-allow-unauthenticated`  
**Scale:** 512Mi RAM · 1 CPU  

### 5.2 Process Methodology

#### Lead Scoring

```
Score = ROUND((Interaction_Value × 0.6) + (Marketing_Influence × 0.4), 2)

  Interaction_Value — quality and recency of direct engagement
  Marketing_Influence — channel attribution, campaign effectiveness, reach

Score ranges:
  0.00–0.39: Low — nurture only
  0.40–0.69: Medium — active follow-up
  0.70–0.89: High — priority pipeline
  0.90–1.00: Hot — immediate executive attention
```

#### Opportunity Pipeline Stages

```
STAGE 1: Lead Identified        — Initial contact recorded, score computed
STAGE 2: Qualified              — RTQL-style qualification; trust and value assessed
STAGE 3: Proposal               — Pricing requested from Gigaton Engine; margin verified
STAGE 4: Negotiation            — Counter-proposals within margin floor
STAGE 5: Decision               — Full pipeline decision submitted to Decision Engine
STAGE 6: Closed Won / Lost      — Outcome recorded; learning loop triggered
```

#### Pricing Integration

```
SalesOS → Gigaton Engine (POST /pricing/calculate)

Request contains:
  ├── pricing_type, base_price, costs (7 dimensions)
  ├── min_acceptable_margin (inherited from product config)
  └── discount_rules, contract_term_months

Response:
  ├── recommended_price
  ├── floor_price (hard minimum)
  ├── gross_margin, margin_ok
  └── CostBreakdown with totals

Margin guard: if margin_ok = false → reject quote, do not present to customer
Degradation: if Gigaton Engine unreachable → SalesOS uses product.base_price as fallback
             is_available() check: status == "ok" AND version == "1.0.0"
```

#### API Surface

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health + db stats |
| `/leads` | GET/POST | Lead management |
| `/leads/{id}/score` | POST | Recompute lead score |
| `/opportunities` | GET/POST | Opportunity pipeline |
| `/opportunities/{id}` | GET/PATCH | Opportunity detail + updates |
| `/opportunities/{id}/pricing` | POST | Batch pricing via Gigaton Engine |
| `/gigaton/status` | GET | Gigaton Engine availability check |
| `/pricing/quote` | POST | Single pricing quote |
| `/interactions` | POST | Record a customer interaction |

---

## 6. INTER-SYSTEM CONNECTIONS

### 6.1 Dependency Map

```
                    ┌───────────────────────────────────────────┐
                    │           CONNECTION TYPES                │
                    │  → HTTP/REST (synchronous)                │
                    │  ⇢ Weights import (file/config)           │
                    │  ↻ Learning feedback (async)              │
                    └───────────────────────────────────────────┘

Decision Engine ─────────────────────────────────────────────────────────────┐
  │                                                                          │
  ├─→ Intelligence Silo                                                      │
  │     POST /decisions/record — every processed decision auto-recorded      │
  │     GET /process — neural inference during deliberate mode               │
  │     GET /matrix/info — model performance telemetry                       │
  │                                                                          │
  ├─→ Sales Operating System                                                 │
  │     SalesOS submits stage-5 opportunities to DE /api/decisions           │
  │     DE verdict (EXECUTE/RECOMMEND/BLOCK) gates the close                 │
  │                                                                          │
  └─↻ Intelligence Silo (learning)                                           │
        Silo exports neural weights → DE imports via bridge.import_weights   │
        DE outcome variance → Silo learning loop via bridge.export_predictions│

Intelligence Silo ────────────────────────────────────────────────────────────┤
  │                                                                           │
  ├─⇢ Decision Engine                                                         │
  │     bridge.import_weights: true  pulls value_weights/penalty_weights     │
  │     from config/engine.yaml on startup                                   │
  │                                                                           │
  ├─↻ Decision Engine                                                         │
  │     bridge.export_predictions: true  pushes SLM outputs back to DE       │
  │     sync_interval: 30 seconds                                            │
  │                                                                           │
  └─→ GCS (optional)                                                          │
        Shared semantic memory sync across distributed silo nodes             │
        mesh_discovery: mdns (local) or gcs_registry (cloud)                 │

Gigaton Engine ────────────────────────────────────────────────────────────────┤
  │                                                                            │
  └─→ Sales Operating System                                                   │
        POST /pricing/calculate ← SalesOS GigatonPricingClient                │
        Called for every proposal and opportunity pricing request              │
        SalesOS env var: GIGATON_ENGINE_URL                                    │
        Identity check: version == "1.0.0" prevents false positive            │

Sales Operating System ─────────────────────────────────────────────────────────┘
  │
  ├─→ Decision Engine
  │     Submits qualified opportunities for full pipeline evaluation
  │
  └─→ Gigaton Engine
        Calls /pricing/calculate for margin-verified quotes
        Calls /margin/dag for ROI scenario analysis
```

### 6.2 Data Flow — A Deal from Lead to Close

```
1. Lead arrives → SalesOS records interaction
                  Score = (Interaction_Value×0.6) + (Marketing_Influence×0.4)

2. Lead qualifies → SalesOS creates Opportunity
                    Stage: Qualified

3. Proposal needed → SalesOS → Gigaton Engine /pricing/calculate
                     Gigaton returns: recommended_price, floor_price, margin_ok
                     If margin_ok=false: SalesOS rejects quote internally

4. Opportunity advances → SalesOS → Decision Engine /api/decisions
                           DE runs 13-stage pipeline:
                             RTQL classification of the deal context
                             Value scoring (strategic_alignment × 2.0 for key deals)
                             Trust assessment of stakeholders
                             7-gate authorization
                           DE verdict: EXECUTE → deal proceeds
                                       RECOMMEND → human review required
                                       BLOCK → deal killed

5. Decision recorded → DE → Intelligence Silo /decisions/record
                        Silo: encodes to 384-dim embedding
                              stores in episodic memory
                              updates semantic index
                              triggers retraining if ≥50 new decisions

6. Retrain fires → Silo updates SLM weights
                   Silo pushes updated predictions to DE bridge
                   DE imports updated weights on next sync (30s interval)

7. Next similar deal → Silo's pattern_detector recognizes pattern
                       causal_predictor estimates downstream effects
                       trust_assessor pre-scores stakeholders
                       → Better, faster decisions on every cycle
```

### 6.3 Service-to-Service Auth

All services run `--no-allow-unauthenticated` in Cloud Run. Internal traffic uses `--ingress=internal-and-cloud-load-balancing`, allowing Cloud Run services within the same project to call each other without identity tokens on every request.

---

## 7. MASTER FIRST PRINCIPLES REGISTRY

These principles are extracted from the shared doctrine across all four systems. They are not guidelines — they are enforced constraints or scored dimensions in the code.

### 7 Non-Negotiables (Immutable)

| # | Principle | Enforcement Level |
|---|-----------|------------------|
| **N1** | **Human agency first** — every automated path has a human override | Code: Gate 4 hard check · anti-pattern: `automation_without_human_override` |
| **N2** | **Ethical technology use** — ethics violations are terminal | Code: `ethical_misalignment` penalty weight = 3.0x (highest of all weights) |
| **N3** | **Truth-seeking over politics** — authority cannot override evidence | Code: RTQL removes authority bias; Gate 3 checks role, not seniority |
| **N4** | **Compounding long-term value over vanity** — flywheels beat isolated wins | Code: `compounding_potential` weight = 1.8x; OVS tracks flywheel health |
| **N5** | **Clarity over ambiguity** — incomplete data blocks execution | Code: 22-field required schema; missing fields = Stage 1 reject |
| **N6** | **Evidence over assumption** — claims require provenance | Code: RTQL requires identifiable source; trust promotion guards |
| **N7** | **Reusable systems over one-off effort** — every outcome teaches the system | Code: learning loop auto-codifies patterns; `knowledge_asset_creation` scored |

### 15 Core Principles

| # | Principle | Category |
|---|-----------|----------|
| **P1** | Reality before preference — decisions map to observable constraints | TRUTH |
| **P2** | Value is relational — relative to stakeholder, objective, time horizon | VALUE |
| **P3** | All resources are finite — time, capital, attention, trust, bandwidth | CONSTRAINTS |
| **P4** | Speed matters when opportunity decays — delayed action destroys value | SPEED |
| **P5** | Trust is earned through repeated validated outcomes | TRUST |
| **P6** | Every system has incentives — identify before deciding | ALIGNMENT |
| **P7** | Risk is asymmetrical — downside ≠ upside | RISK |
| **P8** | Compounding dominates isolated wins — prefer flywheels | COMPOUND |
| **P9** | The best decision is the one you can learn from | LEARNING |
| **P10** | Reversible decisions deserve more speed; irreversible deserve more care | REVERSIBILITY |
| **P11** | Margin is oxygen — protect it before revenue | MARGIN |
| **P12** | Local computation always has inherent advantages | LOCALITY |
| **P13** | Patterns repeat — the system that learns them wins | PATTERN |
| **P14** | Trust compounds or decays — never stays the same | TRUST DYNAMICS |
| **P15** | The map is not the territory — models are approximations, outcomes are truth | CALIBRATION |

### 5 Hard-Stop Anti-Patterns

Any decision exhibiting these patterns is blocked regardless of value or trust score:

| Anti-Pattern | Definition |
|-------------|------------|
| `optics_over_substance` | Decision optimizes for appearance, not measurable outcome |
| `complexity_without_leverage` | Solution is complex but produces no compounding return |
| `undefined_ownership` | No named accountable owner; diffuse responsibility |
| `automation_without_human_override` | Automated system cannot be overridden by a human |
| `vanity_metrics_as_proxy` | Success measured by impressions/followers/views, not value |

---

## 8. HOW EACH PRINCIPLE APPLIES TO EACH SYSTEM

| Principle | Decision Engine | Intelligence Silo | Gigaton Engine | Sales Operating System |
|-----------|----------------|-------------------|----------------|----------------------|
| **N1 Human agency first** | Gate 4 hard-blocks automation without override path | Procedural memory auto-exec only at ≥0.85 confidence; human can always override | Pricing recommendations are advisory; human sets margin floor | Scoring and quotes are advisory; salesperson owns the close |
| **N2 Ethical technology use** | `ethical_misalignment` = 3.0x penalty (terminal blocker at Stage 1.5) | Sentinel mind monitors for ethical drift in patterns | No price below cost enforced as code, not suggestion | Margin floor prevents predatory pricing regardless of discount pressure |
| **N3 Truth-seeking** | RTQL strips authority bias; `noise` stage = 0.00 multiplier | trust_assessor scores context signals, not job titles | DAG coefficients calibrated against real xlsx data, not assumptions | Lead scoring formula is explicit and auditable — not black box |
| **N4 Compounding value** | `compounding_potential` weight = 1.8x; OVS tracks flywheel | Memory hierarchy accumulates — each decision improves the next | Channel scenario: 6-channel Gigaton orchestration → 70%+ occupancy vs 45% baseline | Every interaction scored and stored; history informs future qualification |
| **N5 Clarity** | 22-field required schema; Stage 1 rejects incomplete objects | 384-dim embeddings force explicit representation; 64 pattern classes, not vague clusters | PricingRequest has typed fields for all 7 cost dimensions | OpportunityObject has explicit stage, score, pricing fields |
| **N6 Evidence** | RTQL requires provenance at `qualified` and above | memory_encoder stores experience with context; retrieval requires similarity ≥ 0.72 | DAG coefficients sourced from calibrated xlsx model, not estimates | Lead score formula traceable to two explicit inputs |
| **N7 Reusable systems** | Learning loop codifies every outcome into patterns | Procedural memory stores learned actions; reuse gated at 0.85 confidence | MarginLever library is reusable across properties; trigger engine is property-agnostic | SalesOS schema is domain-agnostic; the scoring formula works for any product |
| **P1 Reality** | RTQL Stage 1 "noise" = 0.00 multiplier (no decision on noise) | Causal predictor trained on real decisions, not synthetic alone | DAG uses logistic + linear regression on observed market data | Lead scoring uses actual interaction data, not assumed intent |
| **P3 Resources finite** | `cost_efficiency` (1.2x), `execution_drag` penalty (1.2x) | TTL-gated working memory (300s); episodic max 10,000 episodes | Fixed costs tracked monthly; trigger engine alerts on margin compression | SQLite + minimal deps; 512Mi RAM budget enforced in Cloud Run |
| **P4 Speed** | `time_leverage` weight = 1.3x; priority score amplifies time-sensitive decisions | Working memory TTL creates urgency gradient — fresh context scored higher | Trigger engine fires in real-time on occupancy/price events | Stage pipeline moves linearly; no re-review at completed stages |
| **P5 Trust** | T0→T4 promotion requires progressively stricter guards; T2+ for execution | trust_assessor as dedicated SLM; trust tier feeds memory retrieval priority | Agent trust levels determine which pricing levers agents can execute | Lead score threshold gates transition from nurture to active pipeline |
| **P7 Risk asymmetric** | `downside_risk` = 2.0x penalty; Gate 5 hard-caps downside_risk ≤ 3 | Pattern 64-class detector flags high-risk recurring patterns | `min_acceptable_margin` is a hard floor, not a suggestion | Pricing bridge returns `margin_ok=false` to SalesOS which rejects the quote |
| **P8 Compounding** | OVS People(0.30)+Process(0.25)+Tech(0.25)+Learning(0.20) tracks org flywheel | Each retrain incorporates all prior decisions; model improves monotonically | Channel scenario: each additional channel compounds occupancy lift | Each closed deal improves lead scoring for next similar deal |
| **P9 Learning** | Adaptive learning captures outcome variance, updates trust tiers | Automated retraining: ≥50 decisions triggers full retrain cycle | Margin lever library updated from observed channel outcomes | Learning loop: outcome variance at close feeds back to lead scoring weights |
| **P10 Reversibility** | `reversibility` is a value dimension (weight 1.0); state machine enforces approved→on_hold | Procedural memory at 0.85 threshold — irreversible actions require highest confidence | Contract term analysis in pricing engine; longer terms reduce reversibility | Opportunity stages are one-directional forward; rollback = new record |
| **P11 Margin** | `revenue_impact` (1.5x) and `cost_efficiency` (1.2x) together define margin health | Silo scores financial decisions using scorer SLM's penalty dimensions | Margin protection is the primary purpose of the entire engine | `floor_price` = `total_cost / (1 - min_acceptable_margin)` — enforced before any quote |
| **P12 Locality** | Local config (engine.yaml) as source of truth; remote only for audit | Local-first storage (FAISS on disk); GCS is a backup, not primary | Local computation for all DAG equations; no external API calls for math | SQLite local file at `/data`; no remote DB dependency |
| **P13 Pattern** | Learning loop codifies patterns from decision history | pattern_detector SLM: 64 pattern classes, trained on cumulative history | Trigger engine fires on pattern-based thresholds (occupancy drops, price drift) | Lead scoring formula identifies behavioral patterns in interaction data |
| **P14 Trust dynamics** | Trust tier demotes automatically on outcome variance; promotes on evidence | trust_assessor SLM continuously re-evaluates trust from context; no static assignment | Agent execution rights scale with performance history | Lead score updates on every new interaction; high-score leads can drop |
| **P15 Calibration** | Executive summary forces explicit outcome prediction with % confidence | Memory consolidation compares predictions against outcomes; updates priors | DAG coefficients re-calibrated from xlsx actuals; model ≠ market | Lead score is a probability, not a certainty; salesperson judgment final |

---

## APPENDIX: DEPLOYMENT TOPOLOGY

```
Google Cloud Platform
├── Cloud Run Services
│   ├── decision-engine          (port 8000, internal only)
│   ├── intelligence-silo        (port 8080, internal only, 4Gi RAM)
│   ├── gigaton-engine           (port 8001, internal only)
│   └── sales-operating-system   (port 8003, internal only)
│
├── Cloud Storage
│   ├── intelligence-silo/shared-memory  (FAISS index, semantic memory)
│   └── intelligence-silo-backup         (vault, journal — private repo fallback)
│
├── Secret Manager
│   ├── ANTHROPIC_API_KEY
│   ├── DECISION_ENGINE_URL
│   ├── GIGATON_ENGINE_URL
│   └── VAULT_PASSPHRASE
│
└── Load Balancer
    └── Routes external traffic → sales-operating-system (or gigaton-ui-system)
        Internal services communicate directly via Cloud Run internal mesh

Local Development
├── intelligence-silo   → localhost:8080
├── decision-engine     → localhost:8000
├── gigaton-engine      → localhost:8001
└── sales-operating-system → localhost:8003

Build Pipeline
└── cloudbuild.yaml (each service)
    ├── docker build → gcr.io/$PROJECT_ID/$SERVICE:$COMMIT_SHA
    ├── docker tag   → :latest
    └── gcloud run deploy
```

---

*Last updated: 2026-05-05*  
*Canonical location: `decision-engine/docs/architecture/MASTER_ARCHITECTURE.md`*
