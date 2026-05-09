# Drift Sentinel — Scanner Specification

How the recursive drift detector walks every source and grades each artifact against `GIGATON_CANONICAL_FIRST_PRINCIPLES.md` + `DRIFT_RULES.yaml`.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Drift Sentinel CLI                         │
│  python drift_scan.py --source <local|github|drive|clickup|all>   │
└──────────────────────────────────┬────────────────────────────────┘
                                   │
                ┌──────────────────┼───────────────────┐
                ▼                  ▼                   ▼
        ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
        │  Adapters    │   │  Rule Engine │   │  Reporter    │
        │  (per source)│   │  (yaml rules)│   │  (json + md) │
        └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
               │                  │                   │
               ▼                  ▼                   ▼
       ┌────────────────┐  ┌─────────────┐   ┌──────────────┐
       │ Artifact Stream│→ │ Find        │ → │ DRIFT REPORT │
       │ (file/doc/task)│  │ Violations  │   │  + summary   │
       └────────────────┘  └─────────────┘   └──────────────┘
```

## Source Adapters (pluggable)

Each adapter yields a stream of `Artifact` objects with this contract:

```python
@dataclass
class Artifact:
    source: str           # "local_codebase" | "github" | "drive" | "clickup" | "downloads"
    artifact_type: str    # "code" | "markdown" | "decision" | "task" | "doc"
    identifier: str       # path | URL | task_id
    content: str          # full or chunked text
    metadata: dict        # extra fields (lang, repo, owner, etc.)
```

### 1. LocalCodebaseAdapter
- Walks `/Users/admin/Documents/GitHub/<repo>/`
- Skips: `node_modules`, `__pycache__`, `.git`, `.next`, `dist`, `build`, `.turbo`
- Reads: `*.ts`, `*.tsx`, `*.py`, `*.md`, `*.yaml`, `*.json` (package.json, tsconfig)
- Per-repo budget: max 500 files (rank by mtime; recent first)
- Special files extracted into structured fields:
  - `CLAUDE.md` → captured as doctrine claim
  - `package.json` / `pyproject.toml` → dependency manifest
  - `schema.prisma` → entity manifest
  - `CAPABILITY_AUDIT.md` (if present) → capability-shipment claims
  - `cloudbuild.yaml` / `Dockerfile` → infra commitments

### 2. LocalDocsAdapter
- Walks `/Users/admin/Downloads/` and `/Users/admin/Documents/`
- Reads: `*.md`, `*.pdf` (text-extracted), `*.docx` (text-extracted)
- Filters: ignore files older than 1 year unless title contains gigaton-relevant keywords
- Keyword whitelist: `gigaton, attractor, smen, sovereign, sie, rtql, value matrix, decision engine, claude automation, doctrine, principle, methodology, dvm, conical proof, causal chain`

### 3. GithubAdapter
- Uses `gh CLI` (already authenticated)
- For each user account in `source_routing.github_remote.accounts`:
  - List repos: `gh repo list <account> --limit 100 --json name,description,updatedAt`
  - For each repo: pull README + CLAUDE.md + recent PRs/issues via `gh api`
- Surfaces: open PRs, recent commits, issue templates, README claims
- Caches results per-day

### 4. DriveAdapter
- Uses Drive MCP (`mcp__claude_ai_Google_Drive__*`)
- For each account in `source_routing.google_drive.accounts`:
  - Searches by keyword whitelist (same as LocalDocsAdapter)
  - Recent files first (modifiedTime DESC)
  - Reads content via `read_file_content` for top 50 hits per account
- Output: doc title + path + extracted body

### 5. ClickUpAdapter
- Uses ClickUp MCP (`mcp__claude_ai_ClickUp__*`)
- Pulls workspace hierarchy → tasks per list
- Per task: title, description, owner, status, custom fields
- Filter: open or recently-updated tasks only (last 90 days)

---

## Rule Engine

### Loading
- Reads `DRIFT_RULES.yaml`
- Each rule compiles into a `Check` callable: `(Artifact) → list[Violation]`

### Detection types

| Type | What it does |
|---|---|
| `regex` | Run patterns against artifact content; each match is a violation |
| `structural` | Custom Python predicate (provided in adapter or `checks/` module) |
| `field_value` | Parse YAML/JSON frontmatter or decision schema; check field thresholds |
| `missing_field` | Verify required fields exist and are non-empty |
| `ratio` | Compute a metric (comment/code, LOC/test) and check threshold |
| `telemetry` | Read from external log/DB (e.g. decision audit log) for codification rules |

### Violation record

```python
@dataclass
class Violation:
    rule_id: str
    severity: str          # critical | major | minor | info
    artifact: str          # identifier
    location: str | None   # file:line / row / pdf:page
    excerpt: str | None    # snippet showing the violation
    suggested_fix: str
```

---

## Recursive Loop

The scanner is **recursive** in two senses:

### 1. Structural recursion
Each adapter yields nested artifacts (repo → file → function-block). Rules can target any nesting level.

### 2. Outcome-feedback recursion (the Gigaton flywheel applied to itself)
After each scan run:
1. Persist violations to SQLite (`drift_history.db`)
2. Compute drift trend per repo / per rule (week-over-week)
3. If a rule fires >10× across the ecosystem, flag for **rule promotion** (move from MAJ → CRIT, OR from text-rule to gating CI hook)
4. If a rule never fires for >6 months, flag for **rule retirement** (principle is fully internalized; no longer needs detection)
5. Feed the codification backlog (per Decision Routing Framework §5.8)

---

## Severity → Action Map

| Severity | Action | Where |
|---|---|---|
| `critical` | Block deploy via CI; alert operator immediately; cannot ship until fixed or formally overridden | Cloud Build pre-deploy hook + Slack alert |
| `major` | Open PR comment; require human review; track in weekly drift report | GitHub PR check + ClickUp ticket |
| `minor` | Log to drift report; track trend | Weekly digest |
| `info` | Acknowledge override; persist exception_id | History only |

---

## Output Formats

### JSON (`reports/drift_<timestamp>.json`)
```json
{
  "scan_id": "uuid",
  "timestamp": "2026-05-05T...",
  "sources": ["local_codebase"],
  "summary": {
    "total_artifacts": 4521,
    "violations": {"critical": 3, "major": 17, "minor": 84, "info": 12}
  },
  "violations": [
    {
      "rule_id": "CRIT-003",
      "severity": "critical",
      "artifact": "gigaton-engine/main.py:142",
      "location": "main.py:142",
      "excerpt": "client.messages.create(model=...) ... (no prompt_version)",
      "suggested_fix": "Attach prompt_version + schema_version to every prod LLM call."
    }
  ],
  "trends": {
    "week_over_week_critical_delta": -2,
    "rules_firing_most": [{"rule_id": "MIN-001", "count": 47}]
  }
}
```

### Markdown (`reports/drift_<timestamp>.md`)
- Executive summary (drift health: GREEN/YELLOW/RED)
- Violations grouped by severity → rule → artifact
- Per-source rollup
- Top remediation candidates (high-leverage fixes)
- Trend graph (count over time per severity)

---

## Integration Hooks

### CI / pre-deploy
```bash
# .github/workflows/drift-check.yml
- name: Drift Sentinel
  run: python drift_sentinel/drift_scan.py --source local_codebase --fail-on critical
```

### Weekly digest (Cloud Scheduler → Cloud Run job)
```bash
python drift_scan.py --source all --report weekly --post-to slack
```

### Pre-PR (developer local)
```bash
python drift_scan.py --source local_codebase --since-commit HEAD~5
```

### Manual deep scan (operator-triggered)
```bash
python drift_scan.py --source all --deep --persist
```

---

## Extension Points

Adding a new rule:
1. Append to `DRIFT_RULES.yaml` with stable ID (CRIT-NNN / MAJ-NNN / etc.)
2. If detection type is `structural` → add a check function to `checks/<rule_id>.py`
3. If it requires a new field on the canonical doc → update `GIGATON_CANONICAL_FIRST_PRINCIPLES.md`
4. Run scanner against existing repos to baseline the new rule's hit rate
5. If hit rate is too high to be useful (>30% of artifacts), the rule is too strict → split or relax

Adding a new source:
1. Create `adapters/<source>_adapter.py` implementing the `Artifact` yield contract
2. Register in `drift_scan.py` adapter registry
3. Add `source_routing.<source>` block to `DRIFT_RULES.yaml` listing applicable rule IDs

---

## Self-Doctrine Compliance

The Drift Sentinel itself MUST satisfy its own doctrine:
- ✅ `prompt_version` not applicable (deterministic, no LLM in core scanner)
- ✅ `audit log` — persists every scan to `drift_history.db`
- ✅ `human override` — `--fail-on never` flag for forced override (logs warning)
- ✅ `provider abstraction` — adapters are pluggable
- ✅ `idempotency` — re-running same scan produces same output (deterministic)
- ✅ `versioned rules` — `version` field in `DRIFT_RULES.yaml`; rule changes require ADR
- ✅ `local-first` — works fully offline against local sources without GCP/Drive/ClickUp
- ✅ `learning loop` — scan history feeds rule promotion/retirement
