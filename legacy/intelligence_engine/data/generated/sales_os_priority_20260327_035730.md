# Sales OS — Backlog Priority Report
*Generated 2026-03-27 03:57 UTC by Intelligence Engine*

> All 22 backlog items scored through the 9-stage decision pipeline.
> Priority score = weighted value × trust × RTQL multiplier × alignment.
> Verdict governs authorization: `auto_execute` = proceed immediately.

---

## Priority Ranking

| # | Sprint | Priority | Net Value | Trust | Verdict | Item |
|---|--------|----------|-----------|-------|---------|------|
| ★ 1 | S3 | 27.821 | 32.0 | T4 | `escalate_tier_1` | **Docs artifact generation** |
| ★ 2 | S5 | 27.821 | 32.0 | T4 | `escalate_tier_1` | **Proposal builder** |
| ★ 3 | S2 | 21.561 | 31.0 | T4 | `escalate_tier_1` | **Opportunities and clients** |
| ★ 4 | S2 | 21.010 | 29.0 | T3 | `escalate_tier_2` | **Recommendation engine** |
| ★ 5 | S2 | 20.286 | 28.0 | T3 | `escalate_tier_1` | **Need-state mapping** |
| 6 | S4 | 19.561 | 27.0 | T3 | `escalate_tier_2` | **Workflow runner** |
| 7 | S4 | 17.790 | 26.0 | T3 | `escalate_tier_2` | **Agent runtime** |
| 8 | S5 | 16.229 | 28.0 | T3 | `escalate_tier_1` | **Bundle recommendation UI** |
| 9 | S1 | 15.997 | 23.0 | T4 | `escalate_tier_1` | **SQLite schema** |
| 10 | S1 | 15.968 | 29.0 | T4 | `auto_execute` | **Bundles CRUD** |
| 11 | S1 | 15.023 | 27.0 | T4 | `escalate_tier_1` | **Seed data import from spreadsheet** |
| 12 | S3 | 14.467 | 26.0 | T4 | `escalate_tier_1` | **Sheets import/export** |
| 13 | S3 | 13.354 | 24.0 | T4 | `escalate_tier_1` | **Google OAuth** |
| 14 | S1 | 11.476 | 22.0 | T4 | `auto_execute` | **Monorepo scaffold** |
| 15 | S5 | 10.948 | 25.0 | T3 | `auto_execute` | **Deck builder** |
| 16 | S1 | 10.850 | 26.0 | T4 | `auto_execute` | **Catalog CRUD** |
| 17 | S4 | 9.634 | 22.0 | T3 | `escalate_tier_1` | **Agent template management** |
| 18 | S6 | 7.651 | 22.0 | T3 | `escalate_tier_1` | **Prompt profile versioning** |
| 19 | S5 | 7.554 | 23.0 | T3 | `auto_execute` | **Follow-up builder** |
| 20 | S6 | 7.245 | 25.0 | T3 | `escalate_tier_1` | **Evaluation logging** |
| 21 | S6 | 6.975 | 19.0 | T4 | `escalate_tier_2` | **Approval system hardening** |
| 22 | S4 | 6.677 | 24.0 | T4 | `auto_execute` | **Execution history** |
| 23 | S6 | 6.665 | 23.0 | T3 | `auto_execute` | **Dataset export** |
| 24 | S2 | 4.637 | 20.0 | T3 | `auto_execute` | **Dashboard summaries** |
| 25 | S3 | 4.405 | 19.0 | T3 | `auto_execute` | **Gmail draft support** |

---

## Top 5 — Build Immediately

### 1. Docs artifact generation (Sprint 3)

- **Priority score**: 27.821
- **Net value**: 32.0
- **Verdict**: `escalate_tier_1`
- **Trust tier**: T4
- **Rationale**: Directly drives 70% proposal time reduction success metric. High user-visible value. Depends on catalog + recommendations data being clean.

### 2. Proposal builder (Sprint 5)

- **Priority score**: 27.821
- **Net value**: 32.0
- **Verdict**: `escalate_tier_1`
- **Trust tier**: T4
- **Rationale**: Most visible user-facing output. Directly tied to 70% time reduction success metric. Depends on workflow runner and artifact generation being stable.

### 3. Opportunities and clients (Sprint 2)

- **Priority score**: 21.561
- **Net value**: 31.0
- **Verdict**: `escalate_tier_1`
- **Trust tier**: T4
- **Rationale**: The demand side of the system. Without clients and opportunities, recommendation engine has no context to work against. Required before need-state mapping is meaningful.

### 4. Recommendation engine (Sprint 2)

- **Priority score**: 21.010
- **Net value**: 29.0
- **Verdict**: `escalate_tier_2`
- **Trust tier**: T3
- **Rationale**: The primary value generator. Success metric: 80% reduction in time to produce upsell path. Rules-based first — avoids premature ML complexity. Directly tied to revenue outcomes.

### 5. Need-state mapping (Sprint 2)

- **Priority score**: 20.286
- **Net value**: 28.0
- **Verdict**: `escalate_tier_1`
- **Trust tier**: T3
- **Rationale**: The intelligence layer for demand. This is what separates a catalog from a sales engine. High compounding — every recommendation downstream uses this mapping.

---

## Defer / Sequence After Dependencies

Items ranked 6–22 should be sequenced after their upstream dependencies are stable.

- **6. Workflow runner** (S4) — priority 19.561, verdict `escalate_tier_2`
- **7. Agent runtime** (S4) — priority 17.790, verdict `escalate_tier_2`
- **8. Bundle recommendation UI** (S5) — priority 16.229, verdict `escalate_tier_1`
- **9. SQLite schema** (S1) — priority 15.997, verdict `escalate_tier_1`
- **10. Bundles CRUD** (S1) — priority 15.968, verdict `auto_execute`
- **11. Seed data import from spreadsheet** (S1) — priority 15.023, verdict `escalate_tier_1`
- **12. Sheets import/export** (S3) — priority 14.467, verdict `escalate_tier_1`
- **13. Google OAuth** (S3) — priority 13.354, verdict `escalate_tier_1`
- **14. Monorepo scaffold** (S1) — priority 11.476, verdict `auto_execute`
- **15. Deck builder** (S5) — priority 10.948, verdict `auto_execute`
- **16. Catalog CRUD** (S1) — priority 10.850, verdict `auto_execute`
- **17. Agent template management** (S4) — priority 9.634, verdict `escalate_tier_1`
- **18. Prompt profile versioning** (S6) — priority 7.651, verdict `escalate_tier_1`
- **19. Follow-up builder** (S5) — priority 7.554, verdict `auto_execute`
- **20. Evaluation logging** (S6) — priority 7.245, verdict `escalate_tier_1`
- **21. Approval system hardening** (S6) — priority 6.975, verdict `escalate_tier_2`
- **22. Execution history** (S4) — priority 6.677, verdict `auto_execute`
- **23. Dataset export** (S6) — priority 6.665, verdict `auto_execute`
- **24. Dashboard summaries** (S2) — priority 4.637, verdict `auto_execute`
- **25. Gmail draft support** (S3) — priority 4.405, verdict `auto_execute`

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