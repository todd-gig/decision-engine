"""FastAPI route tests for /v1/overrides + /v1/proposals + /v1/codification/analyze.

Routes wrap the engine.human_override + engine.codification + analyzer
modules. Default SQLite paths are isolated to a tmp directory per test
via monkeypatch on the storage modules' default-path resolvers.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from engine.ai_router import storage as audit_storage
from engine.codification import storage as codification_storage
from engine.human_override import storage as override_storage


@pytest.fixture
def isolated_dbs(tmp_path: Path, monkeypatch):
    """Point all three SQLite stores at tmp_path so tests don't bleed into each other."""
    audit_db = tmp_path / "llm_audit.db"
    codification_db = tmp_path / "codification_proposals.db"
    override_db = tmp_path / "human_overrides.db"

    monkeypatch.setattr(audit_storage, "_default_db_path", lambda: audit_db)
    monkeypatch.setattr(codification_storage, "_default_db_path", lambda: codification_db)
    monkeypatch.setattr(override_storage, "_default_db_path", lambda: override_db)
    yield {
        "audit": str(audit_db),
        "codification": str(codification_db),
        "override": str(override_db),
    }


@pytest.fixture
def client(isolated_dbs):
    return TestClient(app)


# ── Overrides ────────────────────────────────────────────────────────────────


def _override_payload(**overrides) -> dict:
    base = {
        "decision_id": "DEC-1234",
        "decision_certificate_id": "EC-1234",
        "override_type": "reversal",
        "overridden_by_user_id": "user-uuid",
        "overridden_at": datetime.now(tz=timezone.utc).isoformat(),
        "source_engine": "sales-os",
        "surface": "operator_dashboard:opportunity_detail",
        "original_action": "auto_send_proposal",
        "override_action": "hold_for_review",
        "user_reasoning": "pricing exceeded client budget",
    }
    base.update(overrides)
    return base


def test_overrides_record_202(client):
    r = client.post("/v1/overrides", json=_override_payload())
    assert r.status_code == 202
    body = r.json()
    assert body["override_type"] == "reversal"
    assert body["classification"]["ovs_weight"] == 3.0


def test_overrides_record_unknown_type_422(client):
    r = client.post("/v1/overrides", json=_override_payload(override_type="bogus"))
    assert r.status_code == 422


def test_overrides_get_one(client):
    r1 = client.post("/v1/overrides", json=_override_payload())
    oid = r1.json()["override_id"]
    r2 = client.get(f"/v1/overrides/{oid}")
    assert r2.status_code == 200
    assert r2.json()["override_id"] == oid


def test_overrides_get_404(client):
    r = client.get("/v1/overrides/nope")
    assert r.status_code == 404


def test_overrides_list_filters(client):
    client.post("/v1/overrides", json=_override_payload(decision_id="A", source_engine="alpha"))
    client.post("/v1/overrides", json=_override_payload(decision_id="B", source_engine="beta"))
    r = client.get("/v1/overrides?source_engine=alpha")
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["decision_id"] == "A"
    assert body["filter"]["source_engine"] == "alpha"


def test_overrides_list_user_filter(client):
    client.post("/v1/overrides", json=_override_payload(overridden_by_user_id="user-A"))
    client.post("/v1/overrides", json=_override_payload(overridden_by_user_id="user-B"))
    r = client.get("/v1/overrides?user_id=user-A")
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["overridden_by_user_id"] == "user-A"


# ── Proposals ────────────────────────────────────────────────────────────────


def _proposal_payload(**overrides) -> dict:
    base = {
        "candidate_pv": "explain_recs.v1.0",
        "candidate_sv": "coaching_prose.v1",
        "candidate_score": 0.85,
        "analyzer_run_at": datetime.now(tz=timezone.utc).isoformat(),
        "proposed_python": "def f(): return 1",
        "proposed_tests": "def test_f(): assert f() == 1",
        "why": "high volume + low variance",
        "sim": {
            "n": 120,
            "divergence_p50": 0.05,
            "divergence_p90": 0.12,
            "cost_savings_usd": 15.0,
            "latency_savings_ms": 8000,
        },
    }
    base.update(overrides)
    return base


def test_proposals_open_201(client):
    r = client.post("/v1/proposals", json=_proposal_payload())
    assert r.status_code == 201
    assert r.json()["queue_status"] == "open"


def test_proposals_score_must_be_in_unit_interval(client):
    r = client.post("/v1/proposals", json=_proposal_payload(candidate_score=1.5))
    assert r.status_code == 422


def test_proposals_get(client):
    r1 = client.post("/v1/proposals", json=_proposal_payload())
    pid = r1.json()["proposal_id"]
    r2 = client.get(f"/v1/proposals/{pid}")
    assert r2.status_code == 200
    assert r2.json()["proposal_id"] == pid


def test_proposals_get_404(client):
    r = client.get("/v1/proposals/nope")
    assert r.status_code == 404


def test_proposals_list_status_filter(client):
    r1 = client.post("/v1/proposals", json=_proposal_payload())
    pid = r1.json()["proposal_id"]
    client.post(f"/v1/proposals/{pid}/approve", json={
        "approver_user_id": "todd",
        "approval_why": "ship",
        "new_status": "approved_ship",
        "shipped_pr_url": "https://github.com/.../pull/1",
    })

    open_only = client.get("/v1/proposals?status=open").json()
    assert open_only["count"] == 0
    approved = client.get("/v1/proposals?status=approved_ship").json()
    assert approved["count"] == 1


def test_proposals_approve_404_for_unknown(client):
    r = client.post("/v1/proposals/nope/approve", json={
        "approver_user_id": "x",
        "approval_why": "y",
        "new_status": "rejected",
    })
    assert r.status_code == 404


def test_proposals_approve_422_for_invalid_status(client):
    r1 = client.post("/v1/proposals", json=_proposal_payload())
    pid = r1.json()["proposal_id"]
    r = client.post(f"/v1/proposals/{pid}/approve", json={
        "approver_user_id": "x",
        "approval_why": "y",
        "new_status": "held",  # not in allowed enum
    })
    assert r.status_code == 422


# ── Analyzer ─────────────────────────────────────────────────────────────────


def _seed_audit(audit_db: str, pv: str, sv: str, n: int, *, caller_engine="test"):
    """Seed N synthetic audit rows."""
    from engine.ai_router import audit as audit_mod
    from engine.ai_router import storage as st
    conn = st.get_connection(audit_db)
    try:
        for i in range(n):
            row = {
                "audit_id": f"{pv}-{i:04d}",
                "invoked_at": "2026-05-13T00:00:00Z",
                "caller_engine": caller_engine,
                "caller_function": "test_fn",
                "provider_requested": "anthropic",
                "provider_used": "anthropic",
                "model_requested": "claude-opus-4-7",
                "model_used": "claude-opus-4-7",
                "prompt_version": pv,
                "schema_version": sv,
                "in_chars": 100 + i,
                "out_chars": 200 + (i % 7) * 5,  # low variance
                "in_tokens": 25,
                "out_tokens": 50,
                "cost_usd": 0.0010,
                "latency_ms": 1000,
                "fallback_chain_taken": [],
                "audit_metadata": None,
                "error": None,
                "prompt_hash": audit_mod.hash_text(f"p-{i}"),
                "response_hash": audit_mod.hash_text(f"r-{i}"),
            }
            row["audit_signature"] = audit_mod.sign(row)
            st.insert_audit(conn, row)
    finally:
        conn.close()


def test_analyze_empty_returns_no_candidates(client):
    r = client.post("/v1/codification/analyze", json={
        "min_volume": 10,
        "score_threshold": 0.5,
        "open_top_n_as_proposals": 0,
    })
    assert r.status_code == 200
    assert r.json()["candidate_count"] == 0


def test_analyze_finds_high_volume_candidate(client, isolated_dbs):
    # Seed 150 rows of one pv/sv pair
    _seed_audit(isolated_dbs["audit"], pv="hot.v1", sv="schema.v1", n=150)
    r = client.post("/v1/codification/analyze", json={
        "min_volume": 100,
        "score_threshold": 0.4,
        "open_top_n_as_proposals": 0,
        "audit_db_path": isolated_dbs["audit"],
    })
    body = r.json()
    assert body["candidate_count"] >= 1
    top = body["candidates"][0]
    assert top["candidate_pv"] == "hot.v1"
    assert top["volume"] == 150


def test_analyze_opens_proposals_on_request(client, isolated_dbs):
    _seed_audit(isolated_dbs["audit"], pv="hot.v1", sv="schema.v1", n=200)
    r = client.post("/v1/codification/analyze", json={
        "min_volume": 100,
        "score_threshold": 0.4,
        "open_top_n_as_proposals": 1,
        "audit_db_path": isolated_dbs["audit"],
        "proposals_db_path": isolated_dbs["codification"],
        "why": "test analyzer auto-open",
    })
    body = r.json()
    assert body["proposals_opened_count"] == 1
    assert body["proposals_opened"][0]["queue_status"] == "open"
