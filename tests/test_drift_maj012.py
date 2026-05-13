"""MAJ-012 — in_memory_state_without_db_writethrough."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "drift_sentinel"))

from drift_scan import (  # noqa: E402
    Artifact,
    _check_in_memory_state_without_db_writethrough,
)

_RULE = {
    "id": "MAJ-012",
    "severity": "major",
    "remediation": "DB writethrough required",
}


def _art(content: str) -> Artifact:
    return Artifact(
        source="codebase",
        identifier="services/example/main.py",
        artifact_type="code",
        content=content,
        metadata={"ext": ".py"},
    )


def test_fires_on_chat_queue_bug_pattern():
    """Pre-fix #198 pattern: dict mutation in a handler that doesn't
    write to the matching DB table within the same window."""
    code = """
_approval_queue: dict[str, dict] = {}

async def enqueue_decision(batch_id, decision_id, candidate):
    queue_id = "q_x"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO approval_queue (queue_id) VALUES ($1)",
            queue_id,
        )
    _approval_queue[queue_id] = {"x": 1}

async def chat_handler(req):
    # Bug: in-memory only, no INSERT INTO approval_queue near this line.
    queue_id = "q_chat"
    candidate = {"action_type": "send"}
    button_actions = []
    for _ in range(3):
        button_actions.append({"action": "approve"})
    _approval_queue[queue_id] = {"queue_id": queue_id, "candidate": candidate}
"""
    violations = _check_in_memory_state_without_db_writethrough(_art(code), _RULE)
    assert len(violations) == 1
    assert "_approval_queue" in violations[0].excerpt
    assert "approval_queue" in violations[0].excerpt


def test_clean_when_db_write_paired_with_mutation():
    """Canonical pattern: mutation is paired with INSERT within window."""
    code = """
_approval_queue: dict[str, dict] = {}

async def enqueue(batch_id, decision_id):
    queue_id = "q_x"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO approval_queue (queue_id) VALUES ($1)",
            queue_id,
        )
    _approval_queue[queue_id] = {"x": 1}
"""
    assert _check_in_memory_state_without_db_writethrough(_art(code), _RULE) == []


def test_skips_db_fallback_branch():
    """Mutations inside the `_db_available` False branch are intentional."""
    code = """
_db_available = False
_approval_queue: dict[str, dict] = {}

async def decide(queue_id, decision):
    if _db_available:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO approval_queue (queue_id) VALUES ($1)",
                queue_id,
            )
    else:
        # Fallback path — DB is down, in-memory mutation is the
        # intentional degraded behavior, NOT a drift violation.
        item = _approval_queue[queue_id]
        item["status"] = decision
        _approval_queue[queue_id] = item
"""
    assert _check_in_memory_state_without_db_writethrough(_art(code), _RULE) == []


def test_no_fire_when_no_matching_db_table():
    """A plain in-memory cache with no matching SQL is out of scope."""
    code = """
_session_cache: dict[str, dict] = {}

def remember(k, v):
    _session_cache[k] = v
"""
    assert _check_in_memory_state_without_db_writethrough(_art(code), _RULE) == []


def test_no_fire_on_non_python_files():
    art = Artifact(
        source="codebase",
        identifier="foo.ts",
        artifact_type="code",
        content="const _approval_queue = {};",
        metadata={"ext": ".ts"},
    )
    assert _check_in_memory_state_without_db_writethrough(art, _RULE) == []
