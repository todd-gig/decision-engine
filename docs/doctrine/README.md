# Foundational Doctrine — repo mirror

This directory mirrors the 4 **FOUNDATIONAL** Gigaton doctrine memories so engines + tests + agents can reference them by repo-relative path (instead of `~/.claude/projects/-Users-admin/memory/...` which only resolves on the author's machine).

## What lives here

| File | Doctrine | Established |
|---|---|---|
| [foundational_goal_gigaton_engineered_brand_experience.md](foundational_goal_gigaton_engineered_brand_experience.md) | **PPIM** — "Facilitate predictably profitable interaction management of a gigaton engineered brand experience" | 2026-05-16 |
| [foundational_modular_replication_via_input_substitution.md](foundational_modular_replication_via_input_substitution.md) | **HOW PPIM SCALES** — multi-axis tagged catalogs + operator_context input substitution | 2026-05-16 |
| [universal_connector_hub_architecture.md](universal_connector_hub_architecture.md) | **THE GIGATON PRODUCT** — universal connector + intelligence layer | 2026-05-16 |
| [feedback_web_search_for_data_backfill.md](feedback_web_search_for_data_backfill.md) | Web-search for missing/stale data with citation | 2026-05-16 |

## Source of truth

These files are **mirrors**, not originals. Originals live in the author's auto-memory at `~/.claude/projects/-Users-admin/memory/`. When a doctrine memory is updated, this mirror must be refreshed (see "Refresh procedure" below).

The repo mirror is authoritative *for code that needs a repo-relative path* (tests, docstrings, README links). The auto-memory copy is authoritative *for cross-session agent context*.

## Refresh procedure

When a foundational memory is updated:

```bash
# From repo root:
cp ~/.claude/projects/-Users-admin/memory/foundational_*.md docs/doctrine/
cp ~/.claude/projects/-Users-admin/memory/universal_connector_hub_architecture.md docs/doctrine/
cp ~/.claude/projects/-Users-admin/memory/feedback_web_search_for_data_backfill.md docs/doctrine/
git add docs/doctrine/ && git commit -m "docs(doctrine): refresh mirror from auto-memory"
```

## Why mirror at all

1. **Tests + docstrings** can link to repo-relative paths that work in CI + on other developers' machines
2. **NotebookLM** uploads need files at stable paths so the source registry can re-fetch
3. **Drift-sentinel** can scan for doctrine-claim ≠ committed-code by comparing the mirror version to the code that claims to implement it
4. **Audit trail** — `git log docs/doctrine/` shows the evolution of doctrine alongside the code that implements it

## Anti-patterns

- ❌ Editing files here directly. Edit the auto-memory original first, then refresh.
- ❌ Referencing `~/.claude/projects/-Users-admin/memory/...` in code, tests, or PR bodies. Use `docs/doctrine/<file>.md` paths.
- ❌ Letting the mirror drift > 7 days behind auto-memory.
