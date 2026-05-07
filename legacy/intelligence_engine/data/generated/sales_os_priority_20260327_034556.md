# Sales OS — Backlog Priority Report
*Generated 2026-03-27 03:45 UTC by Intelligence Engine*

> All 22 backlog items scored through the 9-stage decision pipeline.
> Priority score = weighted value × trust × RTQL multiplier × alignment.
> Verdict governs authorization: `auto_execute` = proceed immediately.

---

## Priority Ranking

| # | Sprint | Priority | Net Value | Trust | Verdict | Item |
|---|--------|----------|-----------|-------|---------|------|
| ★ 1 | S1 | 0.000 | 0.0 | T0 | `unknown` | **Monorepo scaffold** |
| ★ 2 | S1 | 0.000 | 0.0 | T0 | `unknown` | **SQLite schema** |
| ★ 3 | S1 | 0.000 | 0.0 | T0 | `unknown` | **Seed data import from spreadsheet** |
| ★ 4 | S1 | 0.000 | 0.0 | T0 | `unknown` | **Catalog CRUD** |
| ★ 5 | S1 | 0.000 | 0.0 | T0 | `unknown` | **Bundles CRUD** |
| 6 | S2 | 0.000 | 0.0 | T0 | `unknown` | **Opportunities and clients** |
| 7 | S2 | 0.000 | 0.0 | T0 | `unknown` | **Need-state mapping** |
| 8 | S2 | 0.000 | 0.0 | T0 | `unknown` | **Recommendation engine** |
| 9 | S2 | 0.000 | 0.0 | T0 | `unknown` | **Dashboard summaries** |
| 10 | S3 | 0.000 | 0.0 | T0 | `unknown` | **Google OAuth** |
| 11 | S3 | 0.000 | 0.0 | T0 | `unknown` | **Sheets import/export** |
| 12 | S3 | 0.000 | 0.0 | T0 | `unknown` | **Docs artifact generation** |
| 13 | S3 | 0.000 | 0.0 | T0 | `unknown` | **Gmail draft support** |
| 14 | S4 | 0.000 | 0.0 | T0 | `unknown` | **Agent runtime** |
| 15 | S4 | 0.000 | 0.0 | T0 | `unknown` | **Agent template management** |
| 16 | S4 | 0.000 | 0.0 | T0 | `unknown` | **Workflow runner** |
| 17 | S4 | 0.000 | 0.0 | T0 | `unknown` | **Execution history** |
| 18 | S5 | 0.000 | 0.0 | T0 | `unknown` | **Proposal builder** |
| 19 | S5 | 0.000 | 0.0 | T0 | `unknown` | **Deck builder** |
| 20 | S5 | 0.000 | 0.0 | T0 | `unknown` | **Follow-up builder** |
| 21 | S5 | 0.000 | 0.0 | T0 | `unknown` | **Bundle recommendation UI** |
| 22 | S6 | 0.000 | 0.0 | T0 | `unknown` | **Evaluation logging** |
| 23 | S6 | 0.000 | 0.0 | T0 | `unknown` | **Dataset export** |
| 24 | S6 | 0.000 | 0.0 | T0 | `unknown` | **Prompt profile versioning** |
| 25 | S6 | 0.000 | 0.0 | T0 | `unknown` | **Approval system hardening** |

---

## Top 5 — Build Immediately

### 1. Monorepo scaffold (Sprint 1)

- **Priority score**: 0.000
- **Net value**: 0.0
- **Verdict**: `unknown`
- **Trust tier**: T0
- **Rationale**: Zero-value on its own but unblocks everything. High reversibility — scaffold can be restructured cheaply early. No revenue until paired with working features.

### 2. SQLite schema (Sprint 1)

- **Priority score**: 0.000
- **Net value**: 0.0
- **Verdict**: `unknown`
- **Trust tier**: T0
- **Rationale**: Foundational — every feature reads/writes this schema. Bad schema now = expensive migration later. High compounding: gets reused by every sprint.

### 3. Seed data import from spreadsheet (Sprint 1)

- **Priority score**: 0.000
- **Net value**: 0.0
- **Verdict**: `unknown`
- **Trust tier**: T0
- **Rationale**: Unlocks real data for every downstream feature. Without it, catalog CRUD and recommendation engine are hollow. Spreadsheet is the source of truth today — capturing it is step 1.

### 4. Catalog CRUD (Sprint 1)

- **Priority score**: 0.000
- **Net value**: 0.0
- **Verdict**: `unknown`
- **Trust tier**: T0
- **Rationale**: The operational heart of the system. Sales team can't use any output if the catalog can't be maintained. Straightforward to build once schema exists.

### 5. Bundles CRUD (Sprint 1)

- **Priority score**: 0.000
- **Net value**: 0.0
- **Verdict**: `unknown`
- **Trust tier**: T0
- **Rationale**: Bundles are the primary revenue mechanism — upsell/cross-sell logic depends on them. Closely related to catalog CRUD but distinct entity with dependency rules. Needed before recommendation engine can 

---

## Defer / Sequence After Dependencies

Items ranked 6–22 should be sequenced after their upstream dependencies are stable.

- **6. Opportunities and clients** (S2) — priority 0.000, verdict `unknown`
- **7. Need-state mapping** (S2) — priority 0.000, verdict `unknown`
- **8. Recommendation engine** (S2) — priority 0.000, verdict `unknown`
- **9. Dashboard summaries** (S2) — priority 0.000, verdict `unknown`
- **10. Google OAuth** (S3) — priority 0.000, verdict `unknown`
- **11. Sheets import/export** (S3) — priority 0.000, verdict `unknown`
- **12. Docs artifact generation** (S3) — priority 0.000, verdict `unknown`
- **13. Gmail draft support** (S3) — priority 0.000, verdict `unknown`
- **14. Agent runtime** (S4) — priority 0.000, verdict `unknown`
- **15. Agent template management** (S4) — priority 0.000, verdict `unknown`
- **16. Workflow runner** (S4) — priority 0.000, verdict `unknown`
- **17. Execution history** (S4) — priority 0.000, verdict `unknown`
- **18. Proposal builder** (S5) — priority 0.000, verdict `unknown`
- **19. Deck builder** (S5) — priority 0.000, verdict `unknown`
- **20. Follow-up builder** (S5) — priority 0.000, verdict `unknown`
- **21. Bundle recommendation UI** (S5) — priority 0.000, verdict `unknown`
- **22. Evaluation logging** (S6) — priority 0.000, verdict `unknown`
- **23. Dataset export** (S6) — priority 0.000, verdict `unknown`
- **24. Prompt profile versioning** (S6) — priority 0.000, verdict `unknown`
- **25. Approval system hardening** (S6) — priority 0.000, verdict `unknown`

---

## Scoring Methodology

Each item was processed through the full 9-stage pipeline:
1. **RTQL pre-filter** — trust-qualifies the evidence claim behind each item
2. **Value assessment** — scores 8 value dimensions + 4 penalty dimensions
3. **Trust assessment** — scores 7 trust inputs → trust tier T0–T4
4. **Authority check** — validates owner has authority for decision class
5. **Alignment check** — doctrine + ethos + first-principles composite
6. **Certificate chain** — QC → VC → TC → EC issuance
7. **7-Gate authorization** — Doctrine, Trust, Value, Reversibility, Risk, Approval, Monitoring
8. **State machine** — final state transition
9. **Audit trail** — full evidence chain recorded to SQLite

*25 items processed, 0 errors*