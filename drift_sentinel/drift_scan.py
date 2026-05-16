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
import fnmatch
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
    # Multi-segment path prefixes to exclude. Used for transient or
    # mirror trees that single-segment matching would miss (e.g.
    # `.claude/worktrees/agent-*` — Claude Code agent worktrees that
    # duplicate real repo code and produce phantom drift hits).
    # Matched as ordered consecutive parts anywhere in the relative path.
    # WHY: 8/29 CRIT-011 hits on the 2026-05-14 scan came from agent
    # worktree mirrors of `tests/test_drift_preventive_rules.py`.
    SKIP_PATH_PREFIXES = (
        (".claude", "worktrees"),
    )
    INCLUDE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".md", ".yaml",
                   ".yml", ".json", ".prisma", ".sql", ".sh"}
    # Files with no extension that we still want to scan (Dockerfile, etc).
    # Required for MAJ-020 (Dockerfile alembic discipline) and MAJ-013/14/15
    # (cloudbuild + bootstrap script patterns).
    INCLUDE_NAMES = {"Dockerfile"}

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

    @classmethod
    def _path_excluded(cls, path: Path) -> bool:
        """True if path is inside a skipped directory or skipped prefix."""
        parts = path.parts
        if any(part in cls.SKIP_DIRS for part in parts):
            return True
        for prefix in cls.SKIP_PATH_PREFIXES:
            # Match the prefix as consecutive segments anywhere in parts.
            n = len(prefix)
            for i in range(len(parts) - n + 1):
                if tuple(parts[i:i + n]) == prefix:
                    return True
        return False

    def _walk_repo(self, repo: Path) -> Iterator[Artifact]:
        files: list[Path] = []
        for path in repo.rglob("*"):
            if self._path_excluded(path):
                continue
            if not path.is_file():
                continue
            if path.suffix in self.INCLUDE_EXT or path.name in self.INCLUDE_NAMES:
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
        # Dockerfile + shell scripts are deploy-adjacent code artifacts
        # the MAJ-013/14/15/20 handlers need to inspect. Classify them
        # as "config" so they fit existing `scope: [codebase]` rules
        # (codebase scope expands to {code, config, schema}).
        if path.name == "Dockerfile" or path.suffix == ".sh":
            return "config"
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


def _check_cloudbuild_secret_env_in_non_bash_step(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-013: cloudbuild.yaml step uses `secretEnv:` but the step does
    NOT run a shell (no `entrypoint: bash` and not a known bash-image).

    WHY: Cloud Build substitutes `$$SECRET_NAME` only inside steps that
    run a shell. Non-shell steps (exec-wrapper, raw gcloud, docker) get
    the literal string `$SECRET_NAME` as the env value, silently breaking
    auth. This is HME bug #5 from the 2026-05-13 cascade — the migrate
    step using exec-wrapper passed `DB_PASSWORD` as an empty string,
    triggering psycopg2 fallback to default unix socket.

    Heuristic:
      - Scan only YAML/YML files whose basename starts with `cloudbuild`
        OR whose path matches `**/cloudbuild*.yaml`.
      - For each YAML step (item under `steps:`), if a `secretEnv:` block
        is present, the step must either:
          (a) have `entrypoint: bash`, OR
          (b) reference a documented bash-shell image (`alpine`, `bash`,
              `busybox`, or `cloud-builders/docker` with explicit
              `entrypoint: bash`), OR
          (c) declare a `# noqa: MAJ-013` override on the line.
      - Otherwise, fire.
      - Step-level parsing is heuristic-driven (regex on indent blocks);
        full YAML AST would be cleaner but pyyaml is already an import
        and this rule is line-precision-tolerant.
    """
    if art.metadata.get("ext") not in {".yaml", ".yml"}:
        return []
    name_lower = Path(art.identifier).name.lower()
    if not name_lower.startswith("cloudbuild"):
        return []

    lines = art.content.split("\n")
    violations: list[Violation] = []
    # Walk steps: find lines that begin a step (indent 2 + `- id:` or
    # `- name:`). For each step, collect its block until next step start
    # at the same indent level.
    step_starts: list[int] = []
    for i, line in enumerate(lines):
        if re.match(r"^\s\s-\s+(id|name|entrypoint)\s*:", line):
            step_starts.append(i)
    if not step_starts:
        return []
    step_starts.append(len(lines))

    for idx in range(len(step_starts) - 1):
        start = step_starts[idx]
        end = step_starts[idx + 1]
        block = "\n".join(lines[start:end])
        if not re.search(r"^\s+secretEnv\s*:", block, re.MULTILINE):
            continue
        # Is the step bash-shelled?
        has_bash_entrypoint = bool(re.search(
            r"^\s+entrypoint\s*:\s*['\"]?bash['\"]?",
            block, re.MULTILINE,
        ))
        # Some configs use `args: -c` with implicit bash; accept that too.
        # Skip if there's a noqa override anywhere in the step.
        if "noqa: MAJ-013" in block:
            continue
        if has_bash_entrypoint:
            continue
        # Find the secretEnv line for accurate location reporting
        m = re.search(r"^\s+secretEnv\s*:", block, re.MULTILINE)
        offset = m.start() if m else 0
        rel_line = block[:offset].count("\n")
        line_no = start + rel_line + 1
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                "cloudbuild step uses secretEnv: but has no "
                "`entrypoint: bash` — secrets pass as literal '$VAR' "
                "to non-shell steps (HME bug #5, 2026-05-13)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))
    return violations


def _check_cloudsql_password_drift_between_instance_and_secret(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-014: Cloud SQL instance password and Secret Manager secret
    value generated by SEPARATE `openssl rand` invocations.

    WHY: PPEME bug from 2026-05-14 — two distinct `openssl rand -base64`
    calls produced different passwords for the instance vs the secret,
    causing FATAL `password authentication failed` at container startup.
    Canonical pattern: generate the password ONCE into a shell variable,
    reuse the same variable in both commands.

    Heuristic:
      - Apply to bootstrap scripts (`.sh`) and to SETUP/README .md docs.
      - Find every `openssl rand` invocation.
      - If a file contains BOTH `gcloud sql instances create` AND
        `gcloud secrets create` for a `<...>-db-password`-named secret,
        AND the password values used in each are produced by independent
        `openssl rand` subshells (not the same shell variable), fire.
      - Skip files with `# noqa: MAJ-014` near the openssl line.
    """
    ext = art.metadata.get("ext")
    if ext not in {".sh", ".md", ".yaml", ".yml"}:
        return []
    content = art.content

    # Must reference both: Cloud SQL instance creation AND db-password
    # secret creation for any drift to be possible.
    has_instance_create = bool(re.search(
        r"gcloud\s+sql\s+instances\s+create\b", content,
    ))
    has_secret_create = bool(re.search(
        r"gcloud\s+secrets\s+create\s+[\w-]*db-password\b", content,
    ))
    if not (has_instance_create and has_secret_create):
        return []

    # Count `openssl rand` subshells of the inline form `$(openssl rand`
    # or `\`openssl rand\``. Treat assignments like `PW=$(openssl rand ...)`
    # as a SINGLE generation site (the var can then be reused).
    inline_subshells = list(re.finditer(
        r"\$\(\s*openssl\s+rand[^)]*\)", content,
    ))
    # Subtract assignments that pin the result to a reusable shell var.
    # `PW=$(openssl rand ...)` or `PASSWORD=$(openssl rand ...)` produce
    # exactly one generation but allow N reuses via `$PW` / `$PASSWORD`.
    var_assignments = list(re.finditer(
        r"^\s*[A-Z_][A-Z0-9_]*\s*=\s*\$\(\s*openssl\s+rand[^)]*\)",
        content, re.MULTILINE,
    ))

    distinct_generations = len(inline_subshells)
    # If at least 2 inline openssl calls exist and the file is NOT using
    # the single-assign-and-reuse pattern for at least one of them,
    # treat that as drift.
    if distinct_generations < 2:
        return []

    # If all `openssl rand` invocations occur inside `VAR=$(...)` form
    # AND the file references the same VAR in both instance-create and
    # secret-create commands, that's the canonical safe pattern.
    if len(var_assignments) == 1 and distinct_generations == 1:
        return []

    # Find the first 'extra' openssl rand site that is NOT a single
    # var-assignment — that's our violation site.
    var_assign_spans = {(m.start(), m.end()) for m in var_assignments}
    violations: list[Violation] = []
    seen_lines: set[int] = set()
    for inline in inline_subshells:
        # Skip if this openssl is inside a `VAR=$(...)` assignment
        wraps_assignment = any(
            a_start <= inline.start() <= a_end
            for a_start, a_end in var_assign_spans
        )
        line_no = content[:inline.start()].count("\n") + 1
        if wraps_assignment and len(inline_subshells) > 1:
            # Two var-assignments = drift (each makes a different PW)
            if len(var_assignments) >= 2 and line_no not in seen_lines:
                if "noqa: MAJ-014" in content.split("\n")[line_no - 1]:
                    continue
                seen_lines.add(line_no)
                violations.append(Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=f"{art.identifier}:{line_no}",
                    excerpt=(
                        "multiple `openssl rand` assignments — instance "
                        "and secret will diverge (PPEME bug, 2026-05-14)"
                    ),
                    suggested_fix=rule.get("remediation", ""),
                ))
            continue
        if line_no in seen_lines:
            continue
        if "noqa: MAJ-014" in content.split("\n")[line_no - 1]:
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                "second `openssl rand` site — instance and secret "
                "passwords will diverge (PPEME bug, 2026-05-14)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))
    return violations


def _check_cloudrun_runtime_sa_missing_cloudsql_client(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-015: Engine bootstrap script creates a `<engine>-runtime` SA
    AND references `--add-cloudsql-instances=...` in deploy config, but
    fails to grant `roles/cloudsql.client` to that SA at project scope.

    WHY: PPEME bug from 2026-05-14 — runtime SA had no Cloud SQL client
    role, so Cloud SQL Auth Proxy failed with 403 `Not authorized to
    access resource. Possibly missing permission cloudsql.instances.get`
    at first container start. Granting `roles/cloudsql.client` at the
    project level is mandatory for any engine that uses the auth proxy.

    Heuristic:
      - Apply to `.sh`, `.md`, `.yaml`, `.yml` files under the repo.
      - Find `iam service-accounts create <name>-runtime` invocations.
      - For each runtime SA, search the SAME file for either a
        `roles/cloudsql.client` binding targeting that SA name, or for
        the absence of any `--add-cloudsql-instances` usage anywhere in
        the file (no Cloud SQL = no Cloud SQL client role required).
      - Fire if `--add-cloudsql-instances` appears but no
        `cloudsql.client` grant for the matched SA.
    """
    ext = art.metadata.get("ext")
    if ext not in {".sh", ".md", ".yaml", ".yml"}:
        return []
    content = art.content

    # No Cloud SQL referenced anywhere → not applicable.
    if not re.search(r"--add-cloudsql-instances", content):
        return []

    runtime_sa_matches = list(re.finditer(
        r"iam\s+service-accounts\s+create\s+([a-z][-a-z0-9]*-runtime)\b",
        content,
    ))
    if not runtime_sa_matches:
        return []

    violations: list[Violation] = []
    for m in runtime_sa_matches:
        sa_name = m.group(1)
        # Search for a cloudsql.client grant targeting this SA.
        grant_pattern = re.compile(
            rf"add-iam-policy-binding[^\n]*"
            rf"serviceAccount:{re.escape(sa_name)}[^\n]*"
            rf"roles/cloudsql\.client",
            re.DOTALL,
        )
        # Also accept the inverse multi-line shape where role appears first
        grant_pattern_b = re.compile(
            rf"roles/cloudsql\.client[^\n]*"
            rf"serviceAccount:{re.escape(sa_name)}",
            re.DOTALL,
        )
        # And accept the 3-line gcloud form with line breaks
        loose_pattern = re.compile(
            rf"add-iam-policy-binding.*?"
            rf"serviceAccount:{re.escape(sa_name)}.*?"
            rf"roles/cloudsql\.client",
            re.DOTALL,
        )
        has_grant = bool(
            grant_pattern.search(content)
            or grant_pattern_b.search(content)
            or loose_pattern.search(content)
        )
        if has_grant:
            continue
        line_no = content[:m.start()].count("\n") + 1
        if "noqa: MAJ-015" in content.split("\n")[line_no - 1]:
            continue
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"runtime SA `{sa_name}` created and Cloud SQL in use, "
                "but no `roles/cloudsql.client` grant found "
                "(PPEME bug, 2026-05-14)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))
    return violations


def _check_dockerfile_alembic_discipline(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-020: Engine repo has alembic but its Dockerfile does NOT
    COPY alembic + alembic.ini + start.sh, OR start.sh does not run
    `alembic upgrade head` before launching the app.

    WHY: HME bug #4 from the 2026-05-13 cascade — Dockerfile only copied
    `api/`, leaving `alembic.ini` and `alembic/` outside the image, so
    container start logged `No config file alembic.ini found` and the
    DB schema was never created. The canonical fix is in
    `standard_engine_deploy_template.md §1-§2`: Dockerfile copies
    `alembic/`, `alembic.ini`, `start.sh`; start.sh runs
    `alembic upgrade head` (12-factor migration on boot).

    Heuristic:
      - Apply only when the scanned artifact is a `Dockerfile` (file
        with that exact basename, any extension is ignored).
      - Look up the repo root from the artifact identifier (first path
        segment). If `<repo>/alembic.ini` or `<repo>/alembic/` exists,
        the rule is applicable.
      - Fire if Dockerfile does NOT contain BOTH of:
          (a) `COPY ... alembic` (alembic dir into image)
          (b) `COPY ... alembic.ini` (config file into image)
      - Separately, if the repo has `start.sh`, ensure it runs
        `alembic upgrade head`; if not, also fire (one violation per
        missing element).
      - `# noqa: MAJ-020` on the COPY/start.sh line suppresses.
    """
    name = Path(art.identifier).name
    if name != "Dockerfile":
        return []

    github_root = Path(
        os.environ.get("DRIFT_LOCAL_CODEBASE_ROOT",
                       "/Users/admin/Documents/GitHub")
    )
    parts = Path(art.identifier).parts
    if not parts:
        return []
    repo_root = github_root / parts[0]
    has_alembic_ini = (repo_root / "alembic.ini").exists()
    has_alembic_dir = (repo_root / "alembic").is_dir()
    if not (has_alembic_ini or has_alembic_dir):
        return []

    content = art.content
    if "noqa: MAJ-020" in content:
        return []
    violations: list[Violation] = []

    # Catch-all: `COPY . .` / `COPY . /app/` (or any whole-context copy)
    # implicitly includes alembic/ + alembic.ini. Skip the granular
    # checks if the Dockerfile copies the entire context.
    copies_whole_context = bool(re.search(
        r"^\s*COPY\s+(?:--\S+\s+)*\.\s+\.?/?",
        content, re.MULTILINE,
    ))
    # (a) COPY of alembic directory
    copy_alembic_dir = copies_whole_context or bool(re.search(
        r"^\s*COPY\b[^\n]*\balembic(?:/|\s|$)",
        content, re.MULTILINE | re.IGNORECASE,
    ))
    # (b) COPY of alembic.ini
    copy_alembic_ini = copies_whole_context or bool(re.search(
        r"^\s*COPY\b[^\n]*\balembic\.ini\b",
        content, re.MULTILINE | re.IGNORECASE,
    ))
    if has_alembic_dir and not copy_alembic_dir:
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=art.identifier,
            excerpt=(
                "repo has `alembic/` directory but Dockerfile does not "
                "COPY it — migrations cannot run at container startup "
                "(HME bug #4, 2026-05-13)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))
    if has_alembic_ini and not copy_alembic_ini:
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=art.identifier,
            excerpt=(
                "repo has `alembic.ini` but Dockerfile does not COPY it "
                "— `alembic upgrade head` will fail with 'No config "
                "file alembic.ini found' (HME bug #4, 2026-05-13)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    # (c) start.sh exists and runs `alembic upgrade head`
    start_sh = repo_root / "start.sh"
    if start_sh.exists():
        try:
            start_content = start_sh.read_text(encoding="utf-8",
                                               errors="ignore")
        except OSError:
            start_content = ""
        if "noqa: MAJ-020" not in start_content:
            runs_migration = bool(re.search(
                r"alembic\s+upgrade\s+head", start_content,
            ))
            if not runs_migration:
                try:
                    rel = str(start_sh.relative_to(github_root))
                except ValueError:
                    rel = str(start_sh)
                violations.append(Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    artifact=art.identifier,
                    location=rel,
                    excerpt=(
                        "start.sh exists but does not run `alembic "
                        "upgrade head` — engine boots without applying "
                        "schema (HME pattern, 2026-05-13)"
                    ),
                    suggested_fix=rule.get("remediation", ""),
                ))
    return violations


def _check_cloud_sql_url_discipline(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-021: Database URL construction uses raw f-string / string
    concatenation with a `/cloudsql/...` socket path instead of
    `sqlalchemy.engine.URL.create(..., query={"host": socket})`.

    WHY: HME bug #6 from the 2026-05-13 cascade — the URL form
    `postgresql://user:pw@{host}/db` treated `/cloudsql/<project>:
    <region>:<instance>` as a TCP hostname. The colons in the socket
    path corrupted parsing → psycopg2 silently fell back to the default
    socket `/var/run/postgresql/.s.PGSQL.5432`. The canonical fix is
    `URL.create(drivername=..., username=..., password=..., database=...,
    query={"host": socket_path})` — encodes the socket path safely.
    See `standard_engine_deploy_template.md §3`.

    Heuristic:
      - Apply to Python files only.
      - Skip test files (heuristic strings often appear in test
        fixtures).
      - Look for raw `postgresql://...@/cloudsql/` or
        `postgresql+psycopg2://...@/cloudsql/` patterns built via
        f-string or `.format()` or `+` concatenation.
      - Also fire on f-strings like f"postgresql://{user}:{password}@
        /cloudsql/...".
      - Do NOT fire if the same file (or surrounding ±15 lines) calls
        `URL.create(`.
      - `# noqa: MAJ-021` on the line suppresses.
    """
    if art.artifact_type != "code":
        return []
    if art.metadata.get("ext") != ".py":
        return []
    name_lower = art.identifier.lower()
    if (name_lower.startswith("test_") or "/tests/" in name_lower
            or "tests/" in name_lower or "_test.py" in name_lower):
        return []

    content = art.content
    lines = content.split("\n")

    # Heuristic patterns for raw URL construction targeting Cloud SQL
    # socket paths. Each pattern requires evidence that the URL is being
    # built (not just string-sliced) AND that it targets `/cloudsql/`
    # OR has a `{host}` / `{socket}` placeholder — that's where the bug
    # lives. Pure scheme-prefix slicing (`"postgresql://" + dsn[len("X"):]`)
    # is OUT of scope; tightened after sales-operating-system false
    # positive on 2026-05-14.
    raw_url_patterns = [
        # f-string with /cloudsql/ socket: f"postgresql://...@/cloudsql/..."
        re.compile(
            r"""f["'](?:postgresql|postgres)\+?\w*://[^"']*?"""
            r"""@/cloudsql/[^"']+["']""",
        ),
        # .format() / concat shape with explicit {host}/{socket} placeholder
        # and a /cloudsql/ reference (paren'd in same template or nearby).
        re.compile(
            r"""["'](?:postgresql|postgres)\+?\w*://[^"']*?"""
            r"""\{(?:host|socket)[^"']*?\}[^"']*?["']""",
        ),
    ]

    violations: list[Violation] = []
    seen_lines: set[int] = set()
    for pat in raw_url_patterns:
        for m in pat.finditer(content):
            line_no = content[:m.start()].count("\n") + 1
            if line_no in seen_lines:
                continue
            # If the file uses URL.create within ±15 lines of the match,
            # treat as safe (mixed-use file with the right pattern present).
            window_start = max(0, line_no - 15)
            window_end = min(len(lines), line_no + 15)
            window = "\n".join(lines[window_start:window_end])
            if re.search(r"\bURL\.create\s*\(", window):
                continue
            # Per-line noqa override
            if "noqa: MAJ-021" in lines[line_no - 1]:
                continue
            seen_lines.add(line_no)
            violations.append(Violation(
                rule_id=rule["id"],
                severity=rule["severity"],
                artifact=art.identifier,
                location=f"{art.identifier}:{line_no}",
                excerpt=(
                    "raw URL construction for Cloud SQL socket path — "
                    "colons in `/cloudsql/<proj>:<region>:<instance>` "
                    "corrupt parsing; use `URL.create(..., "
                    "query={'host': socket})` (HME bug #6, 2026-05-13)"
                ),
                suggested_fix=rule.get("remediation", ""),
            ))
    return violations


def _check_cloudbuild_trigger_invariant(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-022: Engine repo with `cloudbuild.yaml` + `Dockerfile` at root
    deploys to Cloud Run, so a Cloud Build trigger MUST be documented
    via `deploy/CLOUDBUILD_TRIGGER*.md` (and, in live mode, must exist
    as `<repo>-push-to-main` in the target GCP project).

    WHY: 2026-05-14 audit Drift #11 + #13 — `gcloud builds triggers list
    --project=gigaton-platform` returned 0 items. All four platform
    engines (gigaton-gateway, human-management-engine, user-access-engine,
    ppeme) deployed via manual `gcloud builds submit`. Memories claimed
    push-to-main auto-deploys; reality was no automation existed. This
    rule makes the gap visible the moment a new engine repo lands a
    cloudbuild.yaml without a corresponding trigger doc.

    Heuristic (static mode, always on):
      - Trigger only on the artifact `<repo>/cloudbuild.yaml` (root-level
        Cloud Build config; sibling job configs like
        `cloudbuild-job-*.yaml` are skipped — they document Cloud Run
        Jobs that are typically invoked on schedule, not push).
      - Resolve repo root via DRIFT_LOCAL_CODEBASE_ROOT (default
        /Users/admin/Documents/GitHub) + the artifact identifier's
        first path segment.
      - Skip if no sibling `Dockerfile` exists (build-only / library
        repo — not a Cloud Run service).
      - Skip if the artifact is the drift-sentinel's own deploy/
        cloudbuild.yaml or any nested `deploy/**/cloudbuild.yaml`
        (drift-sentinel has its own well-documented invocation pattern;
        it lives inside another repo and isn't a standalone engine).
      - Pass if `<repo>/deploy/` contains any file whose name matches
        the glob `*trigger*.md` (case-insensitive — accepts
        CLOUDBUILD_TRIGGER.md, CLOUDBUILD_TRIGGERS.md (plural), and the
        all-lowercase cloudbuild_trigger.md).
      - Otherwise fire one MAJOR violation.

    Heuristic (live mode, opt-in via env var):
      - Enabled when `DRIFT_CLOUDBUILD_TRIGGER_LIVE_CHECK=1` AND the
        Python library `google.cloud.devtools.cloudbuild_v1` is
        importable. Project defaults to `gigaton-platform`, overridable
        via `DRIFT_GCP_PROJECT`; region defaults to `us-central1`,
        overridable via `DRIFT_GCP_REGION`.
      - Calls `triggers.list_build_triggers` and checks whether any
        trigger's name equals `<repo>-push-to-main`.
      - On lib-missing OR API failure (auth / permission), emit a
        warning to stderr and fall back to static logic.
      - Live-mode violations carry metadata `live_check=true` in
        excerpt for downstream diagnostics.

      `# noqa: MAJ-022` anywhere in cloudbuild.yaml suppresses.
    """
    name = Path(art.identifier).name
    if name != "cloudbuild.yaml":
        return []
    if art.metadata.get("ext") not in {".yaml", ".yml"}:
        return []
    if "noqa: MAJ-022" in art.content:
        return []

    github_root = Path(
        os.environ.get("DRIFT_LOCAL_CODEBASE_ROOT",
                       "/Users/admin/Documents/GitHub")
    )
    parts = Path(art.identifier).parts
    if not parts:
        return []
    # Skip nested cloudbuild.yaml files (e.g. drift_sentinel/deploy/gcp/
    # cloudbuild.yaml lives under decision-engine — that's a sub-resource
    # build config, not the top-of-repo deploy config).
    if len(parts) != 2:
        return []
    repo_name = parts[0]
    repo_root = github_root / repo_name

    if not (repo_root / "Dockerfile").exists():
        return []

    # Static check — accept any case variant of *trigger*.md under deploy/
    deploy_dir = repo_root / "deploy"
    has_trigger_doc = False
    if deploy_dir.is_dir():
        for entry in deploy_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".md" and \
                    "trigger" in entry.stem.lower():
                has_trigger_doc = True
                break

    # Live check (opt-in)
    live_enabled = os.environ.get(
        "DRIFT_CLOUDBUILD_TRIGGER_LIVE_CHECK") == "1"
    live_trigger_found: bool | None = None  # None = not checked
    live_diag: str = ""
    if live_enabled:
        try:
            from google.cloud.devtools import cloudbuild_v1  # type: ignore
        except ImportError:
            sys.stderr.write(
                "MAJ-022 live check requested but "
                "google.cloud.devtools.cloudbuild_v1 is not installed; "
                "falling back to static check\n"
            )
        else:
            project = os.environ.get(
                "DRIFT_GCP_PROJECT", "gigaton-platform")
            region = os.environ.get(
                "DRIFT_GCP_REGION", "us-central1")
            try:
                client = cloudbuild_v1.CloudBuildClient()
                parent = f"projects/{project}/locations/{region}"
                expected = f"{repo_name}-push-to-main"
                live_trigger_found = False
                for trig in client.list_build_triggers(parent=parent):
                    if getattr(trig, "name", "") == expected:
                        live_trigger_found = True
                        break
                if not live_trigger_found:
                    live_diag = (
                        f"no trigger named '{expected}' found in "
                        f"{parent}"
                    )
            except (OSError, ValueError, RuntimeError) as exc:
                # Auth / network / quota failure — log and fall back.
                sys.stderr.write(
                    f"MAJ-022 live check error for {repo_name}: "
                    f"{exc}; falling back to static check\n"
                )
                live_trigger_found = None  # treat as not-checked

    # Decision matrix:
    #   - If live check was enabled, conclusive, AND found trigger → pass
    #     even if static doc missing (the trigger is real).
    #   - If live check was enabled, conclusive, AND no trigger → fire,
    #     regardless of static doc.
    #   - Otherwise (live check not run / inconclusive) → static check
    #     decides.
    if live_trigger_found is True:
        return []
    if live_trigger_found is False:
        return [Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=art.identifier,
            excerpt=(
                f"engine repo `{repo_name}` deploys via cloudbuild.yaml "
                f"but live_check=true reports {live_diag} — push-to-main "
                f"auto-deploy is not configured (Drift #11+#13, "
                f"2026-05-14)"
            ),
            suggested_fix=rule.get("remediation", ""),
        )]
    # Static-only path
    if has_trigger_doc:
        return []
    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt=(
            f"engine repo `{repo_name}` has cloudbuild.yaml + Dockerfile "
            f"but no deploy/*TRIGGER*.md — Cloud Build trigger is "
            f"undocumented and any 'auto-deploy' claim is unverifiable "
            f"(Drift #11+#13, 2026-05-14)"
        ),
        suggested_fix=rule.get("remediation", ""),
    )]


def _check_engine_module_missing_penrose_signal(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-019: Per penrose_falsification_doctrine.md — every new module
    under `engine/<sub-package>/*.py` must declare a Penrose signal +
    dimension in the module docstring (or top-of-file comment block).

    WHY: After Codification + Human Override engines ship (both v0.5),
    the doctrine commits to making Penrose-signal declarations mandatory
    so the falsification dashboard can audit every engine module. Modules
    that predate this rule (pre-2026-05-14 mtime) are grandfathered
    until next material edit (>10-line diff — out of scope for v0; the
    rule fires on absence and gracefully accepts a `# grandfathered:` or
    `# legacy:` first-line escape hatch).

    Heuristic:
      - Apply only to .py files whose repo-relative path matches
        `engine/<sub-package>/<file>.py` (at least two path segments
        beyond `engine/`, excluding `engine/__init__.py` and
        bare `engine/<file>.py` top-level modules).
      - Skip `__init__.py` empty stubs and anything under `tests/`.
      - Read the first 60 lines: if neither `penrose_signal:` nor
        `penrose_dimension:` appears in a docstring or `#` comment line,
        fire MAJOR.
      - First-5-line `# legacy:` or `# grandfathered:` markers exempt.
      - `# noqa: MAJ-019` on any line of the first 60 also exempts.
    """
    if art.artifact_type != "code":
        return []
    if art.metadata.get("ext") != ".py":
        return []
    identifier = art.identifier
    # Match `<repo>/engine/<subpackage>/<file>.py` — first segment is repo,
    # second must be `engine`, third is sub-package, fourth+ is module.
    parts = Path(identifier).parts
    if len(parts) < 4:
        return []
    if parts[1] != "engine":
        return []
    filename = parts[-1]
    if filename == "__init__.py":
        return []
    if "tests" in parts:
        return []

    lines = art.content.split("\n")
    head = "\n".join(lines[:60])

    # Exemptions
    first_five = "\n".join(lines[:5]).lower()
    if "# legacy:" in first_five or "# grandfathered:" in first_five:
        return []
    if "noqa: MAJ-019" in head:
        return []

    has_signal = bool(re.search(r"penrose_signal\s*:", head, re.IGNORECASE))
    has_dimension = bool(re.search(
        r"penrose_dimension\s*:", head, re.IGNORECASE))
    if has_signal and has_dimension:
        return []

    missing: list[str] = []
    if not has_signal:
        missing.append("penrose_signal")
    if not has_dimension:
        missing.append("penrose_dimension")

    return [Violation(
        rule_id=rule["id"],
        severity=rule["severity"],
        artifact=art.identifier,
        location=art.identifier,
        excerpt=(
            "engine module missing Penrose declaration: "
            f"{' + '.join(missing)} (per penrose_falsification_doctrine.md)"
        ),
        suggested_fix=rule.get("remediation", ""),
    )]


# ---------------------------------------------------------------------------
# Framework 5.19 BFT handlers — activate ~2026-05-16 (T+72hr from
# amendment effective_date 2026-05-13). These wire the 6 rules promoted
# by AMEND-2026-05-13-F519 (state_vector_substitution = CRIT-010;
# decision_without_state_estimate = MAJ-016; forecast_without_confidence_bands
# = MAJ-017; uncalibrated_forecast_as_authority = MAJ-018;
# interaction_without_effect_vector = MIN-007; interaction_without_cost =
# MIN-008). YAML defs landed 2026-05-13; without Python handlers they were
# silent (same drift class as MAJ-013/14/15 caught 2026-05-14). This block
# closes the gap before the T+72 activation window.
#
# WHY: doctrine-claim vs committed-code parity. The amendment text already
# says "T+72 hr drift-sentinel rule activation begins ~2026-05-16". The
# activation mechanism is wiring handlers into STRUCTURAL_HANDLERS — there
# is no separate `scheduled_activate_at` field; the rules become live the
# moment they have a handler that can fire. Landing these on 2026-05-14 is
# the canonical execution of the T+72 commitment.
#
# penrose_signal: weakens (forces forecasts + state to be falsifiable)
# penrose_dimension: pos1 (calibration), pos5 (instrumentation)
# ---------------------------------------------------------------------------

# Canonical BFT state vector — Framework 5.19. Set-equality only.
_BFT_CANONICAL_STATE_VARIABLES: frozenset[str] = frozenset({
    "trust", "attention", "clarity", "desire", "urgency",
    "value", "friction", "social_proof", "context_fit",
})

# Recognized aliases for state-vector declarations in Python.
_BFT_STATE_DECL_PATTERNS = (
    re.compile(r"\b(STATE_VARIABLES|STATE_VECTOR_KEYS|STATE_VECTOR_VARS)\s*[:=]\s*[\[\(\{]"),
    re.compile(r"class\s+StateVector\b"),
)

# Recognized list/tuple/set extraction inside a STATE_* declaration.
_BFT_STATE_LIST_BODY_RE = re.compile(
    r"(STATE_VARIABLES|STATE_VECTOR_KEYS|STATE_VECTOR_VARS)"
    r"\s*[:=]\s*[\[\(\{]([^\]\)\}]+)[\]\)\}]",
    re.DOTALL,
)


def _check_state_vector_substitution(
    art: Artifact, rule: dict
) -> list[Violation]:
    """CRIT-010: any spec/code declaring a state vector whose variable
    set is not exactly the canonical 9 from §5.19 BFT.

    Fires on:
      - Python module defining STATE_VARIABLES / STATE_VECTOR_KEYS /
        STATE_VECTOR_VARS as a list/tuple/set literal whose extracted
        identifiers don't set-equal the canonical 9.
      - Markdown spec with a fenced YAML/Python block declaring
        `state_vector:` / `state_variables:` / `STATE_VARIABLES =` whose
        body is not the canonical 9.

    Exemptions:
      - Fixtures prefixed `pre_mtheory_` or under `tests/historical/`.
      - `# noqa: CRIT-010` on any line of the declaration.
      - Docstring blocks that quote the canonical doctrine for explanation.
    """
    if art.artifact_type not in {"code", "markdown"}:
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".md"}:
        return []
    identifier_lc = art.identifier.lower()
    if "tests/historical/" in identifier_lc or "pre_mtheory_" in identifier_lc:
        return []
    if "noqa: CRIT-010" in art.content:
        return []

    violations: list[Violation] = []
    seen: set[tuple[int, str]] = set()

    for match in _BFT_STATE_LIST_BODY_RE.finditer(art.content):
        var_name = match.group(1)
        body = match.group(2)
        # Extract quoted-string identifiers from the body.
        idents = {
            m.group(1).lower()
            for m in re.finditer(r"""['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""", body)
        }
        if not idents:
            continue
        if idents == _BFT_CANONICAL_STATE_VARIABLES:
            continue
        line_no = art.content[: match.start()].count("\n") + 1
        key = (line_no, var_name)
        if key in seen:
            continue
        seen.add(key)
        missing = _BFT_CANONICAL_STATE_VARIABLES - idents
        extra = idents - _BFT_CANONICAL_STATE_VARIABLES
        diff = []
        if missing:
            diff.append(f"missing={sorted(missing)}")
        if extra:
            diff.append(f"extra={sorted(extra)}")
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"{var_name} diverges from canonical §5.19 state vector "
                f"({', '.join(diff) or 'set mismatch'})"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


# MAJ-016 — Decision certificates D2-D6 require state_vector_at_decision.
_BFT_DECISION_CLASS_RE = re.compile(
    r"""decision_class["']?\s*[:=]\s*['"]?(D[1-6])['"]?""",
    re.IGNORECASE,
)
_BFT_STATE_ESTIMATE_FIELD_RE = re.compile(
    r"\b(state_vector_at_decision|state_estimate|state_vector)\b",
    re.IGNORECASE,
)


def _check_decision_without_state_estimate(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-016: D2-D6 certificate emission without a state vector.

    Heuristic (v0): for every `decision_class: D[2-6]` occurrence, check
    that a state-estimate field appears within ±30 lines. D1 is exempt
    (auto-execute trivial-reversible per doctrine).

    Skips test fixtures asserting the absence (negative tests in files
    named `test_*.py` containing `assert.*state_estimate.*None` near the
    match are exempt).
    """
    if art.artifact_type not in {"code", "config", "markdown"}:
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".yaml", ".yml", ".json", ".md"}:
        return []
    if "noqa: MAJ-016" in art.content:
        return []

    lines = art.content.split("\n")
    violations: list[Violation] = []
    seen_lines: set[int] = set()

    for match in _BFT_DECISION_CLASS_RE.finditer(art.content):
        cls = match.group(1).upper()
        if cls == "D1":
            continue
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        # Window: ±30 lines around the match.
        start = max(0, line_no - 31)
        end = min(len(lines), line_no + 30)
        window = "\n".join(lines[start:end])
        if _BFT_STATE_ESTIMATE_FIELD_RE.search(window):
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"decision_class={cls} emitted without state_vector_at_decision "
                f"(§5.19 BFT — D2-D6 require forward-simulation state)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


# MAJ-017 — Forecasts must carry p10/p50/p90 distribution.
_BFT_FORECAST_DECL_RE = re.compile(
    r"\b(forecast|projection|predicted_revenue|predicted_conversion|"
    r"predicted_ltv|predicted_outcome)\s*[:=]",
    re.IGNORECASE,
)
_BFT_CONFIDENCE_BAND_RE = re.compile(
    # `\b` would block matches like `run_monte_carlo` because `_` is a word
    # char; allow free-floating substring match for the named bands.
    r"(p10|p50|p90|confidence_band|forecast_distribution|"
    r"prediction_interval|monte_carlo|distribution)",
    re.IGNORECASE,
)


def _check_forecast_without_confidence_bands(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-017: single-point forecasts violate §5.19 falsifiability.

    For every forecast/projection/predicted_* assignment, check that
    p10/p50/p90 or a named distribution appears within ±20 lines. Inside
    test fixtures, an `assert` line testing absence is exempt.
    """
    if art.artifact_type not in {"code", "config", "markdown"}:
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".yaml", ".yml", ".json", ".md", ".ts", ".tsx"}:
        return []
    if "noqa: MAJ-017" in art.content:
        return []

    lines = art.content.split("\n")
    violations: list[Violation] = []
    seen_lines: set[int] = set()

    for match in _BFT_FORECAST_DECL_RE.finditer(art.content):
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        # Skip lines that ARE the band declaration themselves.
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if _BFT_CONFIDENCE_BAND_RE.search(line_text) and not match.group(0).lower().startswith("forecast"):
            continue
        start = max(0, line_no - 21)
        end = min(len(lines), line_no + 20)
        window = "\n".join(lines[start:end])
        if _BFT_CONFIDENCE_BAND_RE.search(window):
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"forecast/projection without p10/p50/p90 distribution "
                f"(§5.19 BFT falsifiability requirement)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


# MAJ-018 — pre-Mtheory forecasts cited as authority without label.
_BFT_FORECAST_AUTHORITY_RE = re.compile(
    r"\b(forecast_id|predicted_revenue|predicted_conversion|predicted_ltv)"
    r"\s*[:=]",
    re.IGNORECASE,
)
_BFT_CALIBRATION_LABEL_RE = re.compile(
    r"\b(pre_mtheory\s*[:=]\s*true|non_authoritative\s*[:=]\s*true|"
    r"uncalibrated_warning|calibration_status\s*[:=]\s*['\"]?"
    r"(production_grade|calibrated))\b",
    re.IGNORECASE,
)
_BFT_AUTHORITY_VERB_RE = re.compile(
    r"\b(recommend|action|authoritative|drives|trigger|cite)\b",
    re.IGNORECASE,
)


def _check_uncalibrated_forecast_as_authority(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MAJ-018: forecast cited authoritatively without calibration label.

    Heuristic (v0 — no live PPEME calibration table read; surfaces drift
    on artifact text alone): fires when a forecast_id / predicted_*
    appears alongside an authority-suggesting verb (recommend / action /
    drives / trigger / cite) within ±15 lines AND no explicit calibration
    label (pre_mtheory: true, non_authoritative: true, uncalibrated_warning,
    calibration_status: production_grade) appears within ±15 lines.

    PPEME-table-cross-reference is the v1 upgrade (per rule YAML). v0
    surfaces the high-likelihood drift surface for human review.
    """
    if art.artifact_type not in {"code", "markdown", "config"}:
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".md", ".yaml", ".yml", ".json"}:
        return []
    if "noqa: MAJ-018" in art.content:
        return []

    lines = art.content.split("\n")
    violations: list[Violation] = []
    seen_lines: set[int] = set()

    for match in _BFT_FORECAST_AUTHORITY_RE.finditer(art.content):
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        start = max(0, line_no - 16)
        end = min(len(lines), line_no + 15)
        window = "\n".join(lines[start:end])
        if not _BFT_AUTHORITY_VERB_RE.search(window):
            continue
        if _BFT_CALIBRATION_LABEL_RE.search(window):
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"forecast referenced as authority without calibration label "
                f"(§5.19 BFT — pre_mtheory forecasts cannot drive decisions)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


# MIN-007 — production interaction surface without effect-vector catalog entry.
_BFT_INTERACTION_EMIT_RE = re.compile(
    r"\b(emit_event|interaction_id|pipeline\.process)\s*[\(:=]",
)
_BFT_INTERACTION_CATALOG_LINK_RE = re.compile(
    r"\b(interaction_catalog|delta_i|effect_vector|catalog_entry)\b",
    re.IGNORECASE,
)


def _check_interaction_without_effect_vector(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MIN-007: production interaction surface without catalog entry.

    Fires on event emitters / pipeline.process calls / interaction_id
    declarations that don't reference interaction_catalog or a delta_i
    effect vector within ±25 lines. Test fixtures + `# noqa: MIN-007`
    are exempt.

    Cross-reference to PPEME's interaction_catalog table is the v1 upgrade.
    v0 surfaces the textual drift signal so the catalog can be backfilled.
    """
    if art.artifact_type != "code":
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return []
    if "noqa: MIN-007" in art.content:
        return []
    if "tests/" in art.identifier or "/test_" in art.identifier:
        return []

    lines = art.content.split("\n")
    violations: list[Violation] = []
    seen_lines: set[int] = set()

    for match in _BFT_INTERACTION_EMIT_RE.finditer(art.content):
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        start = max(0, line_no - 26)
        end = min(len(lines), line_no + 25)
        window = "\n".join(lines[start:end])
        if _BFT_INTERACTION_CATALOG_LINK_RE.search(window):
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"interaction emitter without interaction_catalog / delta_i "
                f"reference (§5.19 BFT Interaction Model)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


# MIN-008 — interaction_catalog entry without estimated_cost.
_BFT_CATALOG_ENTRY_RE = re.compile(
    r"(INSERT\s+INTO\s+interaction_catalog|interaction_catalog\."
    r"(insert|create|upsert|add_entry))",
    re.IGNORECASE,
)
_BFT_COST_FIELD_RE = re.compile(
    r"\bestimated_cost\b",
    re.IGNORECASE,
)


def _check_interaction_without_cost(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MIN-008: catalog entry insert without estimated_cost field.

    Recommendation panels rank by delta_i / estimated_cost. Missing cost
    eliminates the entry from ranked output silently.

    Fires when a catalog insert/upsert/create call appears without an
    estimated_cost reference within ±20 lines.
    """
    if art.artifact_type not in {"code", "config"}:
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".sql", ".yaml", ".yml"}:
        return []
    if "noqa: MIN-008" in art.content:
        return []

    lines = art.content.split("\n")
    violations: list[Violation] = []
    seen_lines: set[int] = set()

    for match in _BFT_CATALOG_ENTRY_RE.finditer(art.content):
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        start = max(0, line_no - 21)
        end = min(len(lines), line_no + 20)
        window = "\n".join(lines[start:end])
        if _BFT_COST_FIELD_RE.search(window):
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"interaction_catalog entry without estimated_cost field "
                f"(§5.19 BFT — ranking surface depends on delta_i/cost)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


# MIN-010 — catalog-shaped table created without tags JSONB column.
_CATALOG_TABLE_SUFFIXES = (
    "catalog", "registry", "taxonomy", "dictionary", "dimensions", "map"
)
_CATALOG_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(\w+_(?:" + "|".join(_CATALOG_TABLE_SUFFIXES) + r"))\s*\(",
    re.IGNORECASE,
)
_CATALOG_ALEMBIC_CREATE_RE = re.compile(
    r"""op\.create_table\(\s*['"](\w+_(?:"""
    + "|".join(_CATALOG_TABLE_SUFFIXES)
    + r"""))['"]""",
    re.IGNORECASE,
)
_TAGS_JSONB_RE = re.compile(r"\btags\s+JSONB\b", re.IGNORECASE)
_TAGS_ALEMBIC_RE = re.compile(
    r"""Column\(\s*['"]tags['"]\s*,\s*(?:postgresql\.)?JSONB""",
    re.IGNORECASE,
)


def _catalog_table_body(content: str, open_paren_idx: int) -> str:
    """Return text from open paren through matching close paren (simple)."""
    depth = 0
    end = len(content)
    for i in range(open_paren_idx, len(content)):
        ch = content[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return content[open_paren_idx:end]


def _check_catalog_table_missing_tags_jsonb(
    art: Artifact, rule: dict
) -> list[Violation]:
    """MIN-010: catalog-shaped table created without tags JSONB column.

    Per foundational_modular_replication_via_input_substitution.md, any
    catalog table (name ending in _catalog/_registry/_taxonomy/_dictionary
    /_dimensions/_map) must include `tags JSONB` so it can participate in
    multi-axis filtering by operator_context.

    Fires on CREATE TABLE (SQL) or op.create_table (Alembic) for catalog-
    named tables that have no tags JSONB column declared in the same
    body. A follow-up ALTER TABLE ... ADD COLUMN tags JSONB in the same
    migration file also passes.
    """
    if art.artifact_type not in {"code", "config"}:
        return []
    ext = art.metadata.get("ext")
    if ext not in {".py", ".sql"}:
        return []
    if "noqa: MIN-010" in art.content or "MIN-010 N/A" in art.content:
        return []

    violations: list[Violation] = []
    seen_lines: set[int] = set()

    # File-level escape: ALTER TABLE adding tags JSONB elsewhere in same file
    file_has_tags_alter = bool(re.search(
        r"ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"tags\s+JSONB",
        art.content,
        re.IGNORECASE,
    ))

    # SQL CREATE TABLE pattern
    for match in _CATALOG_CREATE_TABLE_RE.finditer(art.content):
        table_name = match.group(1)
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        body = _catalog_table_body(art.content, match.end() - 1)
        if _TAGS_JSONB_RE.search(body):
            continue
        if file_has_tags_alter:
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"CREATE TABLE {table_name} missing `tags JSONB` column "
                f"(MIN-010 — Modular Replication doctrine requires multi-"
                f"axis tags on every catalog-shaped table)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    # Alembic op.create_table pattern
    for match in _CATALOG_ALEMBIC_CREATE_RE.finditer(art.content):
        table_name = match.group(1)
        line_no = art.content[: match.start()].count("\n") + 1
        if line_no in seen_lines:
            continue
        # Look at the next ~80 lines for the closing of the create_table call
        lines = art.content.split("\n")
        window = "\n".join(lines[line_no - 1 : min(len(lines), line_no + 80)])
        if _TAGS_ALEMBIC_RE.search(window):
            continue
        if file_has_tags_alter:
            continue
        seen_lines.add(line_no)
        violations.append(Violation(
            rule_id=rule["id"],
            severity=rule["severity"],
            artifact=art.identifier,
            location=f"{art.identifier}:{line_no}",
            excerpt=(
                f"op.create_table('{table_name}', ...) missing tags JSONB "
                f"Column (MIN-010 — Modular Replication doctrine)"
            ),
            suggested_fix=rule.get("remediation", ""),
        ))

    return violations


def _path_matches_exclude(
    identifier: str, excludes: list[str] | None
) -> bool:
    """Return True if `identifier` matches any glob in `excludes`.

    Matches against both the raw identifier (e.g.
    `decision-engine/tests/test_drift_preventive_rules.py`) and the
    repo-relative form (first path segment stripped — e.g.
    `tests/test_drift_preventive_rules.py`). This lets rule authors
    write either form in `path_exclude:` — repo-relative is more
    portable across the multi-repo scan.
    """
    if not excludes:
        return False
    candidates = [identifier]
    parts = Path(identifier).parts
    if len(parts) > 1:
        candidates.append(str(Path(*parts[1:])))
    for pat in excludes:
        for cand in candidates:
            if fnmatch.fnmatch(cand, pat):
                return True
    return False


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
    "MAJ-013": _check_cloudbuild_secret_env_in_non_bash_step,
    "MAJ-014": _check_cloudsql_password_drift_between_instance_and_secret,
    "MAJ-015": _check_cloudrun_runtime_sa_missing_cloudsql_client,
    "MAJ-019": _check_engine_module_missing_penrose_signal,
    "MAJ-020": _check_dockerfile_alembic_discipline,
    "MAJ-021": _check_cloud_sql_url_discipline,
    "MAJ-022": _check_cloudbuild_trigger_invariant,
    "MAJ-006": _check_schema_without_migration,
    "MAJ-009": _check_phase_gate_violation,
    "MAJ-010": _check_value_chain_break,
    "MIN-001": _check_typescript_any,
    "MIN-009": _check_cloud_run_max_instances_above_one,
    "MIN-010": _check_catalog_table_missing_tags_jsonb,
    # Framework 5.19 BFT — wired 2026-05-14, active per T+72 commitment
    # (effective_date 2026-05-13 + 72hr = ~2026-05-16). See
    # framework_5_19_bft_amendment.md and the BFT handler block above.
    "CRIT-010": _check_state_vector_substitution,
    "MAJ-016": _check_decision_without_state_estimate,
    "MAJ-017": _check_forecast_without_confidence_bands,
    "MAJ-018": _check_uncalibrated_forecast_as_authority,
    "MIN-007": _check_interaction_without_effect_vector,
    "MIN-008": _check_interaction_without_cost,
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
            # Per-rule path exclusion (optional `path_exclude:` field in
            # DRIFT_RULES.yaml). Lets a rule skip artifacts whose identifier
            # matches any glob in the list. Used to exempt test-fixture
            # files that intentionally demonstrate an anti-pattern in
            # string literals (the scanner should not flag its own self-
            # test inputs). Match is checked against the full identifier
            # and against the path relative to its repo root (first path
            # segment stripped), so authors can write either form.
            # WHY: CRIT-011 false-positive cluster on 2026-05-14.
            if _path_matches_exclude(art.identifier, rule.get("path_exclude")):
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
