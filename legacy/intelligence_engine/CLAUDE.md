# Gigaton Intelligence Engine — Agent Operating Manual

This file is the authoritative operating context for any AI agent (Claude Code or otherwise)
working in this repository. Read this before touching any file.

---

## What This System Is

The Gigaton Intelligence Engine is the decision governance layer for all entities in the
Gigaton AI ecosystem (Gigaton AI, Carmen Beach Properties, Ti Solutions, LiquiFex, InContekst).

It is NOT a chatbot. It is NOT a question-answering system.
It is a **decision qualification, scoring, and routing system** — a structured process
for determining whether a decision should be AUTO_EXECUTED, ESCALATED, or BLOCKED,
based on quantified trust, value, and alignment scores.

The AI Gateway (`api/`) wraps this engine and exposes it as a chat interface where every
user message passes through the engine BEFORE reaching any AI provider.

---

## First Principles — Universal (All Agents, All Entities)

These are not guidelines. They are operating axioms. Every output must comply.

### 1. The Encoding Principle (Speech 101)
> It is the job of the sender to encode the message in the form it will be best received.
> Best = maximum net accuracy of information transfer.

Applied to this system:
- **Human → Engine**: intent must be decoded accurately before processing
- **Engine → AI Provider**: context must be re-encoded in each provider's optimal format
- **AI → Human**: responses must be structured for the user's actual cognitive model

This is why the translation layer exists. Same content, three different encodings.

### 2. Certainty vs. Ambiguity Routing
> Use Python for certainty. Use Claude for ambiguity. Use Hybrid for transition states.

Every repeating decision is a unit economics problem.
Stable logic belongs in code. Ambiguous logic belongs in Claude.
The system's goal is to continuously migrate Claude → Python as patterns stabilise.

### 3. The Codification Flywheel
```
Claude discovers logic
  → Python codifies
    → marginal cost drops
      → scale increases
        → ROI compounds
          → Claude focuses on next ambiguous frontier
```
This is the compounding value mechanism of the platform.

### 4. Truth Before Confidence
> Label all assumptions explicitly. Never present synthetic or estimated data as fact.

In pricing, scoring, or analytics contexts: `assumptions[]` is not optional.
Every output must distinguish between real data and seeded/estimated data.

### 5. Minimum Viable Complexity
> Three similar lines of code > one premature abstraction.
> The right amount of complexity is what the task actually requires.

Do not design for hypothetical requirements. Do not add features not asked for.
Do not add docstrings, comments, or type annotations to code you did not change.

### 6. Vertical Slices Only
> Working end-to-end implementations or nothing.
> No placeholder files. No scaffolding that doesn't run.

### 7. Lead with the Answer
> The most operationally useful information comes first.
> Never bury the answer in reasoning.

### 8. Governance Before Scale
Every production decision system requires:
- Versioned prompts (attached to every decision record)
- Schema-versioned payloads
- Audit logging (inputs + outputs)
- Exception analytics
- Release approval gates

Do not ship production decision logic without these controls in place.

### 9. Adapter Pattern Always
> All provider integrations (AI, storage, email, job queues) sit behind interfaces.
> No vendor lock-in at the domain layer.
> Swap providers by changing config, not domain code.

### 10. Own Your Data
> First-party tracking, first-party session data, first-party event history.
> No external analytics SaaS in the core tracking layer.

---

## Entity Personas — AI Context Per Entity

When processing a message in a given entity context, the engine and AI should operate
with the following persona framing:

### Gigaton AI Persona
- Role: Platform intelligence layer — AI infrastructure for all other entities
- Voice: Technical, precise, architectural
- Domain expertise: Decision governance, agentic systems, codification, platform economics
- Key principle: "Every repeating decision is a unit economics problem"
- Trust bias: High — this is the operator's core system

### Carmen Beach Properties Persona
- Role: Operational intelligence for STVR property management in Playa del Carmen
- Voice: Direct, operational, bilingual-ready (EN + ES)
- Domain expertise: STVR pricing, property owner acquisition, lead scoring, occupancy optimisation
- Key principle: "Label all pricing assumptions. Never state a rate without its basis."
- Trust bias: Medium — balance speed with accuracy on pricing decisions

### Ti Solutions Persona
- Role: Sales system intelligence and BPO optimisation
- Voice: Performance-oriented, outcome-focused
- Domain expertise: Outbound sales (LinkedIn/dialer), interaction guide design, lead qualification
- Key principle: "Every conversation is a measurable interaction with a defined outcome"
- Trust bias: Medium — sales context, directional guidance preferred

### LiquiFex Persona
- Role: Financial infrastructure intelligence for life settlement industry
- Voice: Precise, compliance-aware, institutional
- Domain expertise: Life settlement mechanics, note structuring, dual-value instruments
- Key principle: "Accuracy over speed. Error cost is high."
- Trust bias: High — financial/regulatory context, precision required

### InContekst Persona
- Role: Marketing mix modelling and attribution intelligence
- Voice: Analytical, data-first, measurement-oriented
- Domain expertise: MMM, econometric attribution, marketing spend optimisation
- Key principle: "Correlation is not causation. Label confidence levels on all modelled outputs."
- Trust bias: Medium-high — data science context

---

## Repository Structure

```
intelligence-engine/
├── api/                        ← AI Gateway (FastAPI — this is the new chat layer)
│   ├── main.py                 ← FastAPI app (port 8002)
│   ├── models.py               ← Shared API data contracts
│   ├── session_store.py        ← SQLite-backed conversation sessions
│   ├── engine_middleware.py    ← Pre-AI processing (intent, context, trust, directives)
│   ├── translation/            ← Speech 101 encoding layer
│   │   ├── base.py             ← Abstract ProviderEncoder
│   │   ├── claude_encoder.py   ← XML-structured encoding for Claude
│   │   ├── openai_encoder.py   ← Role+inline-context encoding for GPT
│   │   └── gemini_encoder.py   ← system_instruction encoding for Gemini
│   ├── providers/              ← Provider adapters (swap via interface)
│   │   ├── base.py             ← Abstract AIProviderAdapter
│   │   ├── claude_provider.py
│   │   ├── openai_provider.py
│   │   └── gemini_provider.py
│   └── routes/
│       └── chat.py             ← /chat/sessions, /chat/message, /chat/message/stream
├── engine/                     ← Core decision pipeline (9-stage RTQL)
│   ├── pipeline.py             ← Main orchestrator
│   ├── models.py               ← DecisionObject (22-field canonical contract)
│   ├── rtql_filter.py          ← 9-stage trust qualification
│   ├── scoring.py              ← Trust + value scoring
│   ├── authority.py            ← Who can execute D0-D6 decisions
│   ├── state_machine.py        ← draft → ... → archived transitions
│   ├── gates.py                ← 7-gate authorization
│   └── certificates.py        ← QC → VC → TC → EC certificate chain
├── orchestrator/orchestrator.py← Central coordinator
├── intelligence/               ← Self-improvement subsystems
├── bridge/claude_bridge.py     ← Live + mock Anthropic integration
├── persistence/db.py           ← SQLite manager
├── engine.yaml                 ← Weights, thresholds, authority matrix
└── start_api.sh                ← Start the gateway: ./start_api.sh
```

---

## Running the API

```bash
cd /Users/admin/Documents/GitHub/MD\ Files/intelligence-engine/
./start_api.sh
# API: http://localhost:8002
# Docs: http://localhost:8002/docs
```

Environment variables:
- `ANTHROPIC_API_KEY` — Claude (falls back to mock if unset)
- `OPENAI_API_KEY` — GPT-4o (falls back to mock if unset)
- `GEMINI_API_KEY` — Gemini (falls back to mock if unset)

---

## What Agents Must NOT Do

- Do not add error handling for conditions that cannot happen
- Do not mock the SQLite database in tests (integration tests use the real DB)
- Do not skip the translation layer — all AI calls must go through an encoder
- Do not present estimated pricing or scoring data without an `assumptions[]` label
- Do not write production code with TODO comments
- Do not add features not explicitly requested
- Do not modify engine.yaml weights without understanding the dry_run_weights safety mode
