# Drift Sentinel

Recursive drift detector for the Gigaton ecosystem. Walks every codebase, GitHub repo, Drive doc, ClickUp task, and local document; grades each artifact against the canonical philosophy and emits a drift report.

## Files in this directory

| File | Purpose |
|---|---|
| `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` | The single source of truth — distilled from all 4 code stacks + MD Files + Downloads + master KB |
| `DRIFT_RULES.yaml` | Machine-readable rules, one per anti-pattern / principle violation |
| `DRIFT_SCANNER_SPEC.md` | Architecture: adapters, rule engine, reporter, recursion semantics |
| `drift_scan.py` | Working CLI scanner — local + downloads adapters fully implemented; github/drive/clickup are MCP-driven stubs |
| `reports/` | Drift reports (JSON + Markdown) per run |
| `drift_history.db` | SQLite — scan history, trend tracking, rule-promotion / retirement signals |

## Quickstart

```bash
cd /Users/admin/Documents/GitHub/decision-engine/drift_sentinel

# Scan all local codebases under ~/Documents/GitHub
python drift_scan.py --source local_codebase

# Include local philosophy docs from Downloads
python drift_scan.py --source local_codebase,downloads

# CI gate — exit 1 on any critical drift
python drift_scan.py --source local_codebase --fail-on critical
```

Reports land in `reports/drift_<timestamp>.{json,md}`. SQLite history at `drift_history.db`.

## How it ensures no drift from purpose

1. **Canonical anchor** — `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` consolidates all philosophy sources. The scanner cross-references every artifact against this doc.
2. **Recursive flywheel** — after each scan, rule firing rates feed back: rules that fire >10× across the ecosystem get promoted; rules that never fire get retired (principle internalized).
3. **Severity-action map** — critical drift blocks deploy; major drift opens a PR comment; minor drift logs to weekly digest; info-level documents intentional overrides.
4. **Self-doctrine compliance** — the Sentinel itself satisfies its own rules (see `DRIFT_SCANNER_SPEC.md` §Self-Doctrine).

## Extending

- **New rule:** append to `DRIFT_RULES.yaml`, optionally add a structural handler in `drift_scan.py` `STRUCTURAL_HANDLERS`.
- **New source:** add an adapter class implementing `stream() → Iterator[Artifact]`, register in `ADAPTERS`.
- **MCP-backed sources** (Drive, ClickUp, GitHub): the scanner's stub adapters define the interface; full implementations live in the MCP-aware Claude Code session that invokes them.

## Source-of-truth precedence

If `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` and any individual stack's CLAUDE.md disagree, the canonical doc wins until the conflict is resolved by formal governance review per `MASTER_FIRST_PRINCIPLES_REFERENCE.md` §19.
