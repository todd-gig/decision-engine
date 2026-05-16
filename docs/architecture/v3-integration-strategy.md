# Unified Decision Engine — Repo Integration Plan

**Proof ID:** CP-2026-04-13-002
**Classification:** Strategic architecture decision, high-stakes
**Mode:** Conical Proof (full) + Artifact Package
**Invocation:** `gigaton-language` skill v0.1.0
**Generated:** 2026-04-13

---

## 0. Security Finding (Surface First)

**LEAKED GITHUB PAT DETECTED.** In `Desktop/github-multiaccount/repo_master_list.txt`, the remote URL for `Carmen-Beach-Properties` contains a classic-format PAT (`gho_REDACTED_SEE_PHASE_0_TASK_1`) embedded in the URL. This token has at minimum push access to that repo and likely broader scope (the `sQlm` prefix suggests workflow or repo scope). Rotate immediately: GitHub → Settings → Developer settings → Personal access tokens → revoke. Then scrub the file, scan git history for additional exposures, and audit recent pushes to affected repos. Treat this as P0, outside the integration plan itself.

---

## 1. Objective

Produce an **ordered, execution-ready integration plan** that merges all 18 repos across `todd-gig` and `bella-byte` GitHub accounts, the existing v3 operating model, and the `gigaton-language` skill/plugin into **one unified decision engine** that delivers compounding value across every decision cycle.

The target end-state is: every business decision — pricing, sales action, product approval, contract review, client deliverable, automation trigger — routed through a single governance pipeline that scores it against Gigaton's six-dimension rubric, attaches trust certificates, produces an auditable proof artifact, and returns a verdict (auto-execute / escalate / block / needs-data) to the right surface (Platform UI, Slack, ClickUp, GitHub Action).

---

## 2. First-Principles Breakdown

Four axioms govern the system.

**A1 — One proof, one truth.** Every decision is a conical proof. The proof is the unit of work, the unit of audit, and the unit of learning. Prose notes, tribal knowledge, and ad-hoc Slack threads do not qualify as decisions — they are inputs to proofs.

**A2 — Separation of kernel and surface.** The decision kernel (scoring, verdict, certificate chain) must be one service. User surfaces (Platform UI, Slack bot, CLI, Claude skill, GitHub Action) are thin clients that submit inputs and render outputs. Multiple kernels = drift; one kernel + many surfaces = compounding value.

**A3 — Existing work beats new work.** The `decision-engine` repo already implements a v2 RTQL 9-stage pipeline + 7-gate authorization + certificate chain. The `claude_decision_logic_pack` implements the v1 ValueEngine/TrustEngine/RTQLEngine/CertEngine/VerdictEngine/PriorityEngine. The `gigaton-language` skill implements the conical-proof structure and six-dimension scoring. **These are the same engine viewed from different altitudes.** Merge, don't replace.

**A4 — Trust and provenance are first-class.** Every proof carries its evidence chain: which transcript, which email, which contract clause, which prior proof. Without provenance, compounding breaks — you can't trust decision N+1 when decision N's inputs are unknowable.

---

## 3. Scope & Entities

### In scope (21 artifacts)

**Tier 1 — Production backends (must integrate):**
- `decision-engine` (FastAPI, RTQL 9-stage pipeline, 7-gate auth, cert chain) — **the kernel**
- `gigaton-engine` (FastAPI, pricing, margin optimization, multi-agent supervisor, Claude enrichment)
- `sales-operating-system` (FastAPI, 214-item catalog, recommendation engine, agent runtime)
- `transcript-knowledge-base` (Python ETL, 5 sources → 4 destinations, GitHub Actions)
- `Carmen-Beach-Properties` (Next.js 15 + Turborepo + 14 shared packages, GCP Terraform) — **the deployment reference**

**Tier 2 — UI prototypes (consolidate into one surface):**
- `gigaton-ui-system` (best chat subsystem, multi-provider SSE)
- `LiqueFex-Platform-Ui` (visual reference)
- `gigaton` (LiquiFex intake wizard, Gemini analysis)
- `bella-byte/Gigaton-UI-Platform` (Firebase Auth + Google sign-in, React 19 + Vite + react-router)
- `bella-byte/Liquifex-fluidity-presentations` (presentation layer)
- `gigaton-platform-ui` (Turborepo, pnpm, apps+packages split)

**Tier 3 — Intelligence & decision logic:**
- `intelligence-silo` (6 SLM transformers, 4-layer memory, FAISS vectors, mesh)
- `claude_decision_logic_pack` (v1 decision engine — source for kernel merge)
- `gigaton-language` plugin (conical proof + scoring + cross-language validators) — **the reasoning layer**

**Tier 4 — Knowledge archives:**
- `MD-Files` (1,654 files — intellectual DNA)
- `master-knowledge-base` (1,329 files — overlaps MD-Files)
- `braintrust-knowledge-base` (14 session notes — strategic context)

**Tier 5 — Revenue-facing deliverables:**
- PDC site + admin (already production-grade)
- LiquiFex intake flow + presentation
- Interactive Claude Education ROI calculator

**Supporting systems (non-repo):**
- Notion workspace (Recurring Tasks DB, Daily Automation System, project pages)
- ClickUp (task orchestration)
- Google Drive (raw documents, meeting notes)
- Slack (ti-gigaton workspace, team comms)
- Cloudflare (already connected — Workers/KV/R2/D1 available)
- GCP (Cloud Run, Cloud SQL, GCS per existing Terraform)
- Firebase (auth + realtime)

### Out of scope (archival)

`playadelcarmen.homes` (old), `desktop-tutorial`, `CxGuy-Slack-Discussions` (read-only archive), `intelligence-silo-backup` (vault).

### Entities

- **Decision** — the atomic unit. Has an ID, inputs, scoring dimensions, verdict, certificate chain, and an audit trail.
- **Proof** — the rendered, human-auditable representation of a Decision as a conical proof.
- **Surface** — any client that submits a Decision and renders a Proof (UI, Slack, CLI, Action).
- **Kernel** — the single service that scores Decisions and issues verdicts.
- **Token Registry** — versioned Gigaton-language vocabulary that compresses recurring reasoning.
- **Provenance Graph** — typed edges linking Proofs to Evidence (transcript IDs, email message IDs, contract hashes, prior Proof IDs).

---

## 4. Constraints

- **C1 — Solo operator bandwidth.** You are the primary engineer. The plan must be incremental, shippable in weekly increments, with every step producing independent value.
- **C2 — No GitHub MCP in registry.** Repo operations happen locally via clone + git CLI until a GitHub connector ships.
- **C3 — Two GitHub accounts** (`todd-gig`, `bella-byte`). Multi-account SSH config already exists in `github-multiaccount/` scripts.
- **C4 — Leaked PAT (see §0).** Must be rotated before any further remote ops.
- **C5 — Tailwind CDN issue** in three UI prototypes. Production deploys require proper PostCSS install.
- **C6 — Kernel drift risk.** Two decision-engine implementations (v1 in `claude_decision_logic_pack`, v2 in `decision-engine` repo). Must converge, not fork.
- **C7 — Credential gaps.** Zoom OAuth, GitHub PAT (scoped), Otter password, RingCentral JWT, Fireflies API key, Notion integration token are all blockers per `Usage Report — 2026-04-02`.

---

## 5. Assumptions

- **S1** — Gigaton v3 tech stack decisions are locked: Next.js 15 + Turborepo (frontend), FastAPI + Pydantic v2 (backend), PostgreSQL + Prisma (primary data), Firebase (auth + realtime), Claude primary + Gemini fallback, GCP + Cloudflare (infra), GitHub Actions (CI/CD).
- **S2** — The `decision-engine` v2 REST contract (`/v1/decisions/*`) is the canonical kernel API. v1 logic in `claude_decision_logic_pack` gets ported to v2 shape where any capability is missing.
- **S3** — The `gigaton-language` skill/plugin is the sanctioned reasoning protocol. Every Decision submitted to the kernel carries a conical-proof payload in the request body (apex, scope, entities, options, decision, execution, risks) and returns a scored proof + verdict.
- **S4** — `bella-byte/Gigaton-UI-Platform` has the cleanest working Firebase Auth + Google Sign-In. It gets promoted to the canonical surface scaffold and absorbs the chat subsystem from `gigaton-ui-system`.
- **S5** — `transcript-knowledge-base` is the single ingestion pipeline for raw reasoning inputs. Everything else (Slack search, Notion search, email) feeds into it or into the provenance graph.
- **S6** — Claude (this session + future Cowork sessions + Claude Code CLI) is the primary reasoning operator. The `gigaton-language` plugin ensures any Claude surface produces kernel-compatible proofs.

---

## 6. Options

Four viable architectures were considered.

**O1 — Big-bang monorepo consolidation.** Merge all 18 repos into one Turborepo, rebuild surfaces from scratch. *Rejected: violates C1 (bandwidth), high execution risk, destroys provenance of existing commits.*

**O2 — Federated microservices with no unification.** Leave each repo independent, add a thin router in front. *Rejected: violates A2 (kernel drift), produces no compounding value, just aggregates today's fragmentation.*

**O3 — Hub-and-spoke: one kernel, many surfaces, existing-work-first.** `decision-engine` v2 becomes the hub. Every other backend calls it for verdicts. `bella-byte/Gigaton-UI-Platform` becomes the primary surface scaffold and absorbs the best chat subsystem. `transcript-knowledge-base` becomes the ingestion spine. `gigaton-language` plugin becomes the reasoning protocol carried in every request. *Selected.*

**O4 — Rebuild around the `gigaton-language` skill as the kernel.** Make Claude + the skill the decision engine, with all other repos reduced to dumb data stores. *Rejected: violates A3 (existing work), ignores the already-implemented v2 RTQL pipeline, makes the system dependent on session-bound skill execution rather than a deployed service.*

---

## 7. Evaluation Criteria

Options were judged against the six-dimension scoring rubric plus two strategic dimensions:

| Dimension | Weight | Why |
|---|---|---|
| Truth Integrity | 20% | One kernel = one truth (A1, A2). |
| Execution Usefulness | 20% | Must ship in weekly increments (C1). |
| ROI / Decision | 15% | Time-to-first-value matters. |
| Compression Efficiency | 10% | Reducing 21 artifacts to ~6 deployed services. |
| Ambiguity | 10% | Provenance + typed contracts eliminate drift. |
| Audit Recovery | 10% | Every decision reproducible from proof + kernel version. |
| Reversibility | 10% | Each step must be undoable if wrong. |
| Existing-work leverage | 5% | v3 non-negotiable. |

---

## 8. Comparative Assessment

| Criterion | O1 Monorepo | O2 Federated | **O3 Hub-Spoke** | O4 Skill-as-kernel |
|---|---|---|---|---|
| Truth Integrity | 4 | 2 | **5** | 3 |
| Execution Usefulness | 2 | 4 | **5** | 2 |
| ROI / Decision | 2 | 3 | **5** | 2 |
| Compression | 5 | 1 | **4** | 3 |
| Ambiguity (lower = better) | 3 | 2 | **4** | 2 |
| Audit Recovery | 4 | 2 | **5** | 3 |
| Reversibility | 1 | 5 | **4** | 4 |
| Existing-work leverage | 1 | 5 | **5** | 2 |
| **Composite (weighted)** | 2.9 | 2.9 | **4.7** | 2.6 |

---

## 9. Decision

**Adopt Option 3 — Hub-and-Spoke with `decision-engine` v2 as kernel, `bella-byte/Gigaton-UI-Platform` as primary surface, `transcript-knowledge-base` as ingestion spine, and `gigaton-language` plugin as the reasoning protocol carried in every request.**

Composite score: **4.7/5**.

This converges all existing work onto one decision kernel without forcing a rebuild, consolidates six UI prototypes into one surface scaffold, standardizes the reasoning protocol across human-written, Claude-written, and automation-written decisions, and produces a provenance graph that makes decision N+1 stronger than decision N — the definition of compounding value.

---

## 10. Proof of Superiority

**Why O3 beats the alternatives on the axes that matter:**

- **Beats O1 (monorepo)** on reversibility and execution usefulness. Each integration step in O3 is independently shippable and independently reversible. O1 is a single bet.
- **Beats O2 (federated)** on truth integrity and compounding value. O2 aggregates today's fragmentation; O3 eliminates it by forcing one scoring pipeline.
- **Beats O4 (skill-as-kernel)** on availability and audit recovery. A deployed FastAPI service with a versioned API contract is reproducible, monitorable, and testable. A Claude-session-bound skill is not.

**The load-bearing claim:** once every surface submits Decisions through one kernel that carries a conical-proof payload, every downstream system (pricing, sales agent, contract review, approval queue) gets the same governance for free. The first integration costs the most; every subsequent integration is additive.

**Cross-language validator check** (applied selectively to high-stakes sub-claims):

- *German (referent forcing):* "The kernel" must resolve to exactly one deployed service at one URL at one version. Passes — `decision-engine` v2 at a single Cloud Run URL.
- *Japanese (evidentiality):* Every decision proof must carry its evidence source (who said what, where, when). Passes via provenance graph requirement (A4).
- *Hindi (ergativity/aspect):* Who acted? Is the action complete? Passes via explicit agent + completion markers in the Decision schema (`decided_by`, `executed_at`, `verdict` states).

No failures surfaced. The design survives structural interrogation.

---

## 11. Execution Requirements — Ordered Task List

This is the order-of-operations you asked for. Each phase produces independent value; no phase depends on later phases being complete.

### PHASE 0 — Security + Hygiene (Day 0, do first)

1. **Rotate leaked GitHub PAT.** Revoke `gho_sQlm...` in GitHub Settings. Scrub `github-multiaccount/repo_master_list.txt`. Scan git history of `Carmen-Beach-Properties` for unauthorized pushes. *Owner: Todd. Time: 30 min. Blocker for everything else.*
2. **Consolidate credentials vault.** Move all PATs, API keys, OAuth secrets into one password manager or GCP Secret Manager. Document which services use which secret. *Owner: Todd. Time: 2 hr.*
3. **Verify `bella-byte` vs `todd-gig` account split.** Confirm which repos live under which org. Standardize: production repos on `todd-gig`, client-facing demos on `bella-byte` (or the reverse — pick one). *Owner: Todd. Time: 1 hr.*

### PHASE 1 — Kernel Convergence (Week 1)

4. **Declare `decision-engine` v2 the canonical kernel.** Tag current `main` as `v2.0.0`. Freeze the `/v1/decisions/*` REST contract. Add OpenAPI spec to repo root. *Owner: Todd + Claude. Time: 4 hr.*
5. **Port `claude_decision_logic_pack` engines into `decision-engine`.** Merge ValueEngine, TrustEngine, RTQLEngine, CertEngine, VerdictEngine, PriorityEngine as modules alongside v2's RTQL pipeline. Write migration tests proving v1 scenarios still produce same verdicts in v2. Mark `claude_decision_logic_pack` as archived with a tombstone README pointing to `decision-engine`. *Owner: Claude (via skill) + Todd review. Time: 2 days.*
6. **Add `gigaton-language` proof payload to Decision schema.** Extend `Decision` Pydantic model to carry an optional `conical_proof: ConicalProof` field (apex, scope, entities, options, decision, execution, risks, scoring, compression_scan). The kernel stores it, returns it in responses, and references it in the certificate chain. *Owner: Claude. Time: 4 hr.*
7. **Deploy kernel to Cloud Run.** Use the `Carmen-Beach-Properties` Terraform pattern. Wire Cloud SQL PostgreSQL. Add GitHub Actions deploy pipeline. Generate service URL. *Owner: Todd. Time: 1 day.*

### PHASE 2 — Ingestion Spine (Week 2)

8. **Activate `transcript-knowledge-base` credentials.** Add Zoom Server-to-Server OAuth, scoped GitHub PAT, Otter password, RingCentral JWT, Fireflies API key, Notion integration token to GCP Secret Manager + GitHub Actions secrets. Run `bash scripts/setup_credentials.sh`. *Owner: Todd. Time: 4 hr.*
9. **Turn on the 5 ingestion workflows.** Zoom, Otter, Fireflies, RingCentral, Google Meet all pushing to GitHub + Drive + Notion + ClickUp. Verify one full cycle end-to-end. *Owner: Todd. Time: 1 day.*
10. **Add provenance writer.** Every ingested transcript generates a `provenance` record (source_type, source_id, ingested_at, sha256, storage_urls) and writes it to the decision kernel's provenance table. This is the foundation for A4. *Owner: Claude. Time: 1 day.*

### PHASE 3 — Surface Consolidation (Weeks 3–4)

11. **Promote `bella-byte/Gigaton-UI-Platform` to the canonical surface scaffold.** It has working Firebase Auth + Google Sign-In + react-router + 6 pages (Login, SignUp, Platform, Dashboard, BrandIconLists, BrandVoiceDictionary). Tag `v0.1.0`. *Owner: Todd. Time: 2 hr.*
12. **Migrate scaffold from Vite+HashRouter to Next.js 15 + App Router.** Port the 6 pages, keep the Firebase Auth context, keep the visual language. This unlocks S1 (tech stack lock). *Owner: Claude + Todd review. Time: 3 days.*
13. **Extract chat subsystem from `gigaton-ui-system`** into `@gigaton/chat` package. Port SSE streaming + multi-provider selector. Mount at `/chat` in the new surface. Wire to `gigaton-core/services/ai_gateway` (FastAPI + Anthropic + Gemini). *Owner: Claude + Todd. Time: 2 days.*
14. **Extract intake wizard from `gigaton` repo** into `@gigaton/intake` package. Keep Gemini analysis. Mount at `/intake` in the new surface. *Owner: Claude. Time: 1 day.*
15. **Add `/decisions` page** to the surface. Lists all Decisions from the kernel, shows scoring + verdict + conical proof render, supports approve/reject for `escalate_tier_*` verdicts. This is the approval surface per `PLATFORM_UI_MVP.md`. *Owner: Claude + Todd. Time: 2 days.*
16. **Archive superseded UI repos.** Add tombstone READMEs to `LiqueFex-Platform-Ui`, `gigaton-ui-system`, `gigaton` (the Vite one) pointing to the new canonical surface. Do not delete — preserves provenance. *Owner: Todd. Time: 30 min.*

### PHASE 4 — Spoke Integration (Weeks 5–6)

17. **`gigaton-engine` → kernel.** Every pricing decision above a reversibility threshold submits a Decision to the kernel, carries the `conical_proof` payload, and waits for verdict. *Owner: Claude. Time: 2 days.*
18. **`sales-operating-system` → kernel.** Every recommendation with margin impact > $X submits a Decision. Agent runtime waits for `auto_execute` verdict. *Owner: Claude. Time: 2 days.*
19. **`Carmen-Beach-Properties` → kernel.** Admin-side actions (pricing updates, listing approvals) submit Decisions. Client-facing reads don't. *Owner: Todd. Time: 1 day.*
20. **`intelligence-silo` → kernel bridge.** The existing decision-engine bridge wires into v2. SLM outputs become evidence in the provenance graph. *Owner: Claude. Time: 2 days.*

### PHASE 5 — Protocol Saturation (Weeks 7–8)

21. **Slack bot with `gigaton-language` skill.** A bot in `ti-gigaton` workspace that accepts `/decide <question>`, runs the skill, produces a conical proof, submits to the kernel, posts verdict + proof artifact link. *Owner: Claude. Time: 2 days.*
22. **ClickUp → kernel integration.** High-priority tasks automatically generate Decisions. Status changes reflect verdicts. *Owner: Claude. Time: 1 day.*
23. **GitHub Actions → kernel integration.** PRs flagged as high-risk (migrations, prod infra, cert rotation) auto-submit a Decision. Merge blocked until verdict resolves. *Owner: Claude. Time: 2 days.*
24. **Notion → kernel read-back.** The Recurring Tasks DB and Daily Automation System pages render kernel verdicts as columns. *Owner: Claude. Time: 1 day.*
25. **Cloudflare Worker edge router.** One Worker sits in front of the kernel, does auth, rate limit, tenant resolution. *Owner: Todd. Time: 1 day.*

### PHASE 6 — Compounding Loop (Weeks 9–10)

26. **Token promotion pipeline wired in.** Every 10 Decisions, the kernel runs a compression scan (via `gigaton-language` compression-scan stage) and surfaces top-5 promotion candidates. Todd reviews weekly. Approved candidates enter `references/token-registry.md` with version bump. *Owner: Claude + Todd. Time: 2 days build + ongoing.*
27. **Cross-language validator queue.** High-stakes Decisions (reversibility < 0.3 OR financial_exposure > threshold) automatically route through the validator stack before the kernel returns a verdict. *Owner: Claude. Time: 2 days.*
28. **Knowledge archive provenance backfill.** `MD-Files`, `master-knowledge-base`, `braintrust-knowledge-base` get indexed into the provenance graph so old reasoning becomes citable evidence for new Decisions. *Owner: Claude. Time: 3 days.*
29. **Decision-to-outcome feedback loop.** Every Decision gets an `outcome` field populated after execution. Weekly report compares predicted vs actual. Adaptive learning loop in RTQL updates priors. *Owner: Claude + Todd. Time: 3 days.*
30. **Public read-only audit page.** For client trust, a page rendering the Nth most recent Decisions with PII redacted, showing the kernel + proof works. Optional but high-leverage. *Owner: Todd. Time: 2 days.*

---

## 12. Risk Controls

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Leaked PAT abused before rotation | High | Critical | Phase 0 Task 1 runs first. Non-negotiable. |
| Kernel becomes a single point of failure | Medium | High | Cloud Run multi-region + circuit-breaker fallback: if kernel is down, surfaces log Decision to DLQ + auto-execute only `reversibility > 0.9` ones. |
| v1 / v2 divergence during merge | Medium | High | Migration tests (Task 5) must pass 100% of v1 scenarios before v1 is archived. |
| Surface migration (Vite → Next.js) introduces regression | Medium | Medium | Keep old surface running in parallel. Cut over per-page. |
| `transcript-knowledge-base` credential outage | High | Medium | Each source independently activated. Degrade gracefully — one source down != pipeline down. |
| Token promotion introduces hidden ambiguity | Low | Medium | Non-negotiable #3: promotion criteria must include reversibility. Todd reviews every promotion. |
| Scope creep pulling tier-5 repos back in | Medium | Low | Archival tombstones (Task 16). New work not allowed in archived repos. |
| Claude-session-bound reasoning (skill) drifts from kernel contract | Low | High | Plugin version pins to kernel API version. Skill self-checks by hitting `/v1/meta/compatibility` at start of each proof. |

---

## 13. Compression Opportunity Scan

Recurring structures surfaced during this proof. Flagged as promotion candidates for the Gigaton token registry:

| Candidate | Pattern | Recurrence | Promotion Recommendation |
|---|---|---|---|
| `R:KERNEL_AS_HUB` | "One scoring service, many surfaces" | Appears in A2, S2, O3, §10, multiple tasks | **Promote.** High reuse, reduces ambiguity, reversible. |
| `R:EXISTING_FIRST` | "Before building new, check if an existing repo/service/module covers 80%+ of the need" | Appears in A3, S2, Phase 1 Task 5, v3 non-negotiables | **Promote.** Already a non-negotiable — formalize as operator `~>!>` (requires existing-work scan before new-work proposal). |
| `R:PROVENANCE_REQUIRED` | "Every claim carries typed evidence with source_id + timestamp + hash" | Appears in A4, §3 Entities, Task 10, Task 28 | **Promote.** Foundational for compounding value. |
| `E:KERNEL` | Single typed referent for `decision-engine` v2 at one deployed URL at one version | Used throughout §11 | **Promote as typed entity.** |
| `E:SURFACE` | Typed referent for any Decision-submitting client | Used throughout | **Promote as typed entity.** |
| `O:VERDICT` | Enum outcome: `auto_execute` \| `escalate_tier_1` \| `escalate_tier_2` \| `block` \| `needs_data` | Kernel output | **Promote as typed enum.** |
| `@rev` | Reversibility marker, float 0–1 | Used in Decision schema, risk thresholds | **Promote as operator.** |

Recommended registry version bump: `token-registry.md v0.1 → v0.2` after Todd review.

---

## 14. Six-Dimension Scoring

| Dimension | Score | Justification |
|---|---|---|
| Truth Integrity | 5/5 | One kernel enforces A1. Provenance graph enforces A4. Cross-language validator spot-checks applied. |
| Compression Efficiency | 4/5 | 21 artifacts → ~6 deployed services + 1 surface + 1 kernel. Seven new promotion candidates surfaced. |
| Ambiguity | 4/5 | Typed entities (`E:KERNEL`, `E:SURFACE`), typed enums (`O:VERDICT`), versioned API contract. Minor residual around "spoke integration" scope per repo. |
| Execution Usefulness | 5/5 | 30 ordered tasks, each shippable in hours-to-days, each producing independent value. |
| ROI / Decision | 5/5 | First shippable value in Week 1 (kernel deployed). Compounding value by Week 6 (every high-stakes decision governed). |
| Audit Recovery | 5/5 | This proof + kernel version + token registry version + provenance graph = full reconstruction of any Decision. |

**Composite: 4.67 / 5**

---

## 15. Next Best Step

**Start with Phase 0 Task 1 (rotate the leaked PAT) in the next 30 minutes.** Nothing else in this plan is safe to execute while that token is live. After rotation, Phase 1 Task 4 (tag `decision-engine` v2 as `v2.0.0` and freeze the API contract) is the highest-leverage technical step — it establishes the single source of truth that all 29 remaining tasks converge on.

---

## Appendix A — Repo → Role Map (Quick Reference)

| Repo | Account | Role in Unified Engine | Phase |
|---|---|---|---|
| `decision-engine` | todd-gig | **KERNEL** | 1 |
| `claude_decision_logic_pack` | todd-gig | Source → merged into KERNEL, archived | 1 |
| `gigaton-language` plugin | — | **REASONING PROTOCOL** carried in every request | 1 |
| `transcript-knowledge-base` | todd-gig | **INGESTION SPINE** | 2 |
| `bella-byte/Gigaton-UI-Platform` | bella-byte | **CANONICAL SURFACE** (after Next.js migration) | 3 |
| `gigaton-ui-system` | todd-gig | Source → `@gigaton/chat` package, archived | 3 |
| `gigaton` | todd-gig | Source → `@gigaton/intake` package, archived | 3 |
| `LiqueFex-Platform-Ui` | todd-gig | Visual reference only, archived | 3 |
| `bella-byte/Liquifex-fluidity-presentations` | bella-byte | Client deliverable surface | 3 |
| `gigaton-platform-ui` | todd-gig | Turborepo scaffold — migration target | 3 |
| `gigaton-engine` | todd-gig | **SPOKE** — pricing/margin/supervisor | 4 |
| `sales-operating-system` | todd-gig | **SPOKE** — catalog/recommendations | 4 |
| `Carmen-Beach-Properties` | todd-gig | **SPOKE** + deployment reference | 4 |
| `intelligence-silo` | todd-gig | **SPOKE** — SLM evidence into provenance | 4 |
| `gigaton-core` | local (not git) | **AI GATEWAY** service — mount into Surface `/chat` | 3 |
| `MD-Files` | todd-gig | Archive indexed into provenance graph | 6 |
| `master-knowledge-base` | todd-gig | Archive indexed into provenance graph | 6 |
| `braintrust-knowledge-base` | todd-gig | Archive indexed into provenance graph | 6 |
| `Carmen-Beach-Properties` (client) | todd-gig | Revenue-facing, consumes KERNEL for admin ops | 4 |
| `Interactive-Presentation---Claude-Education` | todd-gig | Revenue-facing, no kernel integration needed | — |
| `github-multiaccount` | local | Credential tooling — scrub + retain | 0 |

---

## Appendix B — Kernel API Contract (Locked in Phase 1 Task 4)

```
POST   /v1/decisions                       # Submit a Decision + conical_proof
GET    /v1/decisions/{id}                  # Fetch Decision with verdict + proof
GET    /v1/decisions?status=&surface=&...  # Query
POST   /v1/decisions/{id}/outcome          # Write back actual outcome
GET    /v1/meta/compatibility              # API version + token-registry version
GET    /v1/provenance/{evidence_id}        # Read evidence node
POST   /v1/provenance                      # Write evidence node
GET    /v1/tokens                          # Current token registry
POST   /v1/tokens/candidates               # Surface promotion candidate
```

All requests authenticate via Firebase Auth JWT. All responses include `kernel_version`, `token_registry_version`, `trace_id`.

---

*Generated under `gigaton-language` skill v0.1.0. Proof CP-2026-04-13-002. Composite score 4.67/5.*
