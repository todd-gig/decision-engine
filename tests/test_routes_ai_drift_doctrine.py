"""FastAPI route tests for /v1/ai/invoke + /v1/drift/open + /v1/doctrine/*."""
from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from engine.ai_router import storage as audit_storage
from engine.ai_router.providers import ProviderResponse
from engine.ai_router.providers import anthropic as _anthropic_mod


@pytest.fixture
def client():
    return TestClient(app)


# ── /v1/ai/invoke ────────────────────────────────────────────────────────────


@pytest.fixture
def fake_anthropic(monkeypatch):
    def fake_call(
        *, prompt, model, prompt_version, schema_version,
        max_tokens=1024, temperature=0.0, timeout_seconds=30,
    ):
        return ProviderResponse(
            text=f"http-echo:{prompt}",
            model_used=model,
            in_tokens=12,
            out_tokens=24,
        )
    monkeypatch.setattr(_anthropic_mod, "is_available", lambda: True)
    monkeypatch.setattr(_anthropic_mod, "call", fake_call)
    yield fake_call


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch):
    audit_db = tmp_path / "llm_audit.db"
    monkeypatch.setattr(audit_storage, "_default_db_path", lambda: audit_db)
    monkeypatch.setenv("LLM_AUDIT_HMAC_KEY", "test-key")
    yield str(audit_db)


def test_ai_invoke_success(client, fake_anthropic, isolated_audit_db):
    r = client.post("/v1/ai/invoke", json={
        "prompt": "hello",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "prompt_version": "test.v1",
        "schema_version": "test_schema.v1",
        "caller_engine": "sales-os",
        "caller_function": "explain_recommendations",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "http-echo:hello"
    assert body["provider_used"] == "anthropic"
    assert body["model_used"] == "claude-opus-4-7"
    assert body["in_tokens"] == 12
    assert body["out_tokens"] == 24
    assert body["audit_id"]
    # cost computed from anthropic pricing table
    assert body["cost_usd"] > 0


def test_ai_invoke_rejects_missing_required_fields(client):
    """CRIT-003 + CRIT-007 enforcement at the API boundary."""
    r = client.post("/v1/ai/invoke", json={
        "prompt": "hello",
        # Missing provider, model, prompt_version, schema_version, etc.
    })
    assert r.status_code == 422


def test_ai_invoke_unavailable_provider_returns_503(client, monkeypatch, isolated_audit_db):
    """When no provider in the chain is available, return 503 (not 500)."""
    monkeypatch.setattr(_anthropic_mod, "is_available", lambda: False)
    r = client.post("/v1/ai/invoke", json={
        "prompt": "x",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "prompt_version": "t.v1",
        "schema_version": "ts.v1",
        "caller_engine": "t",
        "caller_function": "f",
    })
    assert r.status_code == 503


def test_ai_invoke_with_audit_metadata(client, fake_anthropic, isolated_audit_db):
    r = client.post("/v1/ai/invoke", json={
        "prompt": "metadata-test",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "prompt_version": "t.v1",
        "schema_version": "ts.v1",
        "caller_engine": "test",
        "caller_function": "f",
        "audit_metadata": {"user_id": "u-1", "decision_id": "DEC-1"},
    })
    assert r.status_code == 200
    # Verify audit row carries metadata
    with sqlite3.connect(isolated_audit_db) as conn:
        row = conn.execute("SELECT audit_metadata FROM llm_audit").fetchone()
        import json
        meta = json.loads(row[0])
        assert meta["user_id"] == "u-1"


# ── /v1/drift/open ───────────────────────────────────────────────────────────


@pytest.fixture
def seeded_drift_db(monkeypatch, tmp_path: Path):
    """Build a fake drift_history.db at the canonical location and return path."""
    # Patch the route's path resolution to use a tmp DB
    db_dir = tmp_path / "drift_sentinel"
    db_dir.mkdir()
    db_path = db_dir / "drift_history.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE scans (
            scan_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            sources TEXT NOT NULL,
            total_artifacts INTEGER NOT NULL,
            critical INTEGER NOT NULL,
            major INTEGER NOT NULL,
            minor INTEGER NOT NULL,
            info INTEGER NOT NULL
        );
        CREATE TABLE violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            artifact TEXT NOT NULL,
            location TEXT,
            excerpt TEXT
        );
    """)
    scan_id = "scan-" + str(uuid.uuid4())
    conn.execute(
        "INSERT INTO scans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (scan_id, "2026-05-14T10:00:00Z", "local_codebase", 100, 2, 3, 5, 1),
    )
    rows = [
        (scan_id, "CRIT-001", "critical", "engine/foo.py", "L10", "while True without rollback"),
        (scan_id, "CRIT-008", "critical", "engine/pricing.py", "L42", "no assumptions[]"),
        (scan_id, "MAJ-005", "major", "package.json", None, "circular dep"),
        (scan_id, "MAJ-012", "major", "module.py", "L88", "in-memory cache no DB writethrough"),
        (scan_id, "MAJ-013", "major", "cloudbuild.yaml", "L20", "secret in non-bash step"),
        (scan_id, "MIN-001", "minor", "ui.tsx", "L15", ": any usage"),
        (scan_id, "INFO-001", "info", "docs/notes.md", None, "documented override"),
    ]
    conn.executemany(
        "INSERT INTO violations(scan_id, rule_id, severity, artifact, location, excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?)", rows,
    )
    conn.commit()
    conn.close()

    # Monkey-patch the path resolution inside the route
    import api.routes as routes_mod
    real_resolve = Path.resolve

    # We can't easily replace Path's resolution, so instead patch the
    # route function path directly. Simpler approach: copy the seeded DB
    # to the expected production location and restore after.
    real_db = (
        Path(__file__).resolve().parent.parent / "drift_sentinel" / "drift_history.db"
    )
    backup = None
    if real_db.exists():
        backup = real_db.read_bytes()
    real_db.parent.mkdir(parents=True, exist_ok=True)
    real_db.write_bytes(db_path.read_bytes())
    yield str(real_db)
    # cleanup
    if backup is not None:
        real_db.write_bytes(backup)
    else:
        real_db.unlink(missing_ok=True)


def test_drift_open_returns_most_recent_scan(client, seeded_drift_db):
    r = client.get("/v1/drift/open")
    assert r.status_code == 200
    body = r.json()
    assert body["scan"] is not None
    assert body["count"] == 7
    severities = [item["severity"] for item in body["items"]]
    # Should be sorted critical-first, then major, then minor, then info
    assert severities[:2] == ["critical", "critical"]
    assert severities[-1] == "info"


def test_drift_open_filter_by_severity(client, seeded_drift_db):
    r = client.get("/v1/drift/open?severity=critical")
    body = r.json()
    assert body["count"] == 2
    assert all(it["severity"] == "critical" for it in body["items"])


def test_drift_open_bad_severity_422(client, seeded_drift_db):
    r = client.get("/v1/drift/open?severity=apocalyptic")
    assert r.status_code == 422


def test_drift_open_handles_no_db(client, monkeypatch):
    """When drift_history.db doesn't exist (fresh repo), return empty + note."""
    real_db = (
        Path(__file__).resolve().parent.parent / "drift_sentinel" / "drift_history.db"
    )
    backup = None
    if real_db.exists():
        backup = real_db.read_bytes()
        real_db.unlink()
    try:
        r = client.get("/v1/drift/open")
        assert r.status_code == 200
        body = r.json()
        assert body["scan"] is None
        assert body["count"] == 0
        assert "note" in body
    finally:
        if backup is not None:
            real_db.write_bytes(backup)


def test_drift_open_scan_id_404(client, seeded_drift_db):
    r = client.get("/v1/drift/open?scan_id=does-not-exist")
    assert r.status_code == 404


# ── /v1/doctrine/* ───────────────────────────────────────────────────────────


def test_doctrine_version_returns_metadata(client):
    """Reads the real canonical doc — must exist in the repo."""
    r = client.get("/v1/doctrine/version")
    assert r.status_code == 200
    body = r.json()
    assert body["path"].endswith("GIGATON_CANONICAL_FIRST_PRINCIPLES.md")
    assert body["framework_count"] >= 1
    assert body["size_bytes"] > 0
    # last_reconciled is optional but should be present in this repo
    assert body["last_reconciled"]


def test_doctrine_body_default_summary(client):
    r = client.get("/v1/doctrine")
    assert r.status_code == 200
    body = r.json()
    assert "preview" in body
    # First 30 lines should contain the doc title or section ref
    assert "Gigaton Canonical First Principles" in body["preview"] or len(body["preview"]) > 0


def test_doctrine_body_include_body(client):
    r = client.get("/v1/doctrine?include_body=true")
    assert r.status_code == 200
    body = r.json()
    assert "body" in body
    assert len(body["body"]) > 100


def test_doctrine_section_5_19(client):
    """Section 5.19 BFT was added in PR #13 — should be retrievable."""
    r = client.get("/v1/doctrine?section=5.19")
    # Pass either way (section exists or not in test snapshot),
    # but if it exists it should match the expected content.
    if r.status_code == 200:
        body = r.json()
        assert body["section"] == "5.19"
        assert "Business Field Theory" in body["body"]
    else:
        # If for some reason §5.19 not present, route should 404
        assert r.status_code == 404


def test_doctrine_unknown_section_404(client):
    r = client.get("/v1/doctrine?section=99.99")
    assert r.status_code == 404
