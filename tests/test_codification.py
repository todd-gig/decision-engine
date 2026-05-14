"""codification — proposal queue lifecycle + v0.5 readiness/cert/signoff/sweep."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.codification import (
    CodificationCertificate,
    CodificationProposal,
    DECISION_CLASS_SIGNERS,
    FOUNDER_SIGNER,
    OWNER_SIGNER,
    ProposalStatus,
    ReadinessCandidate,
    ReadinessThresholds,
    SimulationResult,
    approve_and_certify,
    approve_proposal,
    compute_readiness,
    get_certificate,
    get_proposal,
    has_quorum,
    is_authorized,
    list_certificates_for_candidate,
    list_proposals,
    load_thresholds,
    open_proposal,
    persist_certificate,
    required_signers,
    run_sweep,
)
from engine.codification.certificate import _certs_md_dir as _default_certs_md_dir
from engine.ai_router import storage as audit_storage


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "codification_proposals.db")


def _new_proposal(**kwargs) -> CodificationProposal:
    defaults = dict(
        candidate_pv="explain_recs.v1.0",
        candidate_sv="coaching_prose.v1",
        candidate_score=0.85,
        analyzer_run_at=datetime.now(tz=timezone.utc).isoformat(),
        proposed_python="def explain(recs):\n    return f'Top: {recs[0]}'",
        proposed_tests="def test_explain():\n    assert explain([{'name':'A'}])",
        why="High volume + low variance; deterministic top-rec pattern",
        sim=SimulationResult(
            n=120,
            divergence_p50=0.05,
            divergence_p90=0.12,
            cost_savings_usd=15.0,
            latency_savings_ms=8000,
        ),
    )
    defaults.update(kwargs)
    return CodificationProposal(**defaults)


def test_open_proposal_writes_row_with_status_open(tmp_db):
    p = _new_proposal()
    body = open_proposal(p, db_path=tmp_db)
    assert body["proposal_id"] == p.proposal_id
    assert body["queue_status"] == "open"

    row = get_proposal(p.proposal_id, db_path=tmp_db)
    assert row is not None
    assert row["queue_status"] == "open"
    assert row["candidate_score"] == 0.85
    assert row["sim_n"] == 120


def test_get_proposal_returns_none_for_missing(tmp_db):
    assert get_proposal("does-not-exist", db_path=tmp_db) is None


def test_list_proposals_filters_by_status(tmp_db):
    p1 = _new_proposal()
    p2 = _new_proposal()
    open_proposal(p1, db_path=tmp_db)
    open_proposal(p2, db_path=tmp_db)
    approve_proposal(
        p1.proposal_id,
        approver_user_id="todd",
        approval_why="ship — divergence acceptable",
        new_status=ProposalStatus.APPROVED_SHIP.value,
        shipped_pr_url="https://github.com/.../pull/1",
        db_path=tmp_db,
    )
    open_only = list_proposals(status="open", db_path=tmp_db)
    assert len(open_only) == 1
    assert open_only[0]["proposal_id"] == p2.proposal_id

    approved = list_proposals(status="approved_ship", db_path=tmp_db)
    assert len(approved) == 1
    assert approved[0]["proposal_id"] == p1.proposal_id


def test_approve_proposal_sets_metadata(tmp_db):
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    row = approve_proposal(
        p.proposal_id,
        approver_user_id="todd",
        approval_why="rules match observed pattern; ship as fallback",
        new_status=ProposalStatus.APPROVED_FALLBACK.value,
        db_path=tmp_db,
    )
    assert row["queue_status"] == "approved_fallback"
    assert row["approver_user_id"] == "todd"
    assert "fallback" in row["approval_why"]
    assert row["approved_at"] is not None


def test_approve_rejects_invalid_status(tmp_db):
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with pytest.raises(ValueError):
        approve_proposal(
            p.proposal_id,
            approver_user_id="x",
            approval_why="y",
            new_status="held",  # not in allowed set
            db_path=tmp_db,
        )


def test_approve_already_decided_raises(tmp_db):
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    approve_proposal(
        p.proposal_id,
        approver_user_id="todd",
        approval_why="first decision",
        new_status=ProposalStatus.APPROVED_SHIP.value,
        db_path=tmp_db,
    )
    with pytest.raises(LookupError):
        approve_proposal(
            p.proposal_id,
            approver_user_id="todd",
            approval_why="second decision should fail",
            new_status=ProposalStatus.REJECTED.value,
            db_path=tmp_db,
        )


def test_approve_unknown_id_raises(tmp_db):
    # No proposal stored; approve_proposal should raise LookupError.
    with pytest.raises(LookupError):
        approve_proposal(
            "nonexistent-id",
            approver_user_id="x",
            approval_why="y",
            new_status=ProposalStatus.REJECTED.value,
            db_path=tmp_db,
        )


def test_schema_check_constraint_enforced(tmp_db):
    """SQLite CHECK on queue_status should reject direct invalid writes."""
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE codification_proposals SET queue_status='bogus' WHERE proposal_id = ?",
                (p.proposal_id,),
            )


# ──────────────────────────────────────────────────────────────────────────
# v0.5: readiness scorer
# ──────────────────────────────────────────────────────────────────────────


def _ready_candidate(**kwargs):
    """Builder for a ReadinessCandidate that clears every doctrine floor."""
    defaults = dict(
        candidate_pv="pv.test.v1",
        candidate_sv="sv.test.v1",
        executions=200,
        exception_rate=0.02,
        stability=0.92,
        value=0.7,
        risk=0.2,
    )
    defaults.update(kwargs)
    return ReadinessCandidate(**defaults)


def test_readiness_passes_when_all_floors_clear():
    rs = compute_readiness(_ready_candidate())
    assert rs.is_ready is True
    assert rs.blockers == []
    assert rs.score >= 0.70


def test_readiness_blocks_when_executions_below_floor():
    rs = compute_readiness(_ready_candidate(executions=10))
    assert rs.is_ready is False
    assert any("executions" in b for b in rs.blockers)


def test_readiness_blocks_when_exception_rate_above_ceiling():
    rs = compute_readiness(_ready_candidate(exception_rate=0.30))
    assert rs.is_ready is False
    assert any("exception_rate" in b for b in rs.blockers)


def test_readiness_blocks_when_stability_below_floor():
    rs = compute_readiness(_ready_candidate(stability=0.5))
    assert rs.is_ready is False
    assert any("stability" in b for b in rs.blockers)


def test_readiness_edge_exactly_at_floors_no_hard_block():
    """Doctrine floors are inclusive — exactly-at clears the hard gates.

    A candidate that *just* meets the floors won't always clear the
    composite score_threshold (volume credit is low at the floor); that's
    by design — the composite score caps acceptance, not the gates.
    """
    rs = compute_readiness(_ready_candidate(
        executions=50, exception_rate=0.05, stability=0.80,
    ))
    assert rs.blockers == []


def test_readiness_just_below_each_floor_blocks():
    rs = compute_readiness(_ready_candidate(executions=49))
    assert "executions" in " ".join(rs.blockers)

    rs = compute_readiness(_ready_candidate(exception_rate=0.0501))
    assert "exception_rate" in " ".join(rs.blockers)

    rs = compute_readiness(_ready_candidate(stability=0.7999))
    assert "stability" in " ".join(rs.blockers)


def test_readiness_component_breakdown_returned():
    rs = compute_readiness(_ready_candidate())
    for key in ("volume_norm", "exception_inv", "stability", "value", "risk_inv"):
        assert key in rs.components
        assert 0.0 <= rs.components[key] <= 1.0


def test_readiness_thresholds_loadable_from_yaml(tmp_path):
    """load_thresholds() reads the codification.readiness block."""
    yaml_text = """
codification:
  readiness:
    min_executions: 100
    max_exception_rate: 0.03
    min_stability: 0.85
    score_threshold: 0.80
    weights:
      volume: 0.40
      exception_inv: 0.30
      stability: 0.20
      value: 0.05
      risk_inv: 0.05
"""
    p = tmp_path / "engine.yaml"
    p.write_text(yaml_text)
    th = load_thresholds(str(p))
    assert th.min_executions == 100
    assert th.max_exception_rate == pytest.approx(0.03)
    assert th.min_stability == pytest.approx(0.85)
    assert th.score_threshold == pytest.approx(0.80)
    assert th.weight_volume == pytest.approx(0.40)


def test_readiness_uses_doctrine_defaults_when_yaml_missing(tmp_path):
    th = load_thresholds(str(tmp_path / "does_not_exist.yaml"))
    assert th.min_executions == 50
    assert th.max_exception_rate == pytest.approx(0.05)
    assert th.min_stability == pytest.approx(0.80)


def test_readiness_score_clamped_when_weights_dont_sum_to_one():
    """Operator may tune weights off-1.0; scorer normalizes so score stays in [0,1]."""
    th = ReadinessThresholds(
        weight_volume=0.6, weight_exception_inv=0.6, weight_stability=0.6,
        weight_value=0.6, weight_risk_inv=0.6,
        score_threshold=0.5,
    )
    rs = compute_readiness(_ready_candidate(), thresholds=th)
    assert 0.0 <= rs.score <= 1.0


# ──────────────────────────────────────────────────────────────────────────
# v0.5: CodificationCertificate
# ──────────────────────────────────────────────────────────────────────────


def _new_cert(**overrides) -> CodificationCertificate:
    defaults = dict(
        candidate_id=str(uuid.uuid4()),
        signers=[FOUNDER_SIGNER],
        decision_class="new-module",
        reasoning="Stable Claude pattern: pricing extraction observed across 500+ executions with deterministic outputs.",
        evidence_decision_ids=["DEC-001", "DEC-002", "DEC-003"],
        proposed_spec="def extract_pricing(text):\n    return regex_extract(text)",
        prompt_version="pricing.v3.2",
        schema_version="pricing.schema.v2",
    )
    defaults.update(overrides)
    return CodificationCertificate(**defaults)


def test_certificate_validate_requires_reasoning_min_length():
    with pytest.raises(ValueError, match="reasoning"):
        _new_cert(reasoning="too short").validate()


def test_certificate_validate_rejects_empty_reasoning():
    with pytest.raises(ValueError, match="reasoning"):
        _new_cert(reasoning="").validate()


def test_certificate_validate_requires_at_least_one_signer():
    with pytest.raises(ValueError, match="signer"):
        _new_cert(signers=[]).validate()


def test_certificate_validate_rejects_blank_signer_string():
    with pytest.raises(ValueError, match="signer"):
        _new_cert(signers=["", "  "]).validate()


def test_certificate_sign_then_verify_roundtrip():
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    assert cert.hmac
    assert cert.verify(secret_key="test-secret") is True


def test_certificate_verify_fails_with_wrong_secret():
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    assert cert.verify(secret_key="different-secret") is False


def test_certificate_tamper_detection_on_reasoning():
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    original_hmac = cert.hmac
    # Mutate after signing
    cert.reasoning = "Tampered reasoning that was substituted post-signing event ok"
    # HMAC still old value; verify recomputes and notices mismatch.
    assert cert.verify(secret_key="test-secret") is False
    assert cert.hmac == original_hmac  # didn't auto-update


def test_certificate_tamper_detection_on_spec():
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    cert.proposed_spec = "def malicious(text):\n    return 'evil'"
    assert cert.verify(secret_key="test-secret") is False


def test_certificate_tamper_detection_on_signers():
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    cert.signers = [FOUNDER_SIGNER, "intruder@example.com"]
    assert cert.verify(secret_key="test-secret") is False


def test_certificate_persist_writes_row_and_md(tmp_db, tmp_path, monkeypatch):
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    md_dir = tmp_path / "certs"
    persist_certificate(cert, db_path=tmp_db, md_dir=md_dir)

    # Row exists
    fetched = get_certificate(cert.id, db_path=tmp_db)
    assert fetched is not None
    assert fetched.id == cert.id
    assert fetched.hmac == cert.hmac
    assert fetched.candidate_id == cert.candidate_id
    assert FOUNDER_SIGNER in fetched.signers

    # MD file exists with frontmatter
    md_files = list(md_dir.glob("*.md"))
    assert len(md_files) == 1
    text = md_files[0].read_text()
    assert f"id: {cert.id}" in text
    assert f"hmac: {cert.hmac}" in text
    assert "## Reasoning (WHY)" in text


def test_certificate_persist_refuses_unsigned():
    cert = _new_cert()
    with pytest.raises(ValueError, match="signed"):
        persist_certificate(cert)


def test_certificate_md_file_match_detects_tamper(tmp_db, tmp_path):
    cert = _new_cert()
    cert.sign(secret_key="test-secret")
    persist_certificate(cert, db_path=tmp_db, md_dir=tmp_path / "certs")
    assert cert.md_file_exists()
    assert cert.md_file_matches()
    # Now tamper with the file on disk
    p = Path(cert.md_path)
    text = p.read_text()
    p.write_text(text.replace(cert.hmac, "0" * 64))
    assert cert.md_file_matches() is False


def test_certificate_list_for_candidate_returns_all_signed(tmp_db, tmp_path):
    candidate_id = str(uuid.uuid4())
    c1 = _new_cert(candidate_id=candidate_id)
    c1.sign(secret_key="k")
    persist_certificate(c1, db_path=tmp_db, md_dir=tmp_path / "certs")
    c2 = _new_cert(candidate_id=candidate_id, reasoning="Second cert with sufficiently long reasoning text here for validation.")
    c2.sign(secret_key="k")
    persist_certificate(c2, db_path=tmp_db, md_dir=tmp_path / "certs")
    certs = list_certificates_for_candidate(candidate_id, db_path=tmp_db)
    assert len(certs) == 2


# ──────────────────────────────────────────────────────────────────────────
# v0.5: sign-off routing
# ──────────────────────────────────────────────────────────────────────────


def test_signoff_new_module_requires_founder():
    assert required_signers("new-module") == [FOUNDER_SIGNER]


def test_signoff_tuning_requires_owner():
    assert required_signers("tuning") == [OWNER_SIGNER]


def test_signoff_doctrine_touching_requires_both():
    sigs = required_signers("doctrine-touching")
    assert FOUNDER_SIGNER in sigs
    assert OWNER_SIGNER in sigs
    assert len(sigs) == 2


def test_signoff_unknown_class_defaults_to_founder_conservative():
    assert required_signers("frobnicate") == [FOUNDER_SIGNER]


def test_signoff_is_authorized_case_insensitive():
    assert is_authorized("TODD@gigaton.AI", "new-module") is True
    assert is_authorized("matt@gigaton.ai", "new-module") is False


def test_signoff_is_authorized_rejects_empty():
    assert is_authorized("", "new-module") is False


def test_signoff_quorum_doctrine_touching_needs_both():
    assert has_quorum([FOUNDER_SIGNER], "doctrine-touching") is False
    assert has_quorum([FOUNDER_SIGNER, OWNER_SIGNER], "doctrine-touching") is True


def test_signoff_quorum_new_module_single_signer_ok():
    assert has_quorum([FOUNDER_SIGNER], "new-module") is True
    assert has_quorum([OWNER_SIGNER], "new-module") is False


# ──────────────────────────────────────────────────────────────────────────
# v0.5: approve_and_certify (auth + cert mint, end-to-end)
# ──────────────────────────────────────────────────────────────────────────


def test_approve_and_certify_happy_path(tmp_db, tmp_path, monkeypatch):
    # Redirect MD files into tmp_path so we don't pollute the worktree.
    monkeypatch.setattr(
        "engine.codification.certificate._certs_md_dir",
        lambda: tmp_path / "certs",
    )
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    result = approve_and_certify(
        p.proposal_id,
        approver_user_id=FOUNDER_SIGNER,
        approval_why="Ship as deterministic replacement; observed 500 stable executions over 60 days.",
        new_status=ProposalStatus.APPROVED_SHIP.value,
        decision_class="new-module",
        evidence_decision_ids=["DEC-100", "DEC-101"],
        proposed_spec="def codified(x): return x.upper()",
        prompt_version="pv.test.v1",
        schema_version="sv.test.v1",
        db_path=tmp_db,
        secret_key="test-secret",
    )
    assert result["queue_status"] == "approved_ship"
    assert "certificate" in result
    cert_id = result["certificate"]["id"]
    cert = get_certificate(cert_id, db_path=tmp_db)
    assert cert is not None
    assert cert.verify(secret_key="test-secret")


def test_approve_and_certify_rejects_unauthorized_approver(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "engine.codification.certificate._certs_md_dir",
        lambda: tmp_path / "certs",
    )
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with pytest.raises(PermissionError):
        approve_and_certify(
            p.proposal_id,
            approver_user_id="random@example.com",
            approval_why="Trying to bypass the signoff matrix completely without auth.",
            new_status=ProposalStatus.APPROVED_SHIP.value,
            decision_class="new-module",
            evidence_decision_ids=[],
            proposed_spec="x",
            prompt_version="v",
            schema_version="v",
            db_path=tmp_db,
            secret_key="k",
        )


def test_approve_and_certify_rejects_wrong_signer_for_tuning(tmp_db, tmp_path, monkeypatch):
    """new-module signer (founder) cannot approve a tuning-class proposal."""
    monkeypatch.setattr(
        "engine.codification.certificate._certs_md_dir",
        lambda: tmp_path / "certs",
    )
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with pytest.raises(PermissionError):
        approve_and_certify(
            p.proposal_id,
            approver_user_id=FOUNDER_SIGNER,
            approval_why="Founder trying to approve a tuning-class change unilaterally.",
            new_status=ProposalStatus.APPROVED_SHIP.value,
            decision_class="tuning",
            evidence_decision_ids=[],
            proposed_spec="x",
            prompt_version="v",
            schema_version="v",
            db_path=tmp_db,
            secret_key="k",
        )


def test_approve_and_certify_doctrine_touching_needs_both_signers(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "engine.codification.certificate._certs_md_dir",
        lambda: tmp_path / "certs",
    )
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    # Founder alone is in the required set but cannot satisfy quorum for doctrine-touching.
    with pytest.raises(PermissionError):
        approve_and_certify(
            p.proposal_id,
            approver_user_id=FOUNDER_SIGNER,
            approval_why="Doctrine-touching change attempted with only one of two signers present.",
            new_status=ProposalStatus.APPROVED_SHIP.value,
            decision_class="doctrine-touching",
            evidence_decision_ids=[],
            proposed_spec="x",
            prompt_version="v",
            schema_version="v",
            additional_signers=[],   # missing co-signer
            db_path=tmp_db,
            secret_key="k",
        )

    # With the co-signer it succeeds.
    p2 = _new_proposal()
    open_proposal(p2, db_path=tmp_db)
    result = approve_and_certify(
        p2.proposal_id,
        approver_user_id=FOUNDER_SIGNER,
        approval_why="Doctrine-touching change with both founder and owner co-signing as required.",
        new_status=ProposalStatus.APPROVED_SHIP.value,
        decision_class="doctrine-touching",
        evidence_decision_ids=["D1"],
        proposed_spec="x",
        prompt_version="v",
        schema_version="v",
        additional_signers=[OWNER_SIGNER],
        db_path=tmp_db,
        secret_key="k",
    )
    assert sorted(result["certificate"]["signers"]) == sorted([FOUNDER_SIGNER, OWNER_SIGNER])


def test_approve_and_certify_rejects_short_reasoning(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "engine.codification.certificate._certs_md_dir",
        lambda: tmp_path / "certs",
    )
    p = _new_proposal()
    open_proposal(p, db_path=tmp_db)
    with pytest.raises(ValueError, match="reasoning"):
        approve_and_certify(
            p.proposal_id,
            approver_user_id=FOUNDER_SIGNER,
            approval_why="too short",  # <20 chars
            new_status=ProposalStatus.APPROVED_SHIP.value,
            decision_class="new-module",
            evidence_decision_ids=[],
            proposed_spec="x",
            prompt_version="v",
            schema_version="v",
            db_path=tmp_db,
            secret_key="k",
        )


def test_approve_and_certify_rejects_invalid_status_for_certification():
    """REJECTED should go through plain approve_proposal, not approve_and_certify."""
    with pytest.raises(ValueError, match="APPROVED"):
        approve_and_certify(
            "any-id",
            approver_user_id=FOUNDER_SIGNER,
            approval_why="Reasoning long enough to satisfy the validation rule.",
            new_status=ProposalStatus.REJECTED.value,
            decision_class="new-module",
            evidence_decision_ids=[],
            proposed_spec="x",
            prompt_version="v",
            schema_version="v",
        )


# ──────────────────────────────────────────────────────────────────────────
# v0.5: sweep end-to-end on synthetic audit table
# ──────────────────────────────────────────────────────────────────────────


def _seed_llm_audit_rows(db_path: str, n: int, pv: str, sv: str, *, in_chars=200, out_chars=300):
    """Seed `n` synthetic llm_audit rows for (pv, sv) so analyzer picks them up."""
    conn = audit_storage.get_connection(db_path)
    try:
        for i in range(n):
            conn.execute(
                """
                INSERT INTO llm_audit (
                    audit_id, invoked_at, caller_engine, caller_function,
                    provider_requested, provider_used, model_requested, model_used,
                    prompt_version, schema_version, in_chars, out_chars,
                    in_tokens, out_tokens, cost_usd, latency_ms,
                    fallback_chain_taken, audit_metadata, error,
                    prompt_hash, response_hash, audit_signature
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"AUD-{pv}-{i}",
                    datetime.now(tz=timezone.utc).isoformat(),
                    "test_engine", "test_fn",
                    "anthropic", "anthropic",
                    "claude-3-5", "claude-3-5",
                    pv, sv,
                    in_chars, out_chars,
                    50, 75, 0.001, 200,
                    "[]", "{}", None,
                    "phash", "rhash", "sig",
                ),
            )
    finally:
        conn.close()


def test_sweep_opens_proposals_for_ready_candidates(tmp_path):
    """End-to-end: analyzer finds a candidate, readiness clears, proposal opens."""
    audit_db = str(tmp_path / "llm_audit.db")
    proposals_db = str(tmp_path / "proposals.db")
    # Two PV/SV groups so ecosystem_mean isn't degenerate.
    _seed_llm_audit_rows(audit_db, n=120, pv="codifiable.v1", sv="cs.v1")
    _seed_llm_audit_rows(audit_db, n=80, pv="other.v1", sv="cs.v1", in_chars=100, out_chars=400)

    # Loose thresholds so the synthetic data can clear readiness:
    # exception_rate/stability/risk all come from response_variance which is
    # very low for uniform synthetic rows.
    th = ReadinessThresholds(
        min_executions=50,
        max_exception_rate=0.5,
        min_stability=0.40,
        score_threshold=0.30,
    )
    report = run_sweep(
        min_volume=50,
        score_threshold=0.0,
        audit_db_path=audit_db,
        proposals_db_path=proposals_db,
        thresholds=th,
        why="end-to-end test sweep",
    )
    assert report.candidates_seen >= 1
    assert report.candidates_ready >= 1
    assert report.proposals_opened >= 1
    # Proposals are visible via the standard queue listing.
    proposals = list_proposals(db_path=proposals_db)
    assert len(proposals) == report.proposals_opened


def test_sweep_returns_empty_report_when_no_audit_data(tmp_path):
    audit_db = str(tmp_path / "empty_audit.db")
    proposals_db = str(tmp_path / "proposals.db")
    # Touch the audit DB so analyzer's connection succeeds but the table is empty.
    audit_storage.get_connection(audit_db).close()
    report = run_sweep(
        min_volume=50,
        audit_db_path=audit_db,
        proposals_db_path=proposals_db,
    )
    assert report.candidates_seen == 0
    assert report.candidates_ready == 0
    assert report.proposals_opened == 0


def test_sweep_skips_proposals_when_open_proposals_false(tmp_path):
    audit_db = str(tmp_path / "llm_audit.db")
    proposals_db = str(tmp_path / "proposals.db")
    _seed_llm_audit_rows(audit_db, n=120, pv="x.v1", sv="x.s1")
    _seed_llm_audit_rows(audit_db, n=80, pv="y.v1", sv="y.s1", in_chars=150, out_chars=300)
    th = ReadinessThresholds(
        min_executions=50, max_exception_rate=0.5, min_stability=0.4,
        score_threshold=0.30,
    )
    report = run_sweep(
        min_volume=50, score_threshold=0.0,
        audit_db_path=audit_db, proposals_db_path=proposals_db,
        thresholds=th, open_proposals=False,
    )
    assert report.candidates_seen >= 1
    assert report.proposals_opened == 0
    assert list_proposals(db_path=proposals_db) == []


def test_sweep_carries_version_metadata(tmp_path):
    """Every sweep report must report its own prompt/schema version."""
    audit_db = str(tmp_path / "empty.db")
    proposals_db = str(tmp_path / "proposals.db")
    audit_storage.get_connection(audit_db).close()
    report = run_sweep(audit_db_path=audit_db, proposals_db_path=proposals_db)
    assert report.prompt_version
    assert report.schema_version
    assert "codification_sweep" in report.prompt_version
