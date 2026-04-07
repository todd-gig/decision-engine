# Executive Decision Engine v2.0

Unified decision intelligence engine that processes information through a structured qualification, certification, and execution pipeline. Combines trust assessment, value scoring, authority validation, and adaptive learning into a single deployable artifact.

## What It Does

Accepts a decision payload and runs a 9-stage pipeline:

1. **Input Validation** — Verifies all required fields are populated
2. **RTQL Pre-Filter** — Recursive Trust Qualification Loop classifies input trust quality
3. **Value Assessment** — 8 positive + 4 penalty dimensions, raw and weighted scoring
4. **Trust Assessment** — 7 trust inputs mapped to tier (T0-T4) with promotion guards
5. **Authority Check** — Role hierarchy enforcement per decision class (D0-D6)
6. **Certificate Chain** — Issues QC → VC → TC → EC certificates sequentially
7. **7-Gate Authorization** — Doctrine, trust, value, reversibility, risk, approval, monitoring
8. **State Machine** — Advances decision through 8-state lifecycle
9. **Priority Scoring** — Composite score for execution queue ranking

Returns one of: `auto_execute`, `escalate_tier_1/2/3`, `block`, `needs_data`, or `information_only`.

## Quick Start

### Run locally
```bash
pip install -r requirements.txt
python cli.py run
```

### Run with Docker
```bash
docker compose up --build
```

### Run the test suite
```bash
python cli.py test
```

### Process a single decision
```bash
python cli.py process tests/sample_payload.json
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/config` | Engine configuration |
| POST | `/v1/decisions/process` | **Full pipeline processing** |
| POST | `/v1/decisions/transition` | Validate state transitions |
| GET | `/v1/decisions/lifecycle/{state}` | Lifecycle status for a state |
| POST | `/v1/outcomes/record` | Record post-execution outcome |
| GET | `/v1/learning/summary` | Institutional learning summary |
| GET | `/v1/learning/unapplied` | Unapplied learning records |
| GET | `/dashboard` | Frontend dashboard |
| GET | `/docs` | OpenAPI documentation |

## Example: Full Pipeline Request

```bash
curl -X POST http://localhost:8000/v1/decisions/process \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Deploy updated onboarding email template",
    "decision_class": "D1",
    "owner": "marketing_ops",
    "problem_statement": "Current onboarding email has 12% open rate",
    "requested_action": "Replace with A/B tested winner",
    "stakeholders": ["marketing_ops", "customer_success"],
    "evidence_refs": ["ab_test_results.csv"],
    "execution_plan": "Swap template, monitor 7 days",
    "monitoring_metric": "email_open_rate >= 18%",
    "rollback_trigger": "open_rate < 15% over 48hrs",
    "review_date": "2026-03-31",
    "current_state": "trust_certified",
    "actor_role": "AI_Domain_Agent",
    "value_scores": {
      "revenue_impact": 2, "cost_efficiency": 3, "time_leverage": 4,
      "strategic_alignment": 3, "customer_human_benefit": 3,
      "knowledge_asset_creation": 2, "compounding_potential": 2,
      "reversibility": 5, "downside_risk": 1, "execution_drag": 1,
      "uncertainty": 1, "ethical_misalignment": 0
    },
    "trust_scores": {
      "evidence_quality": 4, "logic_integrity": 4, "outcome_history": 3,
      "context_fit": 4, "stakeholder_clarity": 4,
      "risk_containment": 4, "auditability": 4
    },
    "alignment_scores": {
      "doctrine_alignment": 0.8, "ethos_alignment": 0.9,
      "first_principles_alignment": 0.7
    }
  }'
```

## Project Structure

```
decision-engine/
├── cli.py                    # CLI entry point (run, test, process, seed-certs)
├── api/                      # FastAPI service layer
│   ├── main.py              # App factory + static file mounting
│   ├── routes.py            # All HTTP endpoints
│   └── schemas.py           # Pydantic request/response models
├── engine/                   # Core processing engine (30+ modules)
│   ├── pipeline.py          # Main orchestrator — process_decision()
│   ├── models.py            # Canonical data models (22-field DecisionObject)
│   ├── config.py            # Configurable thresholds, weights, authority matrix
│   ├── scoring.py           # Trust tier, alignment, priority scoring
│   ├── weighted_scoring.py  # Asymmetric weighted value/trust scoring
│   ├── gates.py             # 7-gate autonomous execution authorization
│   ├── authority.py         # Role-based execution rights
│   ├── state_machine.py     # 8-state decision lifecycle
│   ├── certificates.py      # Certificate chain (QC → VC → TC → EC)
│   ├── rtql_filter.py       # RTQL trust qualification (pipeline integration)
│   ├── rtql_classifier.py   # RTQL classifier (standalone)
│   ├── rtql_integration_layer.py  # Registry mutation control
│   ├── audit.py             # Audit logging and serialization
│   ├── gap_analysis.py      # Performance gap detection
│   ├── value_leakage.py     # Value leakage detection
│   ├── roi_engine.py        # ROI calculation and ranking
│   ├── ovs_engine.py        # Organizational Value Score (4-system health)
│   ├── causal_mapper.py     # 4-layer causal chain mapping
│   ├── adaptive_learning.py # 4 learning engines + LVI tracking
│   ├── learning_loop.py     # Post-execution variance tracking
│   ├── exception_engine.py  # Exception classification and escalation
│   ├── governance_gates.py  # 30/60/90-day gate assessments
│   ├── memory_manager.py    # Persistent MD-based memory
│   ├── trust_certificates.py # HMAC-signed trust certificates
│   ├── learning_agent.py    # Claude API-powered learning from human input
│   └── runner.py            # 5-scenario test suite
├── config/
│   └── engine.yaml          # Thresholds, weights, authority matrix, transitions
├── frontend/                 # Dashboard UI
├── data/                     # Learning loop storage (JSONL + index)
├── memory/certs/            # Trust certificate storage
├── docs/                    # Doctrine, principles, taxonomy (10 docs)
├── templates/               # Decision record, certificate, value assessment
├── schemas/                 # YAML schema definitions
└── tests/                   # Integration tests
```

## Engine Subsystems

| Subsystem | Purpose |
|-----------|---------|
| **Pipeline** | Orchestrates all stages in sequence |
| **RTQL** | Classifies input trust quality (noise → axiom candidate) |
| **Value Engine** | 8 positive + 4 penalty dimensions with configurable weights |
| **Trust Engine** | 7-dimension scoring → tier (T0-T4) with promotion guards |
| **Authority Engine** | Role hierarchy × decision class × trust tier matrix |
| **Certificate Chain** | QC → VC → TC → EC with expiration and prerequisites |
| **7-Gate System** | Doctrine, trust, value, reversibility, risk, approval, monitoring |
| **State Machine** | draft → qualified → value_confirmed → trust_certified → execution_cleared → executed → reviewed → archived |
| **OVS Engine** | Organizational health across People, Process, Technology, Learning |
| **ROI Engine** | Impact/cost ratio with leverage and risk adjustments |
| **Causal Mapper** | 4-layer propagation model (primary → compound) |
| **Gap Analysis** | Trust-penalized gap scoring with priority ranking |
| **Value Leakage** | Automated leakage detection with cascade multipliers |
| **Learning Loop** | Variance tracking, trust recommendations, institutional memory |
| **Adaptive Learning** | 4 calibration engines + Learning Value Index |
| **Exception Engine** | 8-class exception taxonomy with codification tracking |
| **Governance Gates** | 30/60/90-day quantified gate assessments |
| **Memory Manager** | Persistent MD-based memory with YAML frontmatter |
| **Trust Certificates** | HMAC-SHA256 signed domain trust certificates |

## Configuration

All tunable parameters live in `config/engine.yaml`:
- Execution and escalation thresholds
- Value dimension weights (asymmetric)
- Penalty dimension weights
- Trust tier multipliers (T0-T4)
- Authority matrix (D1-D6 → role + approval requirements)
- Valid state transitions

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `ANTHROPIC_API_KEY` | For Claude-powered learning agent | Optional |
