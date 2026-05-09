---
title: Decision Engine — Claude Operating Guide
version: 1.0
status: active
created: 2026-05-06
role: project-system-prompt
priority: critical
tags:
  - decision-engine
  - rtql
  - certificate-chain
  - 7-gate-auth
  - learning-loop
  - drift-sentinel
  - canonical-doctrine
---

# Project Identity

**Decision Engine v2.0.0** is the unified decision intelligence service for the Gigaton ecosystem. It implements RTQL trust qualification, the 12-dimension Value Matrix, the 7-dimension Trust Matrix, the QC→VC→TC→EC certificate chain, the 7-gate authorization system, the state machine lifecycle, and the adaptive learning loop. It is also the home of the **canonical first principles document** (the doctrine reference for the entire ecosystem) and the **Drift Sentinel** (recursive doctrine-conformance scanner).

# Architecture

```
decision-engine/
  api/            — FastAPI app (main.py + routes.py: /v1/decisions/*, /v1/outcomes/*, /v1/learning/*)
  engine/         — pipeline.py, gates.py, certificates.py, value.py, trust.py, rtql.py, learning_agent.py, memory_manager.py, decision_engine.py
  schemas/decision_schema.yaml  — DecisionObject canonical schema
  specs/v3-fixed-assumptions.md — runtime assumptions
  docs/           — doctrine docs (01_doctrine, 02_first_principles_registry, ..., 09_learning_loop)
  intelligence_silo/ — auto-record bridge (lazy-loaded)
  tests/          — test_pipeline.py + sample_payload.json
  config/         — engine.yaml (weights + thresholds)
  frontend/       — legacy static HTML (not the platform frontend)
  drift_sentinel/ — recursive doctrine-conformance scanner (rules + scanner + reports + deploy)
  MASTER_FIRST_PRINCIPLES_REFERENCE.md  — anchor doc, every threshold/weight/formula in code
  cli.py
  cloudbuild.yaml — Cloud Run deploy
```

# Public Endpoints

- `POST /v1/decisions/process` — main pipeline
- `POST /v1/decisions/transition` — state machine transition
- `GET  /v1/decisions/lifecycle/{state}` — list decisions by state
- `POST /v1/outcomes/record` — outcome recording (closes learning loop)
- `GET  /v1/learning/summary` — calibration summary
- `GET  /v1/config` / `GET /health`

# Development Rules

1. **MASTER_FIRST_PRINCIPLES_REFERENCE.md is the source of truth** — every threshold, weight, and formula in the code must match this document. Schema-versioned: bump version when changing.
2. **22+ field DecisionObject** — never accept incomplete payloads; QC certificate enforces.
3. **Certificate chain is sequential** — no EC without QC + VC + TC; each is HMAC-SHA256 signed and tamper-evident.
4. **Promotion guards are non-skippable** — T2/T3/T4 trust tier requires per-dimension minimums; never bypass.
5. **Provider abstraction + audit envelope** — every LLM call goes through `_invoke_llm()` with `provider`, `model`, `prompt_version`, `schema_version` (already remediated 2026-05-05).
6. **Auto-record-every-decision** — `pipeline.py:_auto_record_memory()` lazy-loads `intelligence_silo` to persist decisions; non-blocking, ImportError tolerated.
7. **Drift Sentinel must satisfy its own rules** — see `drift_sentinel/DRIFT_SCANNER_SPEC.md` §Self-Doctrine.

# Test Coverage

`tests/test_pipeline.py` — 8 cases (D1 auto-execute, D6 blocked, needs-data, audit trail, certificate chain). Coverage is light; M-03 in BETA_2_GAP_LIST flags this. Expand to cover: per-gate failure paths, RTQL stage transitions, learning-loop variance triggers, demotion automation.

# Org Alignment

- **intelligence-silo**: receives auto-recorded decisions; weight imports planned (B-04)
- **gigaton-engine**: pricing decisions should route through this engine for governance (B-05 — wiring not yet done)
- **drift_sentinel**: scans this and other repos against canonical doctrine; deployed as Cloud Run Job + Cloud Scheduler in `carmen-beach-properties` GCP project
- **All Gigaton repos**: every CLAUDE.md should reference the canonical doc here (B-13 in flight)

---

## Doctrine alignment (recursive)

This repo HOSTS the canonical doc — but it is also subject to it. The canonical doc is the contract; the code is the enforcement. When they disagree, the canonical doc wins until the code is updated to match.

- [`drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md`](drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md) — 7 non-negotiables, 15 first principles, 8 ethos filters, **18 frameworks** (5.18 SMEN added 2026-05-08), 12 anti-patterns
- [`MASTER_FIRST_PRINCIPLES_REFERENCE.md`](MASTER_FIRST_PRINCIPLES_REFERENCE.md) — every threshold, weight, formula

### Doctrine-driven constraints (apply here)

- **B-02 open** — drift_sentinel results not yet feeding back into the 7-gate authorization. Add gate #8 (pre-cert) that queries `drift_history.db` for open critical violations touching the decision domain.
- **B-05 open** — no decision↔gigaton-engine bridge; pricing decisions in gigaton-engine bypass governance.
- **B-15 open** — Engine Artifact Doctrine: the platform frontend is not engineered up-front; it emerges from `f(user, org, platform.intelligence, resources.available)`. Static HTML in `frontend/` is legacy substrate.
- **Slack is user-level only** — never auto-post from learning loop, calibration engines, or any scheduled jobs
