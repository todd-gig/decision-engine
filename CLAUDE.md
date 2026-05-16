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
  api/            — FastAPI app (main.py + routes.py: /v1/decisions/*, /v1/outcomes/*, /v1/learning/*,
                    /v1/overrides/*, /v1/proposals/*, /v1/calibration/*, /v1/codification/*,
                    /v1/penrose/*, /v1/ai/*, /v1/drift/*, /v1/doctrine/*)
  engine/         — pipeline.py, gates.py, certificates.py, value.py, trust.py, rtql.py, learning_agent.py,
                    memory_manager.py, decision_engine.py, pricing_bridge.py, ppeme_outcome_emitter.py,
                    hme_event_emitter.py
  engine/ai_router/         — provider-abstraction chokepoint (CRIT-003 closed: prompt_version +
                              schema_version flow through providers/anthropic.py; audit envelope on every call)
  engine/codification/      — Claude→Python flywheel: readiness scorer + HMAC CodificationCertificate +
                              signoff matrix (todd@/matt@/both) + sweep + LLM proposer + replay simulator
                              (cloudbuild-codification-sweep.yaml wires Cloud Scheduler)
  engine/human_override/    — HMAC chain on OverrideEvent + 5-type taxonomy
                              (REVERSAL 3x / MODIFICATION 2x / REJECTION 2x / SILENT_INACTION 1.5x /
                              REPEATED_OVERRIDE) + pattern detector + nightly sweep + Pub/Sub emitter
                              + drift_history write-through
  engine/ovs_calibration/   — OutcomeSource registry + 3-stage AttributionDaemon
                              (direct + temporal+entity + 4-hop causal walk with 0.85/hop decay + F5.12
                              cascade multiplier) + VarianceComputer + HMAC-signed CalibrationRevision +
                              authority gate (>=10% magnitude requires dual signer) +
                              adapters/ (carmen_beach_revenue, ti_solutions_conversion, gigaton_ui_usage) +
                              counterfactual scoring (observable-only)
  engine/penrose/           — 8-metric falsification scoreboard façade: codification_rate,
                              human_override_rate, decision_velocity, ovs_variance, cascade_multiplier,
                              super_additive_network_value (PPEME inbox), revenue_per_human_touch,
                              drift_critical_count
  scripts/        — bootstrap_outcome_sources.py (idempotent OutcomeSource seed) +
                    backfill_carmen_beach_revenue.py (STVR CSV -> revenue events)
  schemas/decision_schema.yaml  — DecisionObject canonical schema
  specs/v3-fixed-assumptions.md — runtime assumptions
  docs/           — doctrine docs (01_doctrine, 02_first_principles_registry, ..., 09_learning_loop)
  intelligence_silo/ — auto-record bridge (lazy-loaded)
  tests/          — 515+ test functions across pipeline, gates, certificates, ai_router, codification,
                    human_override, ovs_calibration, penrose, drift-sentinel rules, bootstrap, backfill,
                    causal-chain, counterfactual, per-entity adapters, routes
  config/         — engine.yaml (weights + thresholds)
  frontend/       — legacy static HTML (not the platform frontend)
  drift_sentinel/ — recursive doctrine-conformance scanner (rules + scanner + reports + deploy);
                    drift_history.db now baked into Docker image (lights up drift_critical_count metric)
  MASTER_FIRST_PRINCIPLES_REFERENCE.md  — anchor doc, every threshold/weight/formula in code
  cli.py          — subcommands: codification-sweep, override-sweep, bootstrap-sources,
                    backfill-carmen-beach
  cloudbuild.yaml — Cloud Run deploy
  cloudbuild-codification-sweep.yaml — Cloud Scheduler trigger for codification sweep job
```

# Public Endpoints

**Core pipeline + learning loop**
- `POST /v1/decisions/process` — main pipeline
- `POST /v1/decisions/transition` — state machine transition
- `GET  /v1/decisions/lifecycle/{state}` — list decisions by state
- `POST /v1/outcomes/record` — outcome recording (closes learning loop)
- `GET  /v1/learning/summary` — calibration summary
- `GET  /v1/learning/unapplied` — pending calibration deltas
- `GET  /v1/config` / `GET /health`

**Human override (v0.5)**
- `POST /v1/overrides` — record override event (HMAC-chained)
- `POST /v1/overrides/sweep` — run nightly pattern detector
- `GET  /v1/overrides/patterns` — recurring override patterns (supports `?cross_org=true`)
- `GET  /v1/overrides/{override_id}` / `GET /v1/overrides` — fetch / list
- `POST /v1/overrides/drift/flush` — flush drift_history write-through queue
- `GET  /v1/overrides/transport/status` — Pub/Sub emitter health

**Codification (v0.5)**
- `POST /v1/codification/analyze` — analyzer pass on a decision
- `POST /v1/codification/sweep` — readiness sweep + open ready proposals
- `POST /v1/codification/propose/{proposal_id}` — LLM-driven code proposal
- `POST /v1/codification/simulate/{proposal_id}` — replay simulator on historical decisions
- `GET  /v1/codification/proposals/{proposal_id}/artifact` — fetch generated artifact
- `POST /v1/proposals` / `GET /v1/proposals` / `GET /v1/proposals/{id}` — proposal lifecycle
- `POST /v1/proposals/{proposal_id}/approve` — sign-off (todd@/matt@/both)
- `POST /v1/proposals/{proposal_id}/approve-and-certify` — sign-off + mint CodificationCertificate

**OVS calibration (v0.6)**
- `POST /v1/calibration/sources` / `GET /v1/calibration/sources` — OutcomeSource registry
- `POST /v1/calibration/compute-variance` — VarianceComputer pass
- `POST /v1/calibration/attribute` — 3-stage AttributionDaemon entrypoint
- `POST /v1/calibration/revisions` / `GET /v1/calibration/revisions` — HMAC-signed CalibrationRevision lifecycle
- `POST /v1/calibration/causal-chain/walk` — 4-hop causal walk with 0.85/hop decay
- `POST /v1/calibration/counterfactual/score` / `GET /v1/calibration/counterfactual/{id}` — observable-only counterfactual scoring
- `GET  /v1/calibration/adapters/status` — per-entity adapter health (carmen_beach, ti_solutions, gigaton_ui)

**Penrose falsification scoreboard (v0.7)**
- `GET  /v1/penrose/scoreboard` — all 8 metrics
- `GET  /v1/penrose/scoreboard/{metric}` — single-metric drill-down
- `GET  /v1/penrose/revenue/touch-rate` — revenue_per_human_touch (per-entity supported)
- `POST /v1/penrose/network-value/record` — PPEME super-additive network value ingest

**Provider abstraction**
- `POST /v1/ai/invoke` — single chokepoint for LLM calls (audit envelope mandatory)

**Drift + doctrine**
- `GET  /v1/drift/open` — open critical/major drift items
- `GET  /v1/doctrine` / `GET /v1/doctrine/version` — canonical doc surfaces

# Development Rules

1. **MASTER_FIRST_PRINCIPLES_REFERENCE.md is the source of truth** — every threshold, weight, and formula in the code must match this document. Schema-versioned: bump version when changing.
2. **22+ field DecisionObject** — never accept incomplete payloads; QC certificate enforces.
3. **Certificate chain is sequential** — no EC without QC + VC + TC; each is HMAC-SHA256 signed and tamper-evident.
4. **Promotion guards are non-skippable** — T2/T3/T4 trust tier requires per-dimension minimums; never bypass.
5. **Provider abstraction + audit envelope** — every LLM call goes through `_invoke_llm()` with `provider`, `model`, `prompt_version`, `schema_version` (already remediated 2026-05-05).
6. **Auto-record-every-decision** — `pipeline.py:_auto_record_memory()` lazy-loads `intelligence_silo` to persist decisions; non-blocking, ImportError tolerated.
7. **Drift Sentinel must satisfy its own rules** — see `drift_sentinel/DRIFT_SCANNER_SPEC.md` §Self-Doctrine.

# Test Coverage

**515+ test functions** across the full suite (was 8 cases before v0.5). pytest 3.11 + 3.12 + smoke + build all green. Coverage areas:

- `tests/test_pipeline.py` — D1 auto-execute, D6 blocked, needs-data, audit trail, certificate chain
- `tests/test_ai_router.py` — provider abstraction, audit envelope, prompt/schema versioning
- `tests/test_codification_*` — analyzer, readiness, proposer, simulator, sweep, signoff
- `tests/test_human_override_*` / `tests/test_routes_overrides.py` — HMAC chain, taxonomy multipliers, pattern detector, Pub/Sub emitter, drift write-through
- `tests/test_ovs_*` — OutcomeSource registry, AttributionDaemon (direct + temporal + causal-chain), VarianceComputer, CalibrationRevision, authority gate, counterfactual, per-entity adapters
- `tests/test_penrose_*` — scoreboard metrics, per-entity touch-rate, network-value emitter
- `tests/test_bootstrap_sources.py` — startup gate (`PENROSE_BOOTSTRAP_SOURCES=1`) + idempotency
- `tests/test_backfill_carmen_beach.py` — STVR CSV → revenue events
- `tests/test_drift_preventive_rules.py` — drift-sentinel rule fixtures (intentionally excluded from CRIT-011)
- `tests/test_gate_8_drift.py` — drift-sentinel feedback loop (B-02)

M-03 in BETA_2_GAP_LIST (light pipeline coverage) — substantially mitigated. Next gaps: per-gate failure paths, demotion automation.

# Org Alignment

- **intelligence-silo**: receives auto-recorded decisions; weight imports planned (B-04)
- **gigaton-engine**: pricing decisions route through this engine for governance via `engine/pricing_bridge.py` (**B-05 closed** after gigaton-engine PR #3 — pricing flows through the audit envelope)
- **PPEME**: consumes Penrose `super_additive_network_value` events emitted from `engine/penrose/network_value_emitter.py`; PPEME points `PENROSE_SCOREBOARD_URL` at this service to read scoreboard metrics
- **HME**: receives inferred-transition events on AUTO_EXECUTE via `engine/hme_event_emitter.py`
- **drift_sentinel**: scans this and other repos against canonical doctrine; deployed as Cloud Run Job + Cloud Scheduler in `carmen-beach-properties` GCP project; `drift_history.db` now baked into image so `drift_critical_count` Penrose metric reads real data on prod
- **All Gigaton repos**: every CLAUDE.md should reference the canonical doc here (B-13 in flight)

---

## Doctrine alignment (recursive)

This repo HOSTS the canonical doc — but it is also subject to it. The canonical doc is the contract; the code is the enforcement. When they disagree, the canonical doc wins until the code is updated to match.

- [`drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md`](drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md) — 7 non-negotiables, 15 first principles, 8 ethos filters, **19 frameworks** (5.18 SMEN added 2026-05-08; 5.19 BFT added 2026-05-13), 12 anti-patterns
- [`MASTER_FIRST_PRINCIPLES_REFERENCE.md`](MASTER_FIRST_PRINCIPLES_REFERENCE.md) — every threshold, weight, formula

### Doctrine-driven constraints (apply here)

- **B-02 closed** — drift_sentinel ↔ decision-engine feedback loop wired. `gate_8_drift_check()` in `engine/gates.py:403` queries `drift_history.db` for unresolved critical drift touching the decision's domain; failure is structural → BLOCK. Acknowledgment escape hatch: decision text mentioning the `rule_id` (e.g., "Fix CRIT-008") treats that rule as remediated. 7 unit tests in `tests/test_gate_8_drift.py`. Recursive self-governance loop closed.
- **B-05 closed** — `engine/pricing_bridge.py` consults gigaton-engine `/pricing/quote` and returns a normalized envelope onto the decision's evidence chain. After gigaton-engine PR #3 landed, pricing routes through this engine's audit envelope. v0 observational; v0.5 wires into gate-4 (reversibility) + gate-5 (risk containment).
- **B-15 open** — Engine Artifact Doctrine: the platform frontend is not engineered up-front; it emerges from `f(user, org, platform.intelligence, resources.available)`. Static HTML in `frontend/` is legacy substrate.
- **CRIT-003 closed** — `prompt_version` + `schema_version` flow through `engine/ai_router/providers/anthropic.py` (and gemini + openai); every LLM call carries an audit envelope.
- **MAJ-019 active** — every new module under `engine/<sub>/` must declare `penrose_signal: weakens|strengthens|neutral` and `penrose_dimension: <codification|override_rate|velocity|variance|cascade|network_value|revenue_per_touch|drift_count|provider_neutrality>` in its module docstring. `# noqa: MAJ-019` exemption permitted on first 60 lines. Handler at `drift_sentinel/drift_scan.py:2149`.
- **Scanner exclusions** — `tests/test_drift_preventive_rules.py` is excluded from CRIT-011 (intentional fixture); `.claude/worktrees/` is globally excluded from the scanner.
- **Slack is user-level only** — never auto-post from learning loop, calibration engines, or any scheduled jobs

### Penrose-falsification doctrine

All 8 Penrose metrics now have endpoints. Reference memory: `~/.claude/projects/-Users-admin/memory/penrose_falsification_doctrine.md`. After env-var flips (`PENROSE_BOOTSTRAP_SOURCES=1` here; `PENROSE_SCOREBOARD_URL` on PPEME), 6 metrics are numerically responsive; 2 await operator action (PPEME emission for `network_value`; STVR CSV backfill for `revenue_per_human_touch` numerator). `drift_critical_count = 0` sustained as of latest scan.
