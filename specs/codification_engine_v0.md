# Codification Engine — v0 Spec

> Status: BACKLOG → v0 spec (this PR).
> Anchors: `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` §5.8 (Decision
> Routing Framework: Python-first when stable+auditable+high-volume);
> Framework 5.7 (Adaptive Learning Loop); MAJ-008 (`codification_overdue`).
> Depends on: AI Routing Engine v0 (audit log signal); OVS-Calibration
> (outcome attribution signal).

## What

The Codification Engine continuously analyzes the LLM audit log + outcome
attribution data to identify *codification candidates* — prompts/decisions
that have:

- High call volume (high marginal cost benefit from codification)
- Low response variance (deterministic enough to be rules)
- Stable outcome distribution (no drift in what "right" means)
- Auditable inputs (can be expressed in code)

For each candidate, it generates a *codification proposal*: a Python
function that replicates the LLM's behavior with explicit rules, plus
a calibration analysis showing where the rules diverge from the LLM.
A human approves; the codified function ships; the LLM call becomes
a fallback path.

This is the Claude→Python flywheel mechanized as a peer engine.

## Why

§5.8 Decision Routing Framework canonically routes decisions to
*Python-first* when three properties hold: stable + auditable +
high-volume. Today this routing is manual — a human notices a Claude
call has become routine, codifies it, deprecates the LLM call.

Manual codification is bottlenecked by human attention. Many high-value
codification opportunities sit in the audit log indefinitely. MAJ-008
fires on these as `codification_overdue` — but that's a finding, not a
remediation.

Codification Engine remediates: it does the analysis automatically,
proposes the codification, and routes the proposal to the human queue
with the analysis pre-packaged.

## Where

- **v0 location**: sub-package `decision-engine/engine/codification/`
  - `analyzer.py` — audit-log scanner + candidate scoring
  - `proposer.py` — Python code generation from prompt+response patterns
  - `simulator.py` — replays proposed Python against audit-log inputs;
    measures divergence from LLM outputs
  - `queue.py` — proposal queue + human approval workflow
- **Proposal storage**: `codification_proposals` table in decision-engine
  Postgres
- **Approval queue UI**: surfaces in gigaton-ui-system Founder/Owner UI
  panel
- **Standalone service** (v0.5+): graduates when proposal generation
  starts competing for decision-engine resources

## When

- **v0 ship target**: T+14 days after OVS-Calibration v0 ships
- **First analysis run**: post-ship, queued daily at 03:00 UTC
- **Drift activation**: MAJ-008 enforceable once Codification Engine
  is producing proposals — the rule's escape hatch is "if proposal is
  open in queue, drift is acknowledged"

## How — Analyzer

Runs daily over `llm_audit` table:

```python
def find_candidates(audit_log: list[AuditRow], min_volume: int = 100):
    """Group by (prompt_version, schema_version) and score."""
    groups = group_by(audit_log, "prompt_version", "schema_version")
    candidates = []
    for (pv, sv), rows in groups.items():
        if len(rows) < min_volume:
            continue
        score = candidate_score(
            volume=len(rows),
            response_variance=measure_variance(rows),
            outcome_stability=measure_outcome_stability(rows),
            audit_completeness=measure_input_completeness(rows),
        )
        if score > 0.7:
            candidates.append((pv, sv, score, rows))
    return sorted(candidates, key=lambda x: -x[2])
```

### Candidate scoring

```
score = 0.4 * normalize(volume)
      + 0.3 * (1 - response_variance)
      + 0.2 * outcome_stability
      + 0.1 * audit_completeness
```

- `normalize(volume)`: log-scaled relative to ecosystem mean
- `response_variance`: lexical + semantic distance across responses
  for "same" inputs (binned)
- `outcome_stability`: OVS-Calibration's variance signal for the
  decision class this prompt-version serves
- `audit_completeness`: fraction of audit rows with full input
  metadata available for replay

Threshold `> 0.7` chosen conservatively; tunable once we have
historical signal.

## Proposer

For each candidate (pv, sv):

1. Sample `N=50` representative input/output pairs from audit log
2. Cluster inputs by structural similarity
3. For each cluster, propose a deterministic transformation
4. Generate a Python function that:
   - Accepts the audit row's input fields as parameters
   - Returns the same response shape (`schema_version` enforces this)
   - Uses explicit branching for cluster-specific behavior
5. Generate test cases from the held-out audit rows
6. Generate a `WHY` document explaining the reasoning

Proposer is itself an LLM call (recursive — the codifier calls Claude).
The proposer's call IS in the audit log; it's a known exception to
codification (analysis prompts are exempt from MAJ-008).

## Simulator

For each proposal, replays the proposed Python against ALL audit-log
inputs for that (pv, sv) over the last 30 days:

```python
def simulate(proposal: Proposal, audit_rows: list[AuditRow]) -> SimResult:
    divergence_per_row = []
    for row in audit_rows:
        python_output = proposal.fn(**row.audit_metadata)
        llm_output = row.response_text
        divergence_per_row.append(divergence(python_output, llm_output))
    return SimResult(
        n=len(audit_rows),
        divergence_p50=median(divergence_per_row),
        divergence_p90=p90(divergence_per_row),
        cost_savings_usd=sum(row.cost_usd for row in audit_rows),
        latency_savings_ms=sum(row.latency_ms for row in audit_rows),
        # ^ assumes Python execution is ~free; only LLM saving counts
    )
```

`divergence` is metric-specific:
- numeric outputs: relative error
- categorical outputs: agreement rate
- structured outputs: per-field weighted divergence
- free-text outputs: semantic similarity (cosine on embedding)

## Approval queue

Each proposal lands in the queue with:

- Candidate score
- Simulator results (divergence + savings)
- Generated Python code
- Generated tests
- WHY document
- Diff against current LLM behavior (visual)

Approver (Owner role in current governance) chooses:
- **Approve & ship**: PR opened against the calling engine; LLM call
  replaced with codified function; audit log marks pv→codified
- **Approve as fallback**: Python tried first; LLM called on
  divergence > threshold
- **Reject**: proposal archived with reason
- **Defer**: re-evaluate after N more outcomes

## Codification Proposal schema

```sql
CREATE TABLE codification_proposals (
    proposal_id        UUID PRIMARY KEY,
    candidate_pv       TEXT NOT NULL,
    candidate_sv       TEXT NOT NULL,
    candidate_score    REAL NOT NULL,
    analyzer_run_at    TIMESTAMPTZ NOT NULL,
    proposed_python    TEXT NOT NULL,                -- the function body
    proposed_tests     TEXT NOT NULL,                -- pytest cases
    why                TEXT NOT NULL,                -- LLM-generated rationale
    sim_n              INTEGER NOT NULL,
    sim_divergence_p50 REAL NOT NULL,
    sim_divergence_p90 REAL NOT NULL,
    sim_cost_savings_usd  NUMERIC(10, 4),
    sim_latency_savings_ms BIGINT,
    queue_status       TEXT NOT NULL,                -- 'open'|'approved_ship'|'approved_fallback'|'rejected'|'deferred'
    approver_user_id   UUID,
    approved_at        TIMESTAMPTZ,
    approval_why       TEXT,                         -- why approved or rejected
    shipped_pr_url     TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## v0 → v0.5 graduation

Codification Engine promotes from sub-package to standalone service when:

1. Proposal generation queue depth > 50 proposals consistently
2. Engine generates proposals against > 3 engines' audit logs
3. Independent deploy cadence diverges from decision-engine's

## Recursive note

The Codification Engine codifies LLM calls. It is itself partly
LLM-driven (the proposer). When the proposer pattern becomes stable
+ low-variance, Codification will codify *itself* — replacing its own
LLM dependency with Python heuristics. The recursive bootstrap is
intentional; it's the canonical form of the Claude→Python flywheel.

## Context

- **§5.8 Decision Routing**: this engine is the canonical mechanism
  for moving decisions from Claude-first to Python-first when criteria
  are met
- **MAJ-008 `codification_overdue`**: this engine's open queue
  acknowledges the drift; MAJ-008 fires when proposals sit > 60 days
  with no decision
- **AI Routing dependency**: without audit log, Codification has no
  signal
- **OVS-Calibration dependency**: without outcome attribution,
  Codification can't tell whether a candidate is stable
- **Memory cross-ref**: `codification_engine_spec.md` (older memory
  entry — this doc replaces and extends it)
