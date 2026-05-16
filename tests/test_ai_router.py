"""ai_router — invoke() with audit envelope, provider routing, fallback.

Anthropic provider is mocked so tests run without an SDK / API key.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ai_router import invoke, InvokeResult, ProviderUnavailable
from engine.ai_router import audit, storage
from engine.ai_router.providers import ProviderResponse
from engine.ai_router.providers import anthropic as _anthropic_mod


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "llm_audit.db")


@pytest.fixture(autouse=True)
def _stable_hmac_key(monkeypatch):
    monkeypatch.setenv("LLM_AUDIT_HMAC_KEY", "test-hmac-key")
    monkeypatch.delenv("AI_ROUTER_DISABLE_ANTHROPIC", raising=False)
    monkeypatch.delenv("AI_ROUTER_DISABLE_OPENAI", raising=False)
    monkeypatch.delenv("AI_ROUTER_DISABLE_GEMINI", raising=False)
    yield


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Force anthropic provider to be 'available' and return canned text.

    Signature mirrors the real `call(...)` — including required
    prompt_version + schema_version (CRIT-003).
    """
    calls: list[dict] = []

    def fake_call(
        *, prompt, model, prompt_version, schema_version,
        max_tokens=1024, temperature=0.0, timeout_seconds=30,
    ):
        calls.append({
            "prompt": prompt, "model": model,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
        })
        return ProviderResponse(
            text=f"echo:{prompt}",
            model_used=model,
            in_tokens=10,
            out_tokens=20,
        )
    monkeypatch.setattr(_anthropic_mod, "is_available", lambda: True)
    monkeypatch.setattr(_anthropic_mod, "call", fake_call)
    fake_call.calls = calls  # type: ignore[attr-defined]
    yield fake_call


def _count_audit_rows(db_path: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM llm_audit").fetchone()[0]


def _read_audit_row(db_path: str) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM llm_audit LIMIT 1").fetchone()
        return dict(row)


def test_invoke_success_writes_audit_row(fake_anthropic, tmp_db):
    result = invoke(
        prompt="hello",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="test.v1",
        schema_version="test_schema.v1",
        caller_engine="test",
        caller_function="test_invoke_success",
        db_path=tmp_db,
    )
    assert isinstance(result, InvokeResult)
    assert result.text == "echo:hello"
    assert result.provider_used == "anthropic"
    assert result.model_used == "claude-opus-4-7"
    assert result.in_tokens == 10
    assert result.out_tokens == 20
    assert result.cost_usd is not None and result.cost_usd > 0
    assert result.audit_id  # set
    assert _count_audit_rows(tmp_db) == 1


def test_invoke_audit_signature_verifies(fake_anthropic, tmp_db):
    invoke(
        prompt="signed-test",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="t.v1",
        schema_version="ts.v1",
        caller_engine="test",
        caller_function="f",
        db_path=tmp_db,
    )
    row = _read_audit_row(tmp_db)
    # Reconstruct dict with json-decoded fields where needed
    import json as _json
    row["fallback_chain_taken"] = _json.loads(row["fallback_chain_taken"])
    if row.get("audit_metadata"):
        row["audit_metadata"] = _json.loads(row["audit_metadata"])
    assert audit.verify(row)


def test_invoke_audit_signature_tamper_detected(fake_anthropic, tmp_db):
    invoke(
        prompt="tamper-test",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="t.v1",
        schema_version="ts.v1",
        caller_engine="test",
        caller_function="f",
        db_path=tmp_db,
    )
    row = _read_audit_row(tmp_db)
    import json as _json
    row["fallback_chain_taken"] = _json.loads(row["fallback_chain_taken"])
    # Tamper: change prompt_version
    row["prompt_version"] = "tampered.v1"
    assert not audit.verify(row)


def test_invoke_records_hashes_not_full_text(fake_anthropic, tmp_db):
    invoke(
        prompt="secret-prompt-do-not-leak",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="t.v1",
        schema_version="ts.v1",
        caller_engine="test",
        caller_function="f",
        db_path=tmp_db,
    )
    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT * FROM llm_audit")
        names = [d[0] for d in cur.description]
        row = cur.fetchone()
        cells = dict(zip(names, row))
    # Full prompt + response not stored
    for cell in cells.values():
        if isinstance(cell, str):
            assert "secret-prompt-do-not-leak" not in cell
    # Hash IS stored
    assert cells["prompt_hash"] == audit.hash_text("secret-prompt-do-not-leak")


def test_invoke_failure_raises_provider_unavailable(monkeypatch, tmp_db):
    """When no provider is available, raise ProviderUnavailable + write audit row."""
    monkeypatch.setattr(_anthropic_mod, "is_available", lambda: False)
    with pytest.raises(ProviderUnavailable):
        invoke(
            prompt="x",
            provider="anthropic",
            model="claude-opus-4-7",
            prompt_version="t.v1",
            schema_version="ts.v1",
            caller_engine="test",
            caller_function="f",
            db_path=tmp_db,
        )
    # Audit row still written (with error field set)
    assert _count_audit_rows(tmp_db) == 1
    row = _read_audit_row(tmp_db)
    assert row["error"]
    assert row["provider_used"] == ""


def test_kill_switch_disables_provider(monkeypatch, fake_anthropic, tmp_db):
    monkeypatch.setenv("AI_ROUTER_DISABLE_ANTHROPIC", "1")
    with pytest.raises(ProviderUnavailable):
        invoke(
            prompt="x",
            provider="anthropic",
            model="claude-opus-4-7",
            prompt_version="t.v1",
            schema_version="ts.v1",
            caller_engine="test",
            caller_function="f",
            db_path=tmp_db,
        )


def test_fallback_chain_skips_unavailable_then_uses_next(monkeypatch, fake_anthropic, tmp_db):
    """First provider unavailable, second succeeds → audit shows the chain."""
    # Disable openai (which is anyway always unavailable in v0); request openai
    # first with anthropic as fallback.
    result = invoke(
        prompt="chain-test",
        provider="openai",
        model="gpt-5",
        prompt_version="t.v1",
        schema_version="ts.v1",
        caller_engine="test",
        caller_function="f",
        fallback_chain=["openai", "anthropic"],
        db_path=tmp_db,
    )
    # Anthropic actually served it (using gpt-5 model name — that's intentional;
    # the router doesn't translate model names across providers in v0)
    assert result.provider_used == "anthropic"
    chain = result.fallback_chain_taken
    assert chain[0]["provider"] == "openai"
    assert chain[0]["outcome"] == "unavailable"
    assert chain[1]["provider"] == "anthropic"
    assert chain[1]["outcome"] == "success"


def test_invoke_with_audit_metadata(fake_anthropic, tmp_db):
    invoke(
        prompt="x",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="t.v1",
        schema_version="ts.v1",
        caller_engine="test",
        caller_function="f",
        audit_metadata={"user_id": "u-123", "decision_id": "DEC-456"},
        db_path=tmp_db,
    )
    row = _read_audit_row(tmp_db)
    import json as _json
    meta = _json.loads(row["audit_metadata"])
    assert meta["user_id"] == "u-123"
    assert meta["decision_id"] == "DEC-456"


def test_cost_accounting_zero_when_tokens_unknown(monkeypatch, tmp_db):
    def fake_call_no_tokens(
        *, prompt, model, prompt_version, schema_version,
        max_tokens=1024, temperature=0.0, timeout_seconds=30,
    ):
        return ProviderResponse(text="ok", model_used=model, in_tokens=None, out_tokens=None)
    monkeypatch.setattr(_anthropic_mod, "is_available", lambda: True)
    monkeypatch.setattr(_anthropic_mod, "call", fake_call_no_tokens)
    result = invoke(
        prompt="x", provider="anthropic", model="claude-opus-4-7",
        prompt_version="t.v1", schema_version="ts.v1",
        caller_engine="t", caller_function="f", db_path=tmp_db,
    )
    assert result.cost_usd is None


def test_anthropic_pricing_increases_with_model_tier(fake_anthropic, tmp_db):
    """Sanity check: opus > sonnet > haiku for both in/out per-1K rates."""
    opus = _anthropic_mod.PRICING["claude-opus-4-7"]
    sonnet = _anthropic_mod.PRICING["claude-sonnet-4-6"]
    haiku = _anthropic_mod.PRICING["claude-haiku-4-5"]
    assert opus["in_per_1k"] > sonnet["in_per_1k"] > haiku["in_per_1k"]
    assert opus["out_per_1k"] > sonnet["out_per_1k"] > haiku["out_per_1k"]


def test_invoke_rejects_unknown_provider(fake_anthropic, tmp_db):
    """Asking for a provider not in _PROVIDERS → ProviderUnavailable."""
    with pytest.raises(ProviderUnavailable):
        invoke(
            prompt="x",
            provider="madeupprovider",
            model="anything",
            prompt_version="t.v1", schema_version="ts.v1",
            caller_engine="t", caller_function="f", db_path=tmp_db,
        )


# ---------------------------------------------------------------------------
# CRIT-003 enforcement at the Anthropic provider boundary.
# The chokepoint cannot drift on the rule it enforces — prompt_version +
# schema_version must propagate from invoke() into providers.anthropic.call()
# and from there into the audit row.
# ---------------------------------------------------------------------------

def test_anthropic_provider_receives_prompt_and_schema_version(fake_anthropic, tmp_db):
    """invoke() must propagate prompt_version + schema_version into providers.anthropic.call()."""
    invoke(
        prompt="hello",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="pv.alpha",
        schema_version="sv.beta",
        caller_engine="test",
        caller_function="f",
        db_path=tmp_db,
    )
    assert len(fake_anthropic.calls) == 1
    last = fake_anthropic.calls[-1]
    assert last["prompt_version"] == "pv.alpha"
    assert last["schema_version"] == "sv.beta"


def test_anthropic_provider_records_prompt_and_schema_version_in_audit(fake_anthropic, tmp_db):
    """The audit row written for an anthropic call records both versioning fields."""
    invoke(
        prompt="hello",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_version="pv.audit",
        schema_version="sv.audit",
        caller_engine="test",
        caller_function="f",
        db_path=tmp_db,
    )
    row = _read_audit_row(tmp_db)
    assert row["prompt_version"] == "pv.audit"
    assert row["schema_version"] == "sv.audit"


def test_anthropic_provider_rejects_missing_prompt_version():
    """providers.anthropic.call(prompt_version="") must raise — no silent default."""
    with pytest.raises(ValueError, match="prompt_version"):
        _anthropic_mod.call(
            prompt="x",
            model="claude-opus-4-7",
            prompt_version="",
            schema_version="sv.v1",
        )


def test_anthropic_provider_rejects_missing_schema_version():
    """providers.anthropic.call(schema_version="") must raise — no silent default."""
    with pytest.raises(ValueError, match="schema_version"):
        _anthropic_mod.call(
            prompt="x",
            model="claude-opus-4-7",
            prompt_version="pv.v1",
            schema_version="",
        )
