# Intelligence Engine — absorbed precursor

This directory is a verbatim copy of `intelligence-engine/` from the `MD-Files` repo
(`todd-gig/MD-Files`), absorbed into `decision-engine` so all code lives in one
canonical home. The original is now marked superseded.

## Why this lives under `legacy/`

`decision-engine` v2.0 is the production successor of this code. They implement the
same conceptual pipeline (RTQL → trust × value × authority → certificates → state
machine) and have heavy file-level overlap (engine/scoring, gates, certificates,
authority, learning_loop, pipeline, rtql_filter, state_machine, etc.).

Rather than diff-merge file-by-file (risk of silent loss), the full precursor is
preserved here and decision-engine v2 remains the authoritative implementation.
Future PRs can dedup file-by-file as code paths get exercised.

## Unique pieces worth surfacing

These have no equivalent in the v2 implementation and should be considered for
promotion out of `legacy/` into a first-class location:

- `bridge/claude_bridge.py` — Claude API bridge
- `api/translation/{openai,gemini,claude}_encoder.py` — multi-LLM translation layer
- `loaders/sales_os_backlog.py` — Sales OS backlog ingestion (ran successfully 2026-03-30)
- `analyze_reddit_memory.py` — Reddit memory analyzer (~20K LOC standalone tool)
- `ingestion/human_variable_intake.py` — human variable intake
- `data/generated/` — historical intelligence briefs and Sales-OS priority reports
  (provenance / training-data candidates)

## Source provenance

Source path: `MD-Files/intelligence-engine/`

Originating commits in `todd-gig/MD-Files`:

| Commit | Date | Message |
| --- | --- | --- |
| `abd9795` | 2026-03-26 | Add intelligence-engine: end-to-end causal decision governance system |
| `bec3899` | 2026-03-26 | Add Sales OS backlog loader and priority report |
| `20ae136` | 2026-03-30 | Add certification pipeline, Reddit memory analysis, db.py fix, and generated artifacts |
| `3f80f9d` | 2026-04-09 | sync: 2026-04-09 — api/main.py, engine_middleware, models, session_store |

Absorbed into `decision-engine` on 2026-05-07.

## Status

`legacy/` content is **not on the import path** by default and is not run as part of
decision-engine's deployment. Treat it as read-only reference material until specific
files are deliberately promoted.
