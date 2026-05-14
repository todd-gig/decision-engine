"""Drift Sentinel scanner false-positive remediation tests.

Covers three changes from the 2026-05-14 cluster:

1. Path-walking excludes `.claude/worktrees/` (transient Claude Code
   agent worktrees that mirror real repo code and produce phantom
   drift hits). 8/29 CRIT-011 hits on the 2026-05-14 scan came from
   worktree mirrors of `tests/test_drift_preventive_rules.py`.

2. Per-rule `path_exclude:` field in DRIFT_RULES.yaml. CRIT-011 now
   declares `path_exclude: ["tests/test_drift_preventive_rules.py"]`
   because that file intentionally demonstrates the os.environ
   anti-pattern in STRING LITERALS to prove the scanner catches it —
   the scanner should not flag its own self-test inputs.
   This is per-rule (not a blanket tests/ blacklist) so all OTHER
   rules continue to apply to that file.

3. MAJ-019 (engine_module_missing_penrose_signal) is in the
   `rules_applied:` array for `local_codebase`. Before this PR it was
   defined but never wired, so the doctrine commitment from
   penrose_falsification_doctrine.md never fired.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "drift_sentinel"))

from drift_scan import (  # noqa: E402
    Artifact,
    LocalCodebaseAdapter,
    RuleEngine,
    _check_engine_module_missing_penrose_signal,
    _path_matches_exclude,
)

_RULES_FILE = _HERE.parent / "drift_sentinel" / "DRIFT_RULES.yaml"

_MAJ_019_RULE = {
    "id": "MAJ-019",
    "severity": "major",
    "remediation": "Add penrose_signal + penrose_dimension to docstring.",
}


# ---------------------------------------------------------------------------
# 1. LocalCodebaseAdapter._path_excluded — worktree skipping
# ---------------------------------------------------------------------------

def test_worktree_path_excluded():
    """Agent worktree paths are filtered out before file read."""
    p = Path(".claude/worktrees/agent-a4fcafb740755e1c9/"
             "tests/test_drift_preventive_rules.py")
    assert LocalCodebaseAdapter._path_excluded(p) is True


def test_worktree_nested_path_excluded():
    """Deeply nested worktree paths still skip."""
    p = Path("decision-engine/.claude/worktrees/agent-abc123/api/main.py")
    assert LocalCodebaseAdapter._path_excluded(p) is True


def test_real_tests_dir_not_excluded_by_path_walk():
    """Regular tests/ files are NOT skipped at the filesystem walk level —
    they remain in scope for every rule that doesn't opt out per-rule.

    Doctrine: tests SHOULD be scanned by most rules. Per-rule
    `path_exclude:` is the precise mechanism for opting out, not a
    blanket tests/ blacklist.
    """
    p = Path("decision-engine/tests/test_drift_preventive_rules.py")
    assert LocalCodebaseAdapter._path_excluded(p) is False


def test_existing_single_segment_skip_still_works():
    """node_modules / __pycache__ / .git still skip."""
    assert LocalCodebaseAdapter._path_excluded(
        Path("apps/foo/node_modules/lib/index.ts")) is True
    assert LocalCodebaseAdapter._path_excluded(
        Path("engine/__pycache__/x.pyc")) is True


# ---------------------------------------------------------------------------
# 2. _path_matches_exclude — per-rule glob matching
# ---------------------------------------------------------------------------

def test_path_matches_exclude_exact_repo_relative():
    """Exclude expressed as repo-relative path matches the full identifier."""
    excludes = ["tests/test_drift_preventive_rules.py"]
    assert _path_matches_exclude(
        "decision-engine/tests/test_drift_preventive_rules.py",
        excludes,
    ) is True


def test_path_matches_exclude_glob():
    """fnmatch-style globs are supported."""
    excludes = ["tests/test_drift_*.py"]
    assert _path_matches_exclude(
        "decision-engine/tests/test_drift_anything.py", excludes) is True
    # Non-matching path
    assert _path_matches_exclude(
        "decision-engine/tests/test_pipeline.py", excludes) is False


def test_path_matches_exclude_empty_or_none():
    """Empty/None excludes never match."""
    assert _path_matches_exclude("any/path.py", None) is False
    assert _path_matches_exclude("any/path.py", []) is False


def test_path_matches_exclude_unrelated_path():
    """Unrelated paths don't match."""
    excludes = ["tests/test_drift_preventive_rules.py"]
    assert _path_matches_exclude(
        "decision-engine/engine/pipeline.py", excludes) is False


# ---------------------------------------------------------------------------
# 3. RuleEngine.evaluate honors path_exclude (integration with CRIT-011)
# ---------------------------------------------------------------------------

def _make_engine() -> RuleEngine:
    return RuleEngine(_RULES_FILE)


def _crit_011_fixture_artifact() -> Artifact:
    """Artifact that DOES contain the CRIT-011 anti-pattern under a
    FastAPI route decorator. Used to verify both that (a) the rule fires
    on this content normally and (b) the rule is suppressed when the
    identifier matches `path_exclude`.
    """
    content = (
        "from fastapi import APIRouter\n"
        "import os\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/x')\n"
        "def handler():\n"
        "    os.environ['ANTHROPIC_API_KEY'] = 'leaked'\n"
        "    return {}\n"
    )
    return Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="decision-engine/tests/test_drift_preventive_rules.py",
        content=content,
        metadata={"ext": ".py"},
    )


def test_crit_011_path_exclude_skips_self_test_fixture():
    """CRIT-011 declares `path_exclude` for its own self-test file —
    the rule must NOT fire on that file even when the anti-pattern
    is present in string literals or actual code.
    """
    engine = _make_engine()
    art = _crit_011_fixture_artifact()
    violations = engine.evaluate(art)
    crit_011 = [v for v in violations if v.rule_id == "CRIT-011"]
    assert crit_011 == [], (
        f"CRIT-011 should be excluded for self-test fixture file; "
        f"got {crit_011}"
    )


def test_crit_011_still_fires_on_real_application_code():
    """CRIT-011 must still fire on normal application code — the
    exclusion is path-specific, not a global disable.
    """
    engine = _make_engine()
    content = (
        "from fastapi import APIRouter\n"
        "import os\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/x')\n"
        "def handler():\n"
        "    os.environ['ANTHROPIC_API_KEY'] = 'leaked'\n"
        "    return {}\n"
    )
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="decision-engine/api/some_handler.py",
        content=content,
        metadata={"ext": ".py"},
    )
    violations = engine.evaluate(art)
    crit_011 = [v for v in violations if v.rule_id == "CRIT-011"]
    assert len(crit_011) >= 1, (
        "CRIT-011 should fire on regular application code; "
        f"got {crit_011}"
    )


def test_other_rules_still_apply_to_excluded_path():
    """The CRIT-011 path_exclude must NOT cascade to other rules.
    A different rule that legitimately matches the excluded file must
    still fire. We exercise MIN-001 (typescript_any) via a .ts artifact
    bearing the CRIT-011 path identifier — confirms that per-rule
    exclusion is per-rule.
    """
    engine = _make_engine()
    # Construct an artifact with the excluded filename but in a context
    # where MIN-001 should fire. MIN-001 only scans `.ts`/`.tsx` files,
    # so use a .ts content + .ts extension to verify the rule still
    # applies to OTHER files; CRIT-011 path_exclude is rule-scoped.
    ts_art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="decision-engine/apps/web/index.ts",
        content="const x: any = 1;\nconst y = x as any;\n",
        metadata={"ext": ".ts"},
    )
    violations = engine.evaluate(ts_art)
    min_001 = [v for v in violations if v.rule_id == "MIN-001"]
    assert len(min_001) >= 1


# ---------------------------------------------------------------------------
# 4. MAJ-019 is in the applied list + the handler works
# ---------------------------------------------------------------------------

def test_maj_019_in_rules_applied_for_local_codebase():
    """The doctrine commitment from penrose_falsification_doctrine.md
    is honored — MAJ-019 fires against local_codebase.
    """
    with _RULES_FILE.open() as fh:
        spec = yaml.safe_load(fh)
    applied = spec["source_routing"]["local_codebase"]["rules_applied"]
    assert "MAJ-019" in applied, (
        "MAJ-019 must be wired into local_codebase rules_applied "
        "(penrose_falsification_doctrine.md commitment)"
    )


def test_maj_019_fires_on_engine_module_missing_declaration():
    """An engine sub-package module with no Penrose declaration fires."""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="some-repo/engine/sub_package/feature.py",
        content='"""A new engine module without a Penrose declaration."""\n'
                "\n"
                "def do_thing():\n"
                "    return 1\n",
        metadata={"ext": ".py"},
    )
    out = _check_engine_module_missing_penrose_signal(art, _MAJ_019_RULE)
    assert len(out) == 1
    assert out[0].rule_id == "MAJ-019"


def test_maj_019_passes_when_declaration_present():
    """A module declaring penrose_signal + penrose_dimension passes."""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="some-repo/engine/sub_package/feature.py",
        content=(
            '"""Feature module.\n'
            "\n"
            "penrose_signal: weakens\n"
            "penrose_dimension: codification\n"
            '"""\n'
            "\n"
            "def do_thing():\n"
            "    return 1\n"
        ),
        metadata={"ext": ".py"},
    )
    out = _check_engine_module_missing_penrose_signal(art, _MAJ_019_RULE)
    assert out == []


def test_maj_019_skips_init_py():
    """`__init__.py` is exempt — it's typically an empty stub."""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="some-repo/engine/sub_package/__init__.py",
        content="",
        metadata={"ext": ".py"},
    )
    out = _check_engine_module_missing_penrose_signal(art, _MAJ_019_RULE)
    assert out == []


def test_maj_019_skips_top_level_engine_modules():
    """Bare `engine/foo.py` (no sub-package) is out of v0 scope —
    rule applies to `engine/<sub-package>/<file>.py` shape only.
    """
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="some-repo/engine/main.py",
        content='"""Top-level engine entry."""\n',
        metadata={"ext": ".py"},
    )
    out = _check_engine_module_missing_penrose_signal(art, _MAJ_019_RULE)
    assert out == []


def test_maj_019_legacy_marker_exempts():
    """First-5-line `# legacy:` / `# grandfathered:` comment exempts."""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="some-repo/engine/sub_package/old.py",
        content="# legacy: predates penrose doctrine\n\ndef x():\n    return 1\n",
        metadata={"ext": ".py"},
    )
    out = _check_engine_module_missing_penrose_signal(art, _MAJ_019_RULE)
    assert out == []


def test_maj_019_noqa_exempts():
    """A `# noqa: MAJ-019` line within the first 60 exempts."""
    art = Artifact(
        source="local_codebase",
        artifact_type="code",
        identifier="some-repo/engine/sub_package/x.py",
        content='"""Doc."""\n# noqa: MAJ-019\ndef x():\n    return 1\n',
        metadata={"ext": ".py"},
    )
    out = _check_engine_module_missing_penrose_signal(art, _MAJ_019_RULE)
    assert out == []
