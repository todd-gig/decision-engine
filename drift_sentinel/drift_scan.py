"""
Drift Sentinel — recursive drift detector for the Gigaton ecosystem.

Walks codebases, GitHub, Drive, Downloads, and ClickUp; grades every artifact
against DRIFT_RULES.yaml (which encodes GIGATON_CANONICAL_FIRST_PRINCIPLES.md).

CLI:
    python drift_scan.py --source local_codebase
    python drift_scan.py --source all --report-format markdown
    python drift_scan.py --source local_codebase --fail-on critical

Self-doctrine: deterministic, audit-logged, idempotent, local-first.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Callable

try:
    import yaml
except ImportError:
    sys.exit("Drift Sentinel requires pyyaml: pip install pyyaml")

ROOT = Path(__file__).resolve().parent
RULES_FILE = ROOT / "DRIFT_RULES.yaml"
HISTORY_DB = ROOT / "drift_history.db"
REPORTS_DIR = ROOT / "reports"


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class Artifact:
    source: str
    artifact_type: str
    identifier: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Violation:
    rule_id: str
    severity: str
    artifact: str
    location: str | None
    excerpt: str | None
    suggested_fix: str


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

class LocalCodebaseAdapter:
    """Walks /Users/admin/Documents/GitHub/<repo>/ for code + doctrine files."""

    SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".next", "dist",
                 "build", ".turbo", ".venv", "venv", "generated",
                 "__generated__", ".cache", "coverage"}
    INCLUDE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".md", ".yaml",
                   ".yml", ".json", ".prisma", ".sql"}

    def __init__(self, config: dict):
        self.root = Path(config["root"])
        self.include_repos = set(config.get("include_repos", []))
        self.max_files_per_repo = 500

    def stream(self) -> Iterator[Artifact]:
        for repo_dir in sorted(self.root.iterdir()):
            if not repo_dir.is_dir():
                continue
            if self.include_repos and repo_dir.name not in self.include_repos:
                continue
            yield from self._walk_repo(repo_dir)

    def _walk_repo(self, repo: Path) -> Iterator[Artifact]:
        files: list[Path] = []
        for path in repo.rglob("*"):
            if any(part in self.SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in self.INCLUDE_EXT:
                files.append(path)
        # mtime DESC, cap to budget
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[: self.max_files_per_repo]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            atype = self._classify(path)
            yield Artifact(
                source="local_codebase",
                artifact_type=atype,
                identifier=str(path.relative_to(self.root)),
                content=content,
                metadata={"repo": repo.name, "ext": path.suffix,
                          "size": len(content)},
            )

    @staticmethod
    def _classify(path: Path) -> str:
        if path.suffix == ".md":
            return "markdown"
        if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".py"}:
            return "code"
        if path.suffix in {".yaml", ".yml", ".json"}:
            return "config"
        if path.suffix == ".prisma":
            return "schema"
        return "other"


class LocalDocsAdapter:
    """Walks Downloads + Documents for high-signal philosophy docs."""

    KEYWORDS = re.compile(
        r"gigaton|attractor|smen|sovereign|sie|rtql|value matrix|"
        r"decision engine|claude automation|doctrine|principle|"
        r"methodology|dvm|conical proof|causal chain",
        re.IGNORECASE,
    )

    def __init__(self, config: dict):
        self.roots = [Path(r) for r in config.get(
            "roots", ["/Users/admin/Downloads"])]
        self.exts = set(config.get("include_extensions",
                                   [".md", ".txt", ".pdf", ".docx"]))
        self.max_per_root = 200

    def stream(self) -> Iterator[Artifact]:
        for root in self.roots:
            if not root.exists():
                continue
            yield from self._walk(root)

    def _walk(self, root: Path) -> Iterator[Artifact]:
        candidates: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in self.exts:
                continue
            if not (self.KEYWORDS.search(path.name)
                    or self.KEYWORDS.search(str(path.parent))):
                continue
            candidates.append(path)
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates[: self.max_per_root]:
            try:
                if path.suffix.lower() == ".md":
                    content = path.read_text(
                        encoding="utf-8", errors="ignore")
                else:
                    # Stub: PDF/docx extraction handled in production extension
                    content = f"[binary: {path.name}]"
                yield Artifact(
                    source="downloads",
                    artifact_type="doc",
                    identifier=str(path),
                    content=content,
                    metadata={"ext": path.suffix.lower()},
                )
            except (OSError, UnicodeDecodeError):
                continue


class GithubAdapter:
    """Walks GitHub repos for one or more accounts using `gh CLI`.

    Per repo, fetches README and CLAUDE.md (if present). Repos are listed
    via `gh repo list <owner> --json ...`. Files via `gh api`.

    Skips forks, archived repos, and repos older than `max_age_days` (default
    365) unless `include_archived` is true.
    """

    SKIP_NAME_PATTERNS = ("desktop-tutorial",)
    DOCTRINE_FILES = ("README.md", "CLAUDE.md", "AGENTS.md",
                      "PRINCIPLES.md", "DOCTRINE.md", "ARCHITECTURE.md")

    def __init__(self, config: dict):
        import subprocess
        self.accounts = config.get("accounts", ["todd-gig"])
        self.include_archived = config.get("include_archived", False)
        self.max_age_days = config.get("max_age_days", 365)
        self.per_repo_files = config.get("per_repo_files",
                                         self.DOCTRINE_FILES)
        self._subprocess = subprocess
        # Verify gh is available + authenticated
        try:
            r = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, timeout=10)
            if r.returncode != 0:
                print("[github] gh CLI not authenticated; "
                      "adapter will yield 0 artifacts", file=sys.stderr)
                self._available = False
            else:
                self._available = True
        except (FileNotFoundError, OSError) as exc:
            print(f"[github] gh CLI unavailable: {exc}", file=sys.stderr)
            self._available = False

    def _gh_json(self, args: list[str]) -> object:
        """Run a gh subcommand expecting JSON; parse and return."""
        try:
            r = self._subprocess.run(
                ["gh", *args], capture_output=True, text=True, timeout=30)
        except (OSError, self._subprocess.TimeoutExpired) as exc:
            print(f"[github] error running gh {args}: {exc}", file=sys.stderr)
            return None
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return None

    def stream(self) -> Iterator[Artifact]:
        if not self._available:
            return
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        for account in self.accounts:
            repos = self._gh_json([
                "repo", "list", account, "--limit", "100",
                "--json", "name,description,updatedAt,isArchived,isFork",
            ]) or []
            for repo in repos:
                if any(p in repo["name"] for p in self.SKIP_NAME_PATTERNS):
                    continue
                if repo.get("isFork"):
                    continue
                if repo.get("isArchived") and not self.include_archived:
                    continue
                try:
                    updated = datetime.fromisoformat(
                        repo["updatedAt"].replace("Z", "+00:00"))
                except (KeyError, ValueError):
                    updated = datetime.now(timezone.utc)
                if updated < cutoff:
                    continue
                yield from self._scan_repo(account, repo)

    def _scan_repo(self, account: str, repo: dict) -> Iterator[Artifact]:
        repo_name = repo["name"]
        # Yield repo description as an artifact (catches anti-patterns
        # like "stub", "placeholder", "TODO" in description)
        if repo.get("description"):
            yield Artifact(
                source="github",
                artifact_type="markdown",
                identifier=f"github:{account}/{repo_name}#description",
                content=repo["description"],
                metadata={"repo": repo_name, "kind": "description",
                          "updated": repo.get("updatedAt")},
            )
        # Fetch each doctrine file via gh api
        for filename in self.per_repo_files:
            content = self._fetch_file(account, repo_name, filename)
            if not content:
                continue
            yield Artifact(
                source="github",
                artifact_type="markdown",
                identifier=f"github:{account}/{repo_name}/{filename}",
                content=content,
                metadata={"repo": repo_name, "kind": filename,
                          "updated": repo.get("updatedAt")},
            )

    def _fetch_file(self, account: str, repo: str,
                    path: str) -> str | None:
        """Fetch file content via gh api; returns None if not found."""
        try:
            r = self._subprocess.run(
                ["gh", "api", f"repos/{account}/{repo}/contents/{path}",
                 "--jq", ".content"],
                capture_output=True, text=True, timeout=20,
            )
        except (OSError, self._subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        b64 = r.stdout.strip().strip('"')
        if not b64:
            return None
        try:
            import base64
            return base64.b64decode(b64).decode("utf-8", errors="ignore")
        except (ValueError, UnicodeDecodeError):
            return None


class DriveAdapter:
    """Uses Google Drive MCP. Stub — invoke from MCP-aware harness."""

    def __init__(self, config: dict):
        self.accounts = config.get("accounts", [])

    def stream(self) -> Iterator[Artifact]:
        # Production: call mcp__claude_ai_Google_Drive__search_files
        # and mcp__claude_ai_Google_Drive__read_file_content via the
        # parent harness. The CLI scanner is local-first; Drive scanning
        # runs from a Claude Code session that has MCP access.
        return iter([])


class ClickUpAdapter:
    """Uses ClickUp MCP. Stub — invoke from MCP-aware harness."""

    def __init__(self, config: dict):
        pass

    def stream(self) -> Iterator[Artifact]:
        return iter([])


ADAPTERS: dict[str, type] = {
    "local_codebase": LocalCodebaseAdapter,
    "downloads": LocalDocsAdapter,
    "github": GithubAdapter,
    "drive": DriveAdapter,
    "clickup": ClickUpAdapter,
}


# ---------------------------------------------------------------------------
# Rule Engine
# ---------------------------------------------------------------------------

CheckFn = Callable[[Artifact, dict], list[Violation]]


def _check_regex(art: Artifact, rule: dict) -> list[Violation]:
    out: list[Violation] = []
    detection = rule.get("detection", {})
    patterns = detection.get("patterns", [])
    for pat in patterns:
        for m in re.finditer(pat, art.content):
            line_no = art.content[: m.start()].count("\n") + 1
            out.append(Violation(
                rule_id=rule["id"],
                severity=rule["severity"],
                artifact=art.identifier,
                location=f"{art.identifier}:{line_no}",
                excerpt=m.group(0)[:120],
                suggested_fix=rule.get("remediation", ""),
            ))
    return out


def _check_provider_lock_in(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-007: AI/LLM call sites without provider+model abstraction."""
    if art.artifact_type != "code":
        return []
    llm_call = re.search(
        r"(anthropic|openai|client|llm)\.(messages|chat\.completions|"
        r"complete|generate)\.create",
        art.content,
    )
    if not llm_call:
        return []
    has_provider = "provider" in art.content.lower()
    has_model = re.search(r"\bmodel\s*[=:]", art.content)
    if has_provider and has_model:
        return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt="LLM call without provider+model abstraction",
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_prompt_versioning(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-003: prod LLM calls without prompt_version/schema_version."""
    if art.artifact_type != "code":
        return []
    if not re.search(
            r"(messages\.create|chat\.completions\.create)", art.content):
        return []
    has_prompt_v = re.search(r"prompt_version", art.content)
    has_schema_v = re.search(r"schema_version", art.content)
    if has_prompt_v and has_schema_v:
        return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt="LLM call site missing prompt_version/schema_version",
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_typescript_any(art: Artifact, rule: dict) -> list[Violation]:
    """MIN-001: any-typing in TS code."""
    if art.metadata.get("ext") not in {".ts", ".tsx"}:
        return []
    out: list[Violation] = []
    for m in re.finditer(r"(?<!\w)(:\s*any\b|<any>|\bas\s+any\b)", art.content):
        line_no = art.content[: m.start()].count("\n") + 1
        out.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=m.group(0),
            suggested_fix=rule.get("remediation", ""),
        ))
    return out


def _check_ownership_field(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-004: explicit decision records missing owner field.

    Tightened 2026-05-06 to require explicit decision-record markers,
    not casual mentions of "decision" in body text. Prior heuristic
    produced false positives on README.md / CLAUDE.md.
    """
    if art.artifact_type not in {"markdown", "task"}:
        return []
    # Filename markers
    name_lower = art.identifier.lower()
    is_decision_filename = bool(re.search(
        r"(?:^|/)(decision_[\w-]+|dr-\d|rfc-\d|adr-\d)[\w.-]*\.md\b",
        name_lower,
    ))
    # Frontmatter markers
    fm_match = re.match(
        r"\A\s*---\s*\n(.*?)\n---\s*\n", art.content, re.DOTALL)
    fm_block = fm_match.group(1) if fm_match else ""
    is_decision_frontmatter = bool(
        re.search(r"^\s*type\s*:\s*decision_record\b", fm_block,
                  re.MULTILINE | re.IGNORECASE)
        or re.search(r"^\s*(decision_id|dr_id)\s*:\s*\S+", fm_block,
                     re.MULTILINE | re.IGNORECASE)
    )
    # H1 markers
    h1_match = re.search(r"^#\s+(.+)$", art.content, re.MULTILINE)
    h1_text = h1_match.group(1).lower() if h1_match else ""
    is_decision_h1 = (
        "decision record" in h1_text
        or "decision:" in h1_text
        or h1_text.startswith("rfc")
        or h1_text.startswith("adr")
    )
    if not (is_decision_filename or is_decision_frontmatter or is_decision_h1):
        return []
    has_owner = bool(re.search(
        r"^\s*owner\s*:\s*\S+", art.content,
        re.MULTILINE | re.IGNORECASE,
    ))
    if has_owner:
        return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt="Decision record missing `owner:` field",
        suggested_fix=rule.get("remediation", ""),
    )]


# Map rule.detection.type → handler function
DETECTION_HANDLERS: dict[str, CheckFn] = {
    "regex": _check_regex,
}

def _is_decision_record(art: Artifact) -> bool:
    """Shared classifier for CRIT-004, CRIT-005, CRIT-006."""
    if art.artifact_type not in {"markdown", "task"}:
        return False
    name_lower = art.identifier.lower()
    if re.search(
            r"(?:^|/)(decision_[\w-]+|dr-\d|rfc-\d|adr-\d)[\w.-]*\.md\b",
            name_lower):
        return True
    fm_match = re.match(
        r"\A\s*---\s*\n(.*?)\n---\s*\n", art.content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        if re.search(r"^\s*type\s*:\s*decision_record\b",
                     fm, re.MULTILINE | re.IGNORECASE):
            return True
        if re.search(r"^\s*(decision_id|dr_id)\s*:\s*\S+",
                     fm, re.MULTILINE | re.IGNORECASE):
            return True
    h1_match = re.search(r"^#\s+(.+)$", art.content, re.MULTILINE)
    if h1_match:
        h1 = h1_match.group(1).lower()
        if "decision record" in h1 or "decision:" in h1 \
                or h1.startswith("rfc") or h1.startswith("adr"):
            return True
    return False


def _check_decision_auditability(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-005: explicit decision records missing evidence_refs."""
    if not _is_decision_record(art):
        return []
    has_evidence = bool(re.search(
        r"^\s*evidence_refs\s*:\s*[\S\[]",
        art.content, re.MULTILINE | re.IGNORECASE))
    if has_evidence:
        # Quick check: not empty list
        if re.search(r"^\s*evidence_refs\s*:\s*\[\s*\]",
                     art.content, re.MULTILINE | re.IGNORECASE):
            pass  # falls through to violation
        else:
            return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt="Decision record has no `evidence_refs:` (or empty array)",
        suggested_fix=rule.get("remediation",
                               "Cite evidence sources before promotion"),
    )]


def _check_automation_without_override(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-001: autonomous agent loops without rollback / override hooks.

    Tightened to fire only on AGENTIC auto-execution (not regular FastAPI
    lifecycle hooks or generic state-machine while-loops). The canonical
    concern is LLM agent loops without an off-switch.
    """
    if art.artifact_type not in {"code"}:
        return []
    if art.metadata.get("ext") not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return []
    # Agentic signals — narrowed to actual auto-execution behaviors
    agentic_signals = [
        r"\bauto_execute\s*\(",                # auto_execute() function call
        r"\bauto_run\s*\(",
        r"\bclaude_agent_options\b",
        r"\bSTART_AUTONOMOUS\b",
        r"\bsupervisor\.run_all\(",
        r"\bsupervisor\.create_run\(",
        # Agentic Python SDK patterns
        r"\bagent\.run\([^)]*\)",
        r"\bClaudeAgent\(",
    ]
    auto_match = None
    for pat in agentic_signals:
        m = re.search(pat, art.content)
        if m:
            auto_match = m
            break
    if not auto_match:
        return []
    safety_signals = [
        r"\brollback\b",
        r"\bhuman[_ ]?override\b",
        r"\bmanual_approval\b",
        r"\bdead_letter\b",
        r"\bmax_attempts\b",
        r"\bmax_iterations\b",
        r"\brequires_approval\b",
        r"\bawaiting_approval\b",
        r"\bcancel_run\b",
        r"\brevert\(",
    ]
    has_safety = any(re.search(pat, art.content, re.IGNORECASE)
                     for pat in safety_signals)
    if has_safety:
        return []
    line_no = art.content[: auto_match.start()].count("\n") + 1
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=f"{art.identifier}:{line_no}",
        excerpt=f"Agentic auto-execution detected without "
                f"rollback/override (matched: {auto_match.group(0)[:60]})",
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_action_without_qualification(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-006: D3-D6 decision records without required_approvals."""
    if not _is_decision_record(art):
        return []
    klass_match = re.search(
        r"^\s*decision_class\s*:\s*([D]\d)",
        art.content, re.MULTILINE | re.IGNORECASE,
    )
    if not klass_match:
        return []
    klass = klass_match.group(1).upper()
    if klass not in {"D3", "D4", "D5", "D6"}:
        return []
    has_approvals = bool(re.search(
        r"^\s*required_approvals\s*:\s*\[?\s*\S",
        art.content, re.MULTILINE | re.IGNORECASE,
    ))
    if has_approvals:
        # Check it's not an empty list
        if re.search(r"^\s*required_approvals\s*:\s*\[\s*\]",
                     art.content, re.MULTILINE | re.IGNORECASE):
            pass
        else:
            return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt=f"{klass} decision without required_approvals "
                f"(authority matrix violation)",
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_fake_market_data(art: Artifact, rule: dict) -> list[Violation]:
    """CRIT-008: pricing/scoring code lacking explicit assumptions[] surface.

    Heuristic: file references pricing recommendations or score outputs but
    never mentions `assumptions` (the explicit synthetic-data label).
    Test fixtures are excluded — synthetic test data is allowed.
    """
    if art.artifact_type not in {"code"}:
        return []
    if art.metadata.get("ext") not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return []
    name_lower = art.identifier.lower()
    if (name_lower.startswith("test_") or "tests/" in name_lower
            or "/tests/" in name_lower or "__tests__" in name_lower
            or name_lower.endswith(".test.ts")
            or name_lower.endswith(".test.tsx")
            or name_lower.endswith(".spec.ts")
            or "test_" in name_lower.split("/")[-1]):
        return []
    # Tightened — match only OUTPUT-schema definitions, not module imports
    # or unrelated identifiers like `next_recommended_agent`.
    pricing_signals = [
        r"\brecommended_(base|peak|weekend|nightly)_rate\b",
        r"\boccupancy_target_(low|base|high)\b",
        r"class\s+\w*Pricing(?:Recommendation|Profile|Output)\b",
        r"class\s+PricingRecommendation\b",
        # Schema/dict literal where recommended_price is a key being SET
        r"['\"]recommended_(price|rate)['\"]\s*:",
        r"\brecommended_price\s*=\s*\w",
    ]
    has_pricing = any(re.search(pat, art.content)
                      for pat in pricing_signals)
    if not has_pricing:
        return []
    # Check for the explicit assumptions label
    has_assumptions = bool(re.search(
        r"\bassumptions\b", art.content, re.IGNORECASE))
    if has_assumptions:
        return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt="Pricing/score output references found without explicit "
                "`assumptions[]` surface",
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_unaudited_state_change(art: Artifact, rule: dict) -> list[Violation]:
    """MAJ-004: DB writes in retryable / job-like contexts that lack idempotency.

    Tightened to fire only when the file is BOTH (a) doing DB writes and
    (b) operating in a retryable/scheduled/ingestion context. Plain CRUD
    routes that don't retry are out of scope.
    """
    if art.artifact_type not in {"code"}:
        return []
    if art.metadata.get("ext") not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return []
    # First — does this file have a state-changing write?
    write_patterns = [
        (r"prisma\.[a-zA-Z_][\w]*\.(update|delete|create|upsert)\(",
         "prisma write"),
        (r"cursor\.execute\(\s*['\"](?:UPDATE|DELETE|INSERT)\b",
         "raw SQL write"),
    ]
    write_match = None
    write_kind = None
    for pat, kind in write_patterns:
        m = re.search(pat, art.content)
        if m:
            write_match = m
            write_kind = kind
            break
    if not write_match:
        return []
    # Second — is this a retryable / job-like context where idempotency matters?
    name_lower = art.identifier.lower()
    retryable_path = bool(re.search(
        r"(jobs?|sync|ingest|pipeline|worker|scheduled|cron|automation|"
        r"backfill|consumer|handler)",
        name_lower,
    ))
    retryable_content = bool(re.search(
        r"\b(retry|retries|attempts|backoff|max_retries|run_after|"
        r"requeue|@scheduled|cron|@every|setInterval)\b",
        art.content, re.IGNORECASE,
    ))
    if not (retryable_path or retryable_content):
        return []
    # Third — does this module have the audit envelope?
    has_envelope = bool(re.search(
        r"\b(Job|WorkflowEvent|workflow_event|idempotency_key|audit_log)\b",
        art.content,
    ))
    if has_envelope:
        return []
    line_no = art.content[: write_match.start()].count("\n") + 1
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=f"{art.identifier}:{line_no}",
        excerpt=f"{write_kind} in retryable context without "
                "idempotency_key / Job / WorkflowEvent envelope",
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_in_memory_state_without_db_writethrough(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-012: module-level dict/list cache mirroring a DB table, where
    at least one mutation site has no nearby INSERT to that table.

    This is the SIE chat-queue bug class (#198, 2026-05-12). The canonical
    enqueue path is DB-first, but a parallel chat handler appended only
    in memory — items vanished on Cloud Run scale-out + revision roll.

    Heuristic: find every module-level `_<name>: dict[str, dict] = {}`
    (or `list[dict] = []`). If the same file contains `INSERT INTO
    <basename>`, scan every mutation site for that var. Fire on any
    mutation site whose enclosing function body has no `INSERT INTO
    <basename>` and is not inside a `_db_available` fallback branch.
    Comments are stripped before matching so prose describing missing
    SQL doesn't accidentally mask the violation.
    """
    if art.artifact_type != "code":
        return []
    if art.metadata.get("ext") != ".py":
        return []

    decl_pattern = re.compile(
        r"^(?P<var>_[a-z][\w]*)\s*:\s*"
        r"(?:dict\[str,\s*dict\]\s*=\s*\{\}|list\[dict\]\s*=\s*\[\])",
        re.MULTILINE,
    )
    declarations = list(decl_pattern.finditer(art.content))
    if not declarations:
        return []

    # Strip Python line comments before pattern matching — comments
    # mentioning "INSERT INTO <table>" or "_db_available" must not
    # trick the heuristic into thinking the code does what its comment
    # talks about. String-literal SQL still survives this scrub.
    scrubbed_lines: list[str] = []
    for raw in art.content.split("\n"):
        idx = raw.find("#")
        scrubbed_lines.append(raw if idx == -1 else raw[:idx])
    scrubbed_content = "\n".join(scrubbed_lines)
    file_lines = scrubbed_lines
    violations: list[Violation] = []

    for decl in declarations:
        var = decl.group("var")
        basename = var.lstrip("_")

        insert_pattern = re.compile(
            rf"\bINSERT\s+INTO\s+{re.escape(basename)}\b",
            re.IGNORECASE,
        )
        if not insert_pattern.search(scrubbed_content):
            continue

        mutation_pattern = re.compile(
            rf"{re.escape(var)}\[\s*[^\]]+\s*\]\s*=",
        )
        def_pattern = re.compile(r"^\s*(?:async\s+)?def\s+")
        for mut in mutation_pattern.finditer(scrubbed_content):
            mut_line = scrubbed_content[: mut.start()].count("\n") + 1

            # Find the enclosing function bounds: from the most recent
            # `def` above (any indentation) to the next `def` below.
            func_start = 0
            for back_idx in range(mut_line - 2, -1, -1):
                if def_pattern.match(file_lines[back_idx]):
                    func_start = back_idx
                    break
            func_end = len(file_lines)
            for fwd_idx in range(mut_line, len(file_lines)):
                if def_pattern.match(file_lines[fwd_idx]):
                    func_end = fwd_idx
                    break

            func_body = "\n".join(file_lines[func_start:func_end])
            if insert_pattern.search(func_body):
                continue

            # Skip mutations inside a DB-fallback branch. If the enclosing
            # function body checks `_db_available`, the in-memory write is
            # the intentional degraded path.
            if "_db_available" in func_body:
                continue

            violations.append(Violation(
                rule_id=rule["id"],
                severity=rule["severity"],
                artifact=art.identifier,
                location=f"{art.identifier}:{mut_line}",
                excerpt=(
                    f"{var} mutated without INSERT INTO {basename} "
                    f"in the same function body; matching DB table is "
                    f"written elsewhere in this file"
                ),
                suggested_fix=rule.get("remediation", ""),
            ))

    return violations


def _check_monorepo_circular_dep(art: Artifact, rule: dict) -> list[Violation]:
    """MAJ-005: package importing from app, or app importing from sibling app."""
    if art.metadata.get("ext") not in {".ts", ".tsx", ".js", ".jsx"}:
        return []
    path = art.identifier
    # Detect if file lives in /packages/<X>/
    pkg_match = re.search(r"(?:^|/)packages/([\w-]+)/", path)
    app_match = re.search(r"(?:^|/)apps/([\w-]+)/", path)

    if pkg_match:
        # Packages must NOT import from apps/
        bad = re.search(
            r"from\s+['\"](?:[^'\"]*?/)?apps/[\w-]+",
            art.content,
        )
        if bad:
            line_no = art.content[: bad.start()].count("\n") + 1
            return [Violation(
                rule_id=rule["id"],
                severity=rule["severity"],
                artifact=art.identifier,
                location=f"{art.identifier}:{line_no}",
                excerpt="Package imports from apps/ — circular monorepo dep",
                suggested_fix=rule.get("remediation", ""),
            )]
    if app_match:
        my_app = app_match.group(1)
        # Apps must NOT import from sibling apps/<other>/
        for m in re.finditer(
            r"from\s+['\"](?:[^'\"]*?/)?apps/([\w-]+)",
            art.content,
        ):
            other_app = m.group(1)
            if other_app != my_app:
                line_no = art.content[: m.start()].count("\n") + 1
                return [Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=f"{art.identifier}:{line_no}",
                    excerpt=f"App {my_app} imports from sibling app "
                            f"{other_app}",
                    suggested_fix=rule.get("remediation", ""),
                )]
    return []


def _check_capability_without_telemetry(art: Artifact, rule: dict) -> list[Violation]:
    """MAJ-001: new route/endpoint added to production code without any
    observability call (logger, metrics, audit, etc.) in its function body.

    Fires when a Python function decorated with a route decorator exceeds
    10 lines and contains no call to any recognised observability symbol.
    """
    if art.artifact_type != "code":
        return []
    if art.metadata.get("ext") != ".py":
        return []

    ROUTE_RE = re.compile(
        r"@(?:app|router)\."
        r"(?:route|get|post|put|delete|patch)"
        r"\s*\(",
    )
    TELEMETRY_RE = re.compile(
        r"\b(?:logger|logging|structlog|metrics|audit|telemetry|"
        r"increment|track)\b",
    )

    out: list[Violation] = []
    lines = art.content.splitlines()

    i = 0
    while i < len(lines):
        if ROUTE_RE.search(lines[i]):
            decorator_line = i
            # Find the 'def' line (may be on same or next line after decorator)
            def_line = None
            for j in range(i, min(i + 5, len(lines))):
                if re.match(r"\s*(?:async\s+)?def\s+\w+", lines[j]):
                    def_line = j
                    break
            if def_line is None:
                i += 1
                continue

            # Collect function body: lines after def until next same/outer indent
            def_indent = len(lines[def_line]) - len(lines[def_line].lstrip())
            body_lines: list[str] = []
            k = def_line + 1
            while k < len(lines):
                line = lines[k]
                stripped = line.strip()
                if stripped == "":
                    k += 1
                    continue
                indent = len(line) - len(line.lstrip())
                if indent <= def_indent and stripped:
                    break
                body_lines.append(line)
                k += 1

            if len(body_lines) > 10:
                body_text = "\n".join(body_lines)
                if not TELEMETRY_RE.search(body_text):
                    # Extract function name for the excerpt
                    fn_match = re.match(
                        r"\s*(?:async\s+)?def\s+(\w+)", lines[def_line])
                    fn_name = fn_match.group(1) if fn_match else "unknown"
                    out.append(Violation(
                        rule_id=rule["id"],
                        severity=rule["severity"],
                        artifact=art.identifier,
                        location=f"{art.identifier}:{def_line + 1}",
                        excerpt=f"Route handler `{fn_name}` ({len(body_lines)} lines) "
                                "has no observability call (logger/metrics/audit/telemetry)",
                        suggested_fix=rule.get(
                            "remediation",
                            "Add at least one logger.info/metrics.increment/audit call "
                            "inside the route handler body",
                        ),
                    ))
            i = def_line + 1
        else:
            i += 1
    return out


def _check_schema_without_migration(art: Artifact, rule: dict) -> list[Violation]:
    """MAJ-006: schema-change SQL in non-migration Python files, or SQLAlchemy
    model files modified more recently than the latest alembic versions/ file.

    Two detection modes:
    (a) Raw DDL strings (CREATE TABLE / ALTER TABLE / ADD COLUMN / DROP COLUMN)
        in any .py file that is NOT inside an alembic/versions/ directory.
    (b) SQLAlchemy/SQLModel/Tortoise model files whose mtime is newer than the
        most recent alembic versions/ file mtime (git-diff heuristic).
    """
    if art.artifact_type != "code":
        return []
    if art.metadata.get("ext") != ".py":
        return []

    identifier = art.identifier  # relative path string

    # ── mode (a): raw DDL outside migrations ─────────────────────────────────
    is_migration = bool(re.search(
        r"(?:^|[/\\])(?:alembic|migrations)[/\\](?:versions?[/\\])?",
        identifier,
    ))
    if not is_migration:
        DDL_RE = re.compile(
            r"(?:CREATE\s+TABLE|ALTER\s+TABLE|ADD\s+COLUMN|DROP\s+COLUMN)",
            re.IGNORECASE,
        )
        for m in DDL_RE.finditer(art.content):
            # Confirm it's in a string literal (common heuristic: preceded by
            # a quote or triple-quote somewhere on the same expression line)
            line_start = art.content.rfind("\n", 0, m.start()) + 1
            line_text = art.content[line_start: art.content.find("\n", m.start())]
            if re.search(r"""['"]{1,3}""", line_text):
                line_no = art.content[: m.start()].count("\n") + 1
                return [Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=f"{art.identifier}:{line_no}",
                    excerpt=f"Raw DDL `{m.group(0)}` in non-migration file",
                    suggested_fix=rule.get(
                        "remediation",
                        "Move DDL into an alembic migration under alembic/versions/",
                    ),
                )]

    # ── mode (b): ORM model file newer than latest alembic versions/ file ────
    ORM_MODEL_RE = re.compile(
        r"\b(?:declarative_base|DeclarativeBase|SQLModel|"
        r"Model\s*=\s*declarative_base|tortoise\.Model)\b"
    )
    if not ORM_MODEL_RE.search(art.content):
        return []

    # Try to find the alembic versions dir relative to the repo
    # art.identifier is repo-relative; reconstruct absolute path
    github_root = Path("/Users/admin/Documents/GitHub")
    # First segment of identifier is the repo name
    parts = Path(identifier).parts
    if not parts:
        return []
    repo_root = github_root / parts[0]

    versions_dir = repo_root / "alembic" / "versions"
    if not versions_dir.exists():
        return []

    migration_files = list(versions_dir.glob("*.py"))
    if not migration_files:
        # No migrations at all — flag immediately
        return [Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=art.identifier,
            excerpt="ORM model file exists but alembic/versions/ has no migration files",
            suggested_fix=rule.get(
                "remediation",
                "Generate an alembic migration: `alembic revision --autogenerate`",
            ),
        )]

    latest_migration_mtime = max(f.stat().st_mtime for f in migration_files)

    # Reconstruct absolute path of the artifact
    abs_path = github_root / identifier
    try:
        model_mtime = abs_path.stat().st_mtime
    except OSError:
        return []

    if model_mtime > latest_migration_mtime:
        return [Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=art.identifier,
            excerpt=(
                "ORM model file is newer than the most recent alembic migration "
                f"— possible un-migrated schema change"
            ),
            suggested_fix=rule.get(
                "remediation",
                "Run `alembic revision --autogenerate` and review the generated diff",
            ),
        )]
    return []


def _check_phase_gate_violation(art: Artifact, rule: dict) -> list[Violation]:
    """MAJ-009: production file modified after a blocking phase gate document.

    A phase gate file is identified by name pattern or by containing a
    '## Phase Gate' / '# Phase Gate' heading. If the gate is NOT complete
    (contains '[ ]', 'status: blocked', or 'status: pending') but a
    production file in the same repo has an mtime newer than the gate
    document, flag it.

    Note: this handler fires when evaluating the gate document itself —
    it then scans sibling production files to find violations.
    """
    if art.artifact_type != "markdown":
        return []

    identifier = art.identifier
    name_lower = Path(identifier).name.lower()

    # Determine if this is a phase gate document
    is_gate_by_name = bool(re.match(
        r"(?:phase_[\w-]+|phase_gate_[\w-]+|[\w-]+_gate_[\w-]+)\.md$",
        name_lower,
    ))
    is_gate_by_content = bool(re.search(
        r"^#{1,2}\s+Phase\s+Gate\b", art.content, re.MULTILINE | re.IGNORECASE,
    ))
    if not is_gate_by_name and not is_gate_by_content:
        return []

    # Check if gate is blocking
    blocking = bool(re.search(
        r"(?:\[ \]|status\s*:\s*(?:blocked|pending))",
        art.content, re.IGNORECASE,
    ))
    if not blocking:
        return []

    # Find the gate file's mtime
    github_root = Path("/Users/admin/Documents/GitHub")
    abs_gate = github_root / identifier
    try:
        gate_mtime = abs_gate.stat().st_mtime
    except OSError:
        return []

    # Repo root = first segment of identifier
    parts = Path(identifier).parts
    if not parts:
        return []
    repo_root = github_root / parts[0]

    SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".next", "dist",
                 "build", ".turbo", ".venv", "venv"}
    PROD_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}

    violations: list[Violation] = []
    for path in repo_root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in PROD_EXTS:
            continue
        try:
            if path.stat().st_mtime > gate_mtime:
                rel = str(path.relative_to(github_root))
                violations.append(Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=rel,
                    excerpt=(
                        f"Production file `{rel}` modified after blocking "
                        f"phase gate `{identifier}`"
                    ),
                    suggested_fix=rule.get(
                        "remediation",
                        "Complete or unblock the phase gate before shipping "
                        "production code changes",
                    ),
                ))
        except OSError:
            continue
        if len(violations) >= 10:
            break  # cap at 10 per gate doc to avoid noise storms

    return violations


def _check_value_chain_break(art: Artifact, rule: dict) -> list[Violation]:
    """MAJ-010: Gigaton value chain integrity check.

    Fires on three conditions evaluated per-artifact:
    (a) pricing_engine/api.py or margin_optimization/api.py exists but has
        no /health endpoint defined.
    (b) gigaton_client.py is absent from the decision-engine repo.
    (c) Any file imports from pricing_engine or margin_optimization but
        those directories don't exist in the scanned repo.
    """
    if art.artifact_type not in {"code"}:
        return []

    github_root = Path("/Users/admin/Documents/GitHub")
    identifier = art.identifier
    parts = Path(identifier).parts
    if not parts:
        return []
    repo_name = parts[0]
    repo_root = github_root / repo_name

    out: list[Violation] = []

    # ── (a) API files without /health endpoint ────────────────────────────────
    chain_api_files = [
        "pricing_engine/api.py",
        "margin_optimization/api.py",
    ]
    for rel_api in chain_api_files:
        # Only evaluate when we ARE scanning that specific file
        if not identifier.endswith(rel_api.replace("/", os.sep)) and \
                not identifier.endswith(rel_api):
            continue
        has_health = bool(re.search(
            r"""['"]/health['"]""", art.content,
        ))
        if not has_health:
            out.append(Violation(
                rule_id=rule["id"],
                severity=rule["severity"],
                artifact=art.identifier,
                location=art.identifier,
                excerpt=(
                    f"`{rel_api}` exists but defines no `/health` endpoint — "
                    "value chain liveness check will fail"
                ),
                suggested_fix=rule.get(
                    "remediation",
                    "Add a GET /health endpoint returning {status: ok}",
                ),
            ))

    # ── (b) gigaton_client.py absent from decision-engine ─────────────────────
    if repo_name == "decision-engine":
        client_path = repo_root / "gigaton_client.py"
        # Only flag once — when evaluating the repo's main entry point or any
        # file in the engine/ directory to avoid duplicate noise
        if re.search(r"(?:^|[/\\])(?:engine|api)[/\\]", identifier) or \
                identifier == f"{repo_name}/api/main.py":
            if not client_path.exists():
                out.append(Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=str(client_path.relative_to(github_root)),
                    excerpt=(
                        "`decision-engine/gigaton_client.py` is absent — "
                        "B-05 value chain bridge not yet wired"
                    ),
                    suggested_fix=rule.get(
                        "remediation",
                        "Create gigaton_client.py implementing the "
                        "decision-engine → gigaton-engine bridge (B-05)",
                    ),
                ))

    # ── (c) import from missing chain directory ────────────────────────────────
    if art.metadata.get("ext") == ".py":
        CHAIN_IMPORT_RE = re.compile(
            r"(?:^|\n)\s*(?:from|import)\s+(pricing_engine|margin_optimization)\b",
        )
        for m in CHAIN_IMPORT_RE.finditer(art.content):
            pkg = m.group(1)
            pkg_dir = repo_root / pkg
            if not pkg_dir.exists():
                line_no = art.content[: m.start()].count("\n") + 1
                out.append(Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=f"{art.identifier}:{line_no}",
                    excerpt=(
                        f"Import from `{pkg}` but `{repo_name}/{pkg}/` "
                        "does not exist — value chain directory missing"
                    ),
                    suggested_fix=rule.get(
                        "remediation",
                        f"Create the `{pkg}/` package or remove the import",
                    ),
                ))
    return out


def _check_env_mutation_in_request_handler(
    art: Artifact, rule: dict
) -> list[Violation]:
    """CRIT-011: `os.environ[...] = ...` (or .update/.__setitem__) inside a
    function whose decorators register it as a FastAPI route handler.

    Documented bug class: SIE PR `fix/llm-secret-ref-param` (2026-05-14)
    removed `os.environ[KEY] = secret_ref` from `_intel_call_one_provider`
    after cross-user credential contamination was discovered under
    concurrent request load. `os.environ` is process-global; concurrent
    FastAPI handlers writing to it can swap one user's credential
    reference into a second user's call before the second handler reads
    it.

    Heuristic (v0 — direct-decorator only):
      1. Find each os.environ mutation site (assignment, .update, or
         .__setitem__ — NOT .get / .pop / `in os.environ`).
      2. Walk backward to the enclosing `def`/`async def`.
      3. Inspect decorators on the def line and the ±10 lines above.
      4. Fire if any decorator matches FastAPI route patterns:
         @app.<verb>, @router.<verb>, @<name>.<verb> where verb is
         one of get/post/put/patch/delete/options/head.
      5. Skip when the mutation is INSIDE a `# noqa: CRIT-011` line
         (explicit override).

    Transitive callers (handler → helper → env-mutation) are out of v0
    scope; if the rule misses a future variant, that case will be added.
    """
    if art.artifact_type != "code":
        return []
    if art.metadata.get("ext") != ".py":
        return []

    # 1. Find all mutation sites.
    mutation_pattern = re.compile(
        r"os\.environ\s*(?:\[\s*[^\]]+\s*\]\s*=(?!=)"
        r"|\.update\s*\("
        r"|\.__setitem__\s*\()"
    )
    matches = list(mutation_pattern.finditer(art.content))
    if not matches:
        return []

    # 2. Index lines for backward def-scan + decorator inspection.
    lines = art.content.split("\n")
    def_pattern = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+")
    route_decorator_pattern = re.compile(
        r"^\s*@[\w\.]+\.(?:get|post|put|patch|delete|options|head)\s*\(",
    )
    # Also support `@<verb>(` shape (rare, but used in some frameworks).
    bare_route_pattern = re.compile(
        r"^\s*@(?:get|post|put|patch|delete|options|head)\s*\(",
    )

    violations: list[Violation] = []
    for mut in matches:
        mut_line_no = art.content[: mut.start()].count("\n") + 1
        # Allow explicit override on the same line.
        if "noqa: CRIT-011" in lines[mut_line_no - 1]:
            continue

        # Walk back to the enclosing def. Skip nested defs by tracking
        # indentation — but for v0 we accept the most-recent def above
        # the mutation regardless of indent (handlers are top-level).
        enclosing_def_idx: int | None = None
        for back_idx in range(mut_line_no - 2, -1, -1):
            if def_pattern.match(lines[back_idx]):
                enclosing_def_idx = back_idx
                break
        if enclosing_def_idx is None:
            # Mutation at module scope (e.g. test setup) — out of scope.
            continue

        # Inspect the 10 lines above the def for a routing decorator.
        decorator_window_start = max(0, enclosing_def_idx - 10)
        decorator_block = lines[decorator_window_start:enclosing_def_idx]
        has_route_decorator = any(
            route_decorator_pattern.match(line)
            or bare_route_pattern.match(line)
            for line in decorator_block
        )
        if not has_route_decorator:
            continue

        excerpt = lines[mut_line_no - 1].strip()[:120]
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{mut_line_no}",
            excerpt=(
                f"os.environ mutation inside FastAPI route handler: "
                f"{excerpt}"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


def _check_cloud_run_max_instances_above_one(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MIN-009: Cloud Run service config with --max-instances > 1.

    Several v0 designs assume single-instance correctness: SecretStore
    cache (PR #208, process-local), in-memory rate-limiter state,
    scheduler leader-election. Lifting --max-instances above 1 before
    v1 cross-instance work ships introduces silent correctness bugs.

    Detects:
      - `--max-instances=N` or `--max-instances N` (gcloud CLI) where N>1
      - `maxScale: "N"` annotation (Knative service) where N>1
      - `max_instances: N` / `maxScale: N` config fields where N>1

    Skips:
      - N <= 1
      - Absence of the flag (Cloud Run default is irrelevant — this rule
        only fires when an operator EXPLICITLY raises the cap).
      - Lines with `# noqa: MIN-009` override.
    """
    ext = art.metadata.get("ext")
    if ext not in {".yaml", ".yml", ".sh", ".md", ".py"}:
        return []

    patterns = [
        # gcloud CLI flag — covers `--max-instances=5` and `--max-instances 5`
        re.compile(r"--max-instances[=\s]+(\d+)"),
        # Knative-style maxScale annotation: `maxScale: "5"` or `maxScale: '5'`
        re.compile(r"maxScale\s*:\s*['\"]?(\d+)['\"]?"),
        # Config field: `max_instances: 5` / `max_instances=5`
        re.compile(r"\bmax_instances\s*[:=]\s*(\d+)"),
    ]

    lines = art.content.split("\n")
    violations: list[Violation] = []
    seen_lines: set[int] = set()

    for pat in patterns:
        for m in pat.finditer(art.content):
            try:
                n = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if n <= 1:
                continue
            line_no = art.content[: m.start()].count("\n") + 1
            if line_no in seen_lines:
                continue
            if "noqa: MIN-009" in lines[line_no - 1]:
                continue
            seen_lines.add(line_no)
            violations.append(Violation(
                rule_id=rule["id"],
                severity=rule["severity"],
                artifact=art.identifier,
                location=f"{art.identifier}:{line_no}",
                excerpt=(
                    f"Cloud Run scale cap raised to {n} — triggers v1 "
                    f"cross-instance follow-up review"
                ),
                suggested_fix=rule.get("remediation", ""),
            ))

    return violations


# Map rule.id → custom structural handler (for rules that need bespoke logic)
STRUCTURAL_HANDLERS: dict[str, CheckFn] = {
    "CRIT-001": _check_automation_without_override,
    "CRIT-003": _check_prompt_versioning,
    "CRIT-004": _check_ownership_field,
    "CRIT-005": _check_decision_auditability,
    "CRIT-006": _check_action_without_qualification,
    "CRIT-007": _check_provider_lock_in,
    "CRIT-008": _check_fake_market_data,
    "CRIT-011": _check_env_mutation_in_request_handler,
    "MAJ-001": _check_capability_without_telemetry,
    "MAJ-004": _check_unaudited_state_change,
    "MAJ-005": _check_monorepo_circular_dep,
    "MAJ-012": _check_in_memory_state_without_db_writethrough,
    "MAJ-006": _check_schema_without_migration,
    "MAJ-009": _check_phase_gate_violation,
    "MAJ-010": _check_value_chain_break,
    "MIN-001": _check_typescript_any,
    "MIN-009": _check_cloud_run_max_instances_above_one,
}


class RuleEngine:
    def __init__(self, rules_path: Path):
        with rules_path.open() as fh:
            self.spec = yaml.safe_load(fh)
        self.rules: list[dict] = self.spec.get("rules", [])
        self.routing: dict = self.spec.get("source_routing", {})

    def applicable_rules(self, source: str) -> list[dict]:
        rule_ids = set(self.routing.get(source, {}).get("rules_applied", []))
        if not rule_ids:
            return self.rules
        return [r for r in self.rules if r["id"] in rule_ids]

    def evaluate(self, art: Artifact) -> list[Violation]:
        out: list[Violation] = []
        for rule in self.applicable_rules(art.source):
            scope = rule.get("scope", [])
            if scope and art.artifact_type not in self._expand_scope(scope):
                continue
            handler = STRUCTURAL_HANDLERS.get(rule["id"]) or \
                DETECTION_HANDLERS.get(rule.get("detection", {}).get("type"))
            if handler is None:
                continue
            try:
                out.extend(handler(art, rule))
            except (re.error, KeyError, TypeError) as exc:
                # Don't let a malformed rule crash the scan
                out.append(Violation(
                    rule_id=rule["id"],
                    severity="info",
                    artifact=art.identifier,
                    location=None,
                    excerpt=f"Rule handler error: {exc}",
                    suggested_fix="Fix rule definition in DRIFT_RULES.yaml",
                ))
        return out

    @staticmethod
    def _expand_scope(scope: list[str]) -> set[str]:
        """Map rule scope vocab to Artifact.artifact_type values."""
        mapping = {
            "codebase": {"code", "config", "schema"},
            "markdown": {"markdown"},
            "decision": {"markdown"},
            "clickup_task": {"task"},
            "drive_doc": {"doc"},
        }
        out: set[str] = set()
        for s in scope:
            out |= mapping.get(s, {s})
        return out


# ---------------------------------------------------------------------------
# History persistence
# ---------------------------------------------------------------------------

def init_history() -> sqlite3.Connection:
    conn = sqlite3.connect(HISTORY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            scan_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            sources TEXT NOT NULL,
            total_artifacts INTEGER NOT NULL,
            critical INTEGER NOT NULL,
            major INTEGER NOT NULL,
            minor INTEGER NOT NULL,
            info INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            artifact TEXT NOT NULL,
            location TEXT,
            excerpt TEXT,
            FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
        )
    """)
    conn.commit()
    return conn


def persist(conn: sqlite3.Connection, scan_id: str, ts: str,
            sources: list[str], total: int,
            violations: list[Violation]) -> None:
    counts = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    conn.execute(
        "INSERT INTO scans VALUES (?,?,?,?,?,?,?,?)",
        (scan_id, ts, ",".join(sources), total,
         counts["critical"], counts["major"],
         counts["minor"], counts["info"]),
    )
    conn.executemany(
        "INSERT INTO violations(scan_id, rule_id, severity, artifact, "
        "location, excerpt) VALUES (?,?,?,?,?,?)",
        [(scan_id, v.rule_id, v.severity, v.artifact, v.location, v.excerpt)
         for v in violations],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def write_reports(scan_id: str, ts: str, sources: list[str],
                  artifacts_count: int,
                  violations: list[Violation]) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(exist_ok=True)
    counts = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1

    json_path = REPORTS_DIR / f"drift_{ts.replace(':', '-')}.json"
    json_path.write_text(json.dumps({
        "scan_id": scan_id,
        "timestamp": ts,
        "sources": sources,
        "summary": {
            "total_artifacts": artifacts_count,
            "violations": counts,
        },
        "violations": [asdict(v) for v in violations],
    }, indent=2))

    md_path = REPORTS_DIR / f"drift_{ts.replace(':', '-')}.md"
    health = "GREEN" if counts["critical"] == 0 and counts["major"] < 5 \
        else ("YELLOW" if counts["critical"] == 0 else "RED")
    lines = [
        f"# Drift Report — {ts}",
        "",
        f"**Scan:** `{scan_id}`",
        f"**Sources:** {', '.join(sources)}",
        f"**Artifacts scanned:** {artifacts_count}",
        f"**Health:** {health}",
        "",
        "## Summary",
        f"- Critical: {counts['critical']}",
        f"- Major:    {counts['major']}",
        f"- Minor:    {counts['minor']}",
        f"- Info:     {counts['info']}",
        "",
        "## Violations",
    ]
    for severity in ["critical", "major", "minor", "info"]:
        bucket = [v for v in violations if v.severity == severity]
        if not bucket:
            continue
        lines.append(f"\n### {severity.upper()} ({len(bucket)})")
        for v in bucket[:50]:  # cap per-bucket display
            lines.append(
                f"- **{v.rule_id}** — `{v.location or v.artifact}`  \n"
                f"  excerpt: `{(v.excerpt or '')[:80]}`  \n"
                f"  fix: {v.suggested_fix}"
            )
        if len(bucket) > 50:
            lines.append(f"\n_... {len(bucket) - 50} more {severity} "
                         f"violations in JSON report._")
    md_path.write_text("\n".join(lines))
    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _repo_level_checks(engine: RuleEngine, root: Path) -> list[Violation]:
    """Repo-level checks (MIN-002 no_test_suite, etc.) that require
    aggregating across all files in a repo, not per-file evaluation."""
    out: list[Violation] = []
    rules_by_id = {r["id"]: r for r in engine.rules}

    for repo_dir in sorted(root.iterdir()):
        if not repo_dir.is_dir():
            continue
        if repo_dir.name.startswith("."):
            continue

        # Determine if it's a code repo (has package.json or pyproject.toml)
        has_package_json = (repo_dir / "package.json").exists()
        has_pyproject = (repo_dir / "pyproject.toml").exists()
        has_requirements = (repo_dir / "requirements.txt").exists()
        is_code_repo = has_package_json or has_pyproject or has_requirements
        if not is_code_repo:
            continue

        # MIN-002 — no test suite
        rule = rules_by_id.get("MIN-002")
        if rule:
            test_count = _count_tests(repo_dir)
            if test_count == 0:
                out.append(Violation(
                    rule_id="MIN-002",
                    severity=rule["severity"],
                    artifact=f"repo:{repo_dir.name}",
                    location=str(repo_dir),
                    excerpt="No test files found "
                            "(test_*.py, *.test.ts, *.spec.ts, "
                            "tests/, __tests__/)",
                    suggested_fix=rule.get(
                        "remediation",
                        "Add at least smoke tests for the golden path"),
                ))
    return out


def _count_tests(repo: Path) -> int:
    """Count test-suite files in a repo (rough heuristic)."""
    count = 0
    skip = {"node_modules", "__pycache__", ".git", ".next", "dist",
            "build", ".turbo", ".venv", "venv", "generated",
            "__generated__"}
    for path in repo.rglob("*"):
        if any(part in skip for part in path.parts):
            continue
        if not path.is_file():
            continue
        name = path.name.lower()
        if (name.startswith("test_") and name.endswith(".py")
                or name.endswith(".test.ts")
                or name.endswith(".test.tsx")
                or name.endswith(".test.js")
                or name.endswith(".spec.ts")
                or name.endswith(".spec.tsx")
                or name.endswith(".spec.js")):
            count += 1
        elif "tests" in path.parts or "__tests__" in path.parts:
            if path.suffix in {".py", ".ts", ".tsx", ".js"}:
                count += 1
    return count


def run_scan(sources: list[str], engine: RuleEngine) -> tuple[
        int, list[Violation]]:
    artifacts_count = 0
    violations: list[Violation] = []
    for src in sources:
        adapter_cls = ADAPTERS.get(src)
        if adapter_cls is None:
            print(f"  [skip] unknown source: {src}", file=sys.stderr)
            continue
        # Build adapter config from rule routing or sensible defaults
        cfg = engine.routing.get(src, {})
        if src == "local_codebase" and "root" not in cfg:
            cfg = {**cfg, "root": "/Users/admin/Documents/GitHub"}
        if src == "downloads" and "roots" not in cfg:
            cfg = {**cfg, "roots": ["/Users/admin/Downloads"],
                   "include_extensions": [".md", ".txt"]}
        adapter = adapter_cls(cfg)
        for art in adapter.stream():
            artifacts_count += 1
            violations.extend(engine.evaluate(art))

    # Repo-level checks (MIN-002 etc.) — run once at end if local_codebase
    # was scanned
    if "local_codebase" in sources:
        local_cfg = engine.routing.get("local_codebase", {})
        local_root = Path(local_cfg.get("root",
                                        "/Users/admin/Documents/GitHub"))
        if local_root.exists():
            violations.extend(_repo_level_checks(engine, local_root))

    return artifacts_count, violations


def post_to_slack(scan_id: str, ts: str, sources: list[str],
                  artifacts_count: int,
                  violations: list[Violation]) -> bool:
    """POST a digest to a Slack webhook.

    Reads SLACK_WEBHOOK_URL from env. Returns True on success.
    Keeps the body small — links to the JSON report, summarizes counts,
    lists top 5 critical findings.
    """
    import urllib.error
    import urllib.request

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("[slack] SLACK_WEBHOOK_URL not set; skipping",
              file=sys.stderr)
        return False
    counts = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    health = "🟢 GREEN" if counts["critical"] == 0 and counts["major"] < 5 \
        else ("🟡 YELLOW" if counts["critical"] == 0 else "🔴 RED")
    crit_samples = [v for v in violations if v.severity == "critical"][:5]
    crit_block = "\n".join(
        f"• `{v.rule_id}` — {v.artifact}" for v in crit_samples) \
        or "_(none)_"
    payload = {
        "text": (
            f"*Drift Sentinel — {ts}*\n"
            f"Health: {health}  ·  Scan: `{scan_id}`  ·  "
            f"Sources: {', '.join(sources)}  ·  "
            f"Artifacts: {artifacts_count}\n\n"
            f"*Counts*  critical: *{counts['critical']}*  ·  "
            f"major: {counts['major']}  ·  minor: {counts['minor']}  ·  "
            f"info: {counts['info']}\n\n"
            f"*Top critical findings*\n{crit_block}"
        ),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                print(f"[slack] POST returned {resp.status}",
                      file=sys.stderr)
            return ok
    except urllib.error.URLError as exc:
        print(f"[slack] error posting: {exc}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gigaton Drift Sentinel")
    parser.add_argument(
        "--source", default="local_codebase",
        help="Source to scan: local_codebase | downloads | github | "
             "drive | clickup | all (comma-separated)")
    parser.add_argument(
        "--fail-on", default="never",
        choices=["never", "critical", "major", "minor"],
        help="Exit non-zero if violations of this severity found")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing to drift_history.db")
    parser.add_argument(
        "--post-to-slack", action="store_true",
        help="POST a digest to SLACK_WEBHOOK_URL (env var)")
    args = parser.parse_args(argv)

    if args.source == "all":
        sources = list(ADAPTERS.keys())
    else:
        sources = [s.strip() for s in args.source.split(",") if s.strip()]

    engine = RuleEngine(RULES_FILE)
    scan_id = uuid.uuid4().hex[:12]
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"[drift_sentinel] scan {scan_id} @ {ts}")
    print(f"[drift_sentinel] sources: {sources}")
    artifacts_count, violations = run_scan(sources, engine)

    if not args.no_persist:
        conn = init_history()
        persist(conn, scan_id, ts, sources, artifacts_count, violations)
        conn.close()

    json_path, md_path = write_reports(
        scan_id, ts, sources, artifacts_count, violations)
    print(f"[drift_sentinel] reports → {json_path}")
    print(f"[drift_sentinel] reports → {md_path}")

    if args.post_to_slack:
        if post_to_slack(scan_id, ts, sources, artifacts_count, violations):
            print("[drift_sentinel] slack digest posted")

    severity_order = ["info", "minor", "major", "critical"]
    if args.fail_on != "never":
        threshold = severity_order.index(args.fail_on)
        for v in violations:
            if severity_order.index(v.severity) >= threshold:
                print(f"[drift_sentinel] FAIL: {v.severity} drift detected "
                      f"(--fail-on={args.fail_on})", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
