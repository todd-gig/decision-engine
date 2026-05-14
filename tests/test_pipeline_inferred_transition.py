"""Pipeline-level integration tests for HME inferred-transition emission.

Verifies the agentic-loop closure end-to-end via the pipeline entrypoint:
when `process_decision` produces an AUTO_EXECUTE verdict AND the decision
references an initiative UUID, exactly one POST is fired to HME's
`/v1/webhooks/inferred-transition`. All other paths (no UUID in text,
non-AUTO_EXECUTE verdicts, feature-flag off) emit zero webhook calls.

This complements `test_initiative_webhook.py` (unit tests on the
emitter itself) by exercising the pipeline → emitter wire.
"""
from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.config import EngineConfig
from engine.hme_event_emitter import _reset_idempotency_cache
from engine.models import (
    AlignmentScores, DecisionClass, DecisionObject, ExecutionVerdict,
    ReversibilityTag, TimeHorizon, TrustScores, ValueScores,
)
from engine.pipeline import process_decision

# Reusable initiative UUID for the integration tests.
_INITIATIVE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Configure the gateway + force OIDC off so the emitter takes the wire path."""
    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("DECISION_HME_DISABLE_OIDC", "1")
    monkeypatch.delenv("DECISION_HME_EMIT_DISABLED", raising=False)
    monkeypatch.delenv("EMIT_INFERRED_TRANSITION", raising=False)
    _reset_idempotency_cache()
    yield
    _reset_idempotency_cache()


def _ok_response():
    m = mock.MagicMock()
    m.__enter__ = mock.MagicMock(return_value=m)
    m.__exit__ = mock.MagicMock(return_value=None)
    m.status = 200
    m.getcode = mock.MagicMock(return_value=200)
    m.read.return_value = b"{}"
    return m


def _make_d1_with_initiative_uuid(uuid: str = _INITIATIVE_UUID) -> DecisionObject:
    """D1 (auto-execute) decision whose action text references an initiative UUID.

    The pipeline's `infer_initiative_id` walks action/title/evidence;
    placing the UUID in `requested_action` is sufficient to trigger emission.
    """
    return DecisionObject(
        title="Advance onboarding initiative",
        decision_class=DecisionClass.D1_REVERSIBLE_TACTICAL,
        owner="marketing_ops",
        time_horizon=TimeHorizon.IMMEDIATE,
        reversibility=ReversibilityTag.R1_EASILY_REVERSIBLE,
        problem_statement="Current onboarding email has 12% open rate",
        requested_action=f"Advance initiative {uuid} to next stage",
        context_summary="A/B test shows clear winner",
        stakeholders=["marketing_ops", "customer_success"],
        evidence_refs=["ab_test_results.csv", "compliance_checklist.md"],
        execution_plan="Swap template, monitor 7 days",
        monitoring_metric="email_open_rate >= 18%",
        rollback_trigger="open_rate < 15% over 48hrs",
        review_date="2026-03-31",
        current_state="trust_certified",
        actor_role="AI_Domain_Agent",
        value_scores=ValueScores(
            revenue_impact=2, cost_efficiency=3, time_leverage=4,
            strategic_alignment=3, customer_human_benefit=3,
            knowledge_asset_creation=2, compounding_potential=2, reversibility=5,
            downside_risk=1, execution_drag=1, uncertainty=1, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=4, logic_integrity=4, outcome_history=3,
            context_fit=4, stakeholder_clarity=4, risk_containment=4, auditability=4,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.8, ethos_alignment=0.9,
            first_principles_alignment=0.7,
        ),
    )


def _make_d1_without_initiative_uuid() -> DecisionObject:
    """D1 (auto-execute) decision with NO initiative UUID anywhere in its text."""
    d = _make_d1_with_initiative_uuid()
    d.title = "Deploy updated onboarding email template"
    d.requested_action = "Replace template with A/B tested winner"
    d.context_summary = "A/B test showed 22% open rate"
    d.evidence_refs = ["ab_test_results.csv", "compliance_checklist.md"]
    return d


def _make_blocked_decision_with_initiative_uuid() -> DecisionObject:
    """D6 (BLOCK) decision that DOES mention an initiative UUID.

    Verifies the gate is on `verdict == AUTO_EXECUTE`, not on text content.
    Even with an initiative UUID present, a BLOCK verdict must not emit.
    """
    return DecisionObject(
        title="Acquire competitor for $2M",
        decision_class=DecisionClass.D6_IRREVERSIBLE_HIGH_BLAST,
        owner="ceo",
        time_horizon=TimeHorizon.MID_TERM,
        reversibility=ReversibilityTag.R4_EFFECTIVELY_IRREVERSIBLE,
        problem_statement="Competitor has IP to accelerate roadmap",
        requested_action=f"Proceed with acquisition tied to initiative {_INITIATIVE_UUID}",
        context_summary="Preliminary DD, unaudited financials",
        stakeholders=["ceo", "cfo", "board"],
        evidence_refs=["preliminary_dd_report.pdf"],
        assumptions=["IP is defensible"],
        unknowns=["Full audit pending"],
        required_approvals=["ceo", "cfo", "board"],
        execution_plan="Complete DD, negotiate, board vote",
        monitoring_metric="integration_milestones",
        rollback_trigger="deal_breaker_in_dd",
        current_state="draft",
        actor_role="Human_CEO",
        value_scores=ValueScores(
            revenue_impact=4, cost_efficiency=2, time_leverage=5,
            strategic_alignment=5, customer_human_benefit=3,
            knowledge_asset_creation=4, compounding_potential=5, reversibility=0,
            downside_risk=5, execution_drag=4, uncertainty=5, ethical_misalignment=0,
        ),
        trust_scores=TrustScores(
            evidence_quality=2, logic_integrity=3, outcome_history=1,
            context_fit=3, stakeholder_clarity=3, risk_containment=1, auditability=2,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=0.7, ethos_alignment=0.6,
            first_principles_alignment=0.5,
        ),
    )


def _capture_webhook_calls():
    """Return (mock_urlopen, calls_list) where calls_list collects only the
    inferred-transition webhook POSTs (filtering out the gamification POST
    that also fires on AUTO_EXECUTE)."""
    calls: list[dict] = []

    def fake_urlopen(req, timeout):
        url = req.full_url
        if "/v1/webhooks/inferred-transition" in url:
            import json
            calls.append({
                "url": url,
                "method": req.get_method(),
                "body": json.loads(req.data.decode("utf-8")),
            })
        return _ok_response()

    return fake_urlopen, calls


# ── AUTO_EXECUTE + initiative_id → exactly one POST ─────────────────────────


def test_pipeline_auto_execute_with_initiative_emits_one_webhook():
    """The agentic-loop happy path: AUTO_EXECUTE + UUID → POST fires."""
    fake_urlopen, calls = _capture_webhook_calls()
    config = EngineConfig()
    decision = _make_d1_with_initiative_uuid()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = process_decision(decision, config)

    assert result.execution_packet.verdict == ExecutionVerdict.AUTO_EXECUTE
    assert len(calls) == 1, f"expected 1 inferred-transition POST, got {len(calls)}"
    body = calls[0]["body"]
    assert body["initiative_id"] == _INITIATIVE_UUID
    assert body["to_stage"] == "IN_PROGRESS"
    assert body["source_engine"] == "decision-engine"
    assert "AUTO_EXECUTE" in body["reasoning"]


# ── AUTO_EXECUTE but no initiative_id → zero POSTs ──────────────────────────


def test_pipeline_auto_execute_without_initiative_emits_no_webhook():
    """AUTO_EXECUTE on a decision lacking an initiative UUID → no webhook.

    This is the safe-detection guarantee from `infer_initiative_id`:
    only decisions that explicitly reference `initiative <uuid>` fire
    a lifecycle transition.
    """
    fake_urlopen, calls = _capture_webhook_calls()
    config = EngineConfig()
    decision = _make_d1_without_initiative_uuid()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = process_decision(decision, config)

    assert result.execution_packet.verdict == ExecutionVerdict.AUTO_EXECUTE
    assert calls == []


# ── Non-AUTO_EXECUTE verdict + initiative_id present → zero POSTs ───────────


def test_pipeline_block_with_initiative_uuid_emits_no_webhook():
    """A BLOCK verdict on a decision that mentions an initiative must NOT emit.

    Guarantees the gate is verdict-keyed, not text-keyed.
    """
    fake_urlopen, calls = _capture_webhook_calls()
    config = EngineConfig()
    decision = _make_blocked_decision_with_initiative_uuid()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = process_decision(decision, config)

    assert result.execution_packet.verdict == ExecutionVerdict.BLOCK
    assert calls == []


# ── Feature-flag OFF suppresses pipeline emission ───────────────────────────


def test_pipeline_emit_inferred_transition_flag_off_suppresses(monkeypatch):
    """EMIT_INFERRED_TRANSITION=0 → AUTO_EXECUTE + UUID still produces zero POSTs."""
    monkeypatch.setenv("EMIT_INFERRED_TRANSITION", "0")
    fake_urlopen, calls = _capture_webhook_calls()
    config = EngineConfig()
    decision = _make_d1_with_initiative_uuid()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = process_decision(decision, config)

    assert result.execution_packet.verdict == ExecutionVerdict.AUTO_EXECUTE
    assert calls == []


# ── HME outage does not break the pipeline ──────────────────────────────────


def test_pipeline_continues_when_hme_returns_5xx():
    """If HME returns 5xx on the webhook, the decision pipeline still succeeds."""
    import urllib.error
    from io import BytesIO

    def fail_urlopen(req, timeout):
        if "/v1/webhooks/inferred-transition" in req.full_url:
            raise urllib.error.HTTPError(
                req.full_url, 503, "service unavailable",
                hdrs=None, fp=BytesIO(b"{}"),
            )
        return _ok_response()

    config = EngineConfig()
    decision = _make_d1_with_initiative_uuid()
    with mock.patch("urllib.request.urlopen", side_effect=fail_urlopen):
        result = process_decision(decision, config)

    assert result.success is True
    assert result.execution_packet.verdict == ExecutionVerdict.AUTO_EXECUTE


# ── Re-running same decision does not double-emit ───────────────────────────


def test_pipeline_re_run_does_not_double_emit():
    """Running the same decision twice through the pipeline → one POST total.

    The emitter's in-process idempotency cache suppresses the second
    POST for the same (decision_id, initiative_id, to_stage) tuple.
    """
    fake_urlopen, calls = _capture_webhook_calls()
    config = EngineConfig()
    decision = _make_d1_with_initiative_uuid()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        process_decision(decision, config)
        process_decision(decision, config)

    assert len(calls) == 1, (
        f"expected single POST due to idempotency, got {len(calls)}"
    )
