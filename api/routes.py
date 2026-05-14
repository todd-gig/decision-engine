"""
API Routes — Unified decision engine endpoints.

Exposes the full pipeline, simplified evaluation, state transitions,
outcome recording, learning analytics, and configuration.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional

from engine.models import (
    DecisionObject, DecisionClass, ReversibilityTag, TimeHorizon,
    ValueScores, TrustScores, AlignmentScores,
    RTQLInput, RTQLScores, CausalChecks,
)
from engine.config import EngineConfig, load_config
from engine.pipeline import process_decision
from engine.audit import serialize_pipeline_result
from engine.state_machine import (
    can_transition as sm_can_transition,
    advance_state, get_lifecycle_status,
    STATE_CERTIFICATE_MAP,
)
from engine.learning_loop import record_outcome as ll_record_outcome, LearningStore

# Simplified evaluation imports (backward compat)
from engine.weighted_scoring import compute_weighted_value as _simple_value
from engine.scoring import calculate_trust_tier

from .schemas import (
    FullDecisionRequest, SimpleEvaluationRequest,
    TransitionRequest, TransitionResponse,
    OutcomeRequest, PipelineResponse, AuditEntry,
    OverrideRecordRequest, ProposalCreateRequest, ProposalApproveRequest,
    ProposalSimSummary, AnalyzerRunRequest, AIInvokeRequest,
    SweepRunRequest, ProposalApproveAndCertifyRequest,
)

router = APIRouter()

# Load config once at startup
_config: Optional[EngineConfig] = None


def _get_config() -> EngineConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


# ── Health & Config ──


@router.get("/health")
def health():
    return {"status": "ok", "engine_version": "2.0.0"}


@router.get("/v1/config")
def get_config():
    config = _get_config()
    return {
        "thresholds": {
            "value_execute_min": config.thresholds.value_execute_min,
            "value_escalate_min": config.thresholds.value_escalate_min,
            "trust_execute_min": config.thresholds.trust_execute_min,
            "trust_recommend_min": config.thresholds.trust_recommend_min,
        },
        "trust_multiplier": config.trust_multiplier,
        "valid_transitions": config.valid_transitions,
    }


# ── Full Pipeline ──


def _build_decision_object(req: FullDecisionRequest) -> DecisionObject:
    """Convert API request into engine DecisionObject."""
    vs = req.value_scores
    ts = req.trust_scores
    als = req.alignment_scores

    rtql = None
    if req.rtql_input:
        ri = req.rtql_input
        rtql = RTQLInput(
            claim=ri.claim,
            source=ri.source,
            is_identifiable=ri.is_identifiable,
            has_provenance=ri.has_provenance,
            scores=RTQLScores(
                source_integrity=ri.scores.source_integrity,
                exposure_count=ri.scores.exposure_count,
                independence=ri.scores.independence,
                explainability=ri.scores.explainability,
                replicability=ri.scores.replicability,
                adversarial_robustness=ri.scores.adversarial_robustness,
                novelty_yield=ri.scores.novelty_yield,
            ),
            causal_checks=CausalChecks(
                reveals_causal_mechanism=ri.causal_checks.reveals_causal_mechanism,
                is_irreducible=ri.causal_checks.is_irreducible,
                survives_authority_removal=ri.causal_checks.survives_authority_removal,
                survives_context_shift=ri.causal_checks.survives_context_shift,
            ),
        )

    return DecisionObject(
        title=req.title,
        decision_class=DecisionClass(req.decision_class),
        owner=req.owner,
        time_horizon=TimeHorizon(req.time_horizon),
        reversibility=ReversibilityTag(req.reversibility),
        problem_statement=req.problem_statement,
        requested_action=req.requested_action,
        context_summary=req.context_summary,
        stakeholders=req.stakeholders,
        constraints=req.constraints,
        value_scores=ValueScores(
            revenue_impact=vs.revenue_impact,
            cost_efficiency=vs.cost_efficiency,
            time_leverage=vs.time_leverage,
            strategic_alignment=vs.strategic_alignment,
            customer_human_benefit=vs.customer_human_benefit,
            knowledge_asset_creation=vs.knowledge_asset_creation,
            compounding_potential=vs.compounding_potential,
            reversibility=vs.reversibility,
            downside_risk=vs.downside_risk,
            execution_drag=vs.execution_drag,
            uncertainty=vs.uncertainty,
            ethical_misalignment=vs.ethical_misalignment,
        ),
        trust_scores=TrustScores(
            evidence_quality=ts.evidence_quality,
            logic_integrity=ts.logic_integrity,
            outcome_history=ts.outcome_history,
            context_fit=ts.context_fit,
            stakeholder_clarity=ts.stakeholder_clarity,
            risk_containment=ts.risk_containment,
            auditability=ts.auditability,
        ),
        alignment_scores=AlignmentScores(
            doctrine_alignment=als.doctrine_alignment,
            ethos_alignment=als.ethos_alignment,
            first_principles_alignment=als.first_principles_alignment,
            anti_pattern_flags=als.anti_pattern_flags,
            applied_principles=als.applied_principles,
        ),
        rtql_input=rtql,
        evidence_refs=req.evidence_refs,
        assumptions=req.assumptions,
        unknowns=req.unknowns,
        required_approvals=req.required_approvals,
        execution_plan=req.execution_plan,
        monitoring_metric=req.monitoring_metric,
        rollback_trigger=req.rollback_trigger,
        review_date=req.review_date,
        current_state=req.current_state,
        actor_role=req.actor_role,
        has_missing_data=req.has_missing_data,
        ethical_conflict=req.ethical_conflict,
    )


@router.post("/v1/decisions/process", response_model=PipelineResponse)
def process_decision_endpoint(req: FullDecisionRequest):
    """
    Full pipeline processing — the primary endpoint.

    Accepts a complete DecisionObject and runs the full 9-stage pipeline:
    validation → RTQL → value → trust → authority → certificates →
    7-gate authorization → state machine → priority scoring.

    Returns verdict, certificates, audit trail, and executive summary.
    """
    config = _get_config()
    decision = _build_decision_object(req)
    result = process_decision(decision, config)

    # Build response
    serialized = serialize_pipeline_result(result)
    verdict = ""
    reason = ""
    if result.execution_packet:
        verdict = result.execution_packet.verdict.value
        blocking = result.execution_packet.blocking_gates
        reason = blocking[0] if blocking else "all_gates_passed"

    cert_status = {}
    if result.certificate_chain:
        chain = result.certificate_chain
        for name, cert in [("QC", chain.qc), ("VC", chain.vc),
                           ("TC", chain.tc), ("EC", chain.ec)]:
            cert_status[name] = cert.status.value if cert else "not_attempted"

    next_state = ""
    if "execution" in serialized:
        # Derive from state machine
        from engine.state_machine import next_state_for_action
        next_state = next_state_for_action(req.current_state, verdict)

    audit_log = [
        AuditEntry(stage=r["stage"], detail={"action": r["action"], "notes": r["notes"]})
        for r in serialized.get("audit_trail", [])
    ]

    return PipelineResponse(
        decision_id=result.decision_id,
        success=result.success,
        validation_errors=result.validation_errors,
        recommended_action=verdict,
        reason_code=reason,
        value_classification=result.value_classification,
        net_value_score=result.net_value_score,
        trust_tier=result.trust_tier.value,
        trust_total=result.trust_total,
        alignment_composite=round(result.alignment_composite, 3),
        alignment_violations=result.alignment_violations,
        priority_score=result.priority_score,
        next_state=next_state,
        certificate_status=cert_status,
        executive_summary=result.executive_summary,
        audit_log=audit_log,
        full_result=serialized,
    )


# ── State Transitions ──


@router.post("/v1/decisions/transition", response_model=TransitionResponse)
def transition_decision(payload: TransitionRequest):
    """Check if a state transition is valid and return required certificates."""
    config = _get_config()
    allowed = sm_can_transition(payload.current_state, payload.target_state, config)
    certs = STATE_CERTIFICATE_MAP.get(payload.target_state, [])
    return TransitionResponse(
        allowed=allowed,
        current_state=payload.current_state,
        target_state=payload.target_state,
        required_certificates=certs,
    )


@router.get("/v1/decisions/lifecycle/{state}")
def lifecycle_status(state: str):
    """Get lifecycle position for a decision state."""
    return get_lifecycle_status(state)


# ── Learning Loop ──


@router.post("/v1/outcomes/record")
def record_outcome_endpoint(req: OutcomeRequest):
    """Record a post-execution outcome for the learning loop."""
    record = ll_record_outcome(
        decision_id=req.decision_id,
        decision_class=req.decision_class,
        original_verdict=req.original_verdict,
        expected_value=req.expected_value,
        expected_timeline_days=req.expected_timeline_days,
        expected_risk_level=req.expected_risk_level,
        actual_value=req.actual_value,
        actual_timeline_days=req.actual_timeline_days,
        actual_risk_materialized=req.actual_risk_materialized,
        actual_risk_description=req.actual_risk_description,
        outcome_summary=req.outcome_summary,
        lessons_learned=req.lessons_learned,
        recorded_by=req.recorded_by,
    )
    return {
        "record_id": record.record_id,
        "decision_id": record.decision_id,
        "trust_recommendation": record.variance.trust_recommendation.value,
        "composite_variance": record.variance.composite_variance_score,
        "suggested_actions": record.variance.suggested_actions,
    }


@router.get("/v1/learning/summary")
def learning_summary():
    """Get institutional learning summary."""
    store = LearningStore()
    return {
        "summary": store.generate_learning_summary(),
        "stats": store.compute_class_stats(),
    }


@router.get("/v1/learning/unapplied")
def unapplied_learnings():
    """Get learning records that haven't been applied yet."""
    store = LearningStore()
    records = store.get_unapplied()
    return {
        "count": len(records),
        "records": [
            {
                "decision_id": r.decision_id,
                "decision_class": r.decision_class,
                "trust_recommendation": r.variance.trust_recommendation.value,
                "suggested_actions": r.variance.suggested_actions,
                "suggested_update_targets": r.variance.suggested_update_targets,
            }
            for r in records
        ],
    }


# ── Human Overrides ─────────────────────────────────────────────────────────


@router.post("/v1/overrides", status_code=202)
def overrides_record(payload: OverrideRecordRequest):
    """Record a human override of an engine decision.

    Per CRIT-001 (Human Override Non-Negotiable). Persists to the
    human_overrides SQLite store; 5-type taxonomy classification is
    computed automatically. v0.5 additions:
      - reasoning ≥20 chars enforced (422 on short reasoning)
      - HMAC-SHA256 signature attached to every persisted row
      - OVS-Calibration emission on insert (per-type weight)
      - per-overrider rate-limit alert at >10/hour (never blocks)
    """
    from engine.human_override import (
        OverrideRecord, ReasoningTooShort, record_override,
    )
    try:
        rec = OverrideRecord(
            decision_id=payload.decision_id,
            decision_certificate_id=payload.decision_certificate_id,
            override_type=payload.override_type,
            overridden_by_user_id=payload.overridden_by_user_id,
            overridden_at=payload.overridden_at,
            source_engine=payload.source_engine,
            surface=payload.surface,
            original_action=payload.original_action,
            override_action=payload.override_action,
            user_reasoning=payload.user_reasoning,
            freeform_metadata=payload.freeform_metadata,
        )
        return record_override(rec)
    except ReasoningTooShort as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        # classify_override raises on unknown override_type
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/v1/overrides/sweep", status_code=202)
def overrides_sweep(window_days: int = 1, dry_run: bool = False):
    """Run the nightly human-override pattern sweep (admin).

    Detects clusters over the last `window_days` days, persists them to
    override_patterns, and opens negative-polarity codification
    proposals for stable patterns (cluster_size ≥5 AND span ≥48h).
    """
    from engine.human_override import sweep
    window_days = max(1, min(int(window_days), 30))
    return sweep.run_nightly_sweep(window_days=window_days, dry_run=dry_run)


@router.get("/v1/overrides/patterns")
def overrides_patterns(
    cross_org: bool = False,
    polarity: Optional[str] = None,
    limit: int = 200,
):
    """List detected override patterns.

    When `cross_org=true`, any user-id fields in the response are
    redacted to a stable anonymous hash (per spec decision #11). The
    override_patterns table itself doesn't carry user ids today; the
    redaction seam is defensive for v0.6 schema extensions.
    """
    from engine.human_override import anonymize, patterns
    limit = max(1, min(int(limit), 1000))
    items = patterns.list_patterns(limit=limit, polarity=polarity)
    if cross_org:
        items = [anonymize.redact_row(item) for item in items]
    return {
        "items": items,
        "count": len(items),
        "filter": {"polarity": polarity, "cross_org": cross_org},
    }


@router.get("/v1/overrides/{override_id}")
def overrides_get(override_id: str):
    """Return one override record by id."""
    import sqlite3
    from engine.human_override import storage
    conn = storage.get_connection()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM human_overrides WHERE override_id = ?",
            (override_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"override {override_id!r} not found")
        return dict(row)
    finally:
        conn.close()


@router.get("/v1/overrides")
def overrides_list(
    source_engine: Optional[str] = None,
    override_type: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 200,
):
    """List override records with optional filters."""
    import sqlite3
    from engine.human_override import storage
    limit = max(1, min(limit, 1000))
    conn = storage.get_connection()
    try:
        conn.row_factory = sqlite3.Row
        clauses = []
        params: list = []
        if source_engine is not None:
            clauses.append("source_engine = ?")
            params.append(source_engine)
        if override_type is not None:
            clauses.append("override_type = ?")
            params.append(override_type)
        if user_id is not None:
            clauses.append("overridden_by_user_id = ?")
            params.append(user_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        sql = f"""
            SELECT * FROM human_overrides {where}
            ORDER BY overridden_at DESC LIMIT ?
        """
        rows = conn.execute(sql, params).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "count": len(rows),
            "filter": {
                "source_engine": source_engine,
                "override_type": override_type,
                "user_id": user_id,
            },
        }
    finally:
        conn.close()


# ── Codification Proposals ──────────────────────────────────────────────────


@router.post("/v1/proposals", status_code=201)
def proposals_open(payload: ProposalCreateRequest):
    """Open a new codification proposal in the queue (status='open')."""
    from engine.codification import (
        CodificationProposal, SimulationResult, open_proposal,
    )
    prop = CodificationProposal(
        candidate_pv=payload.candidate_pv,
        candidate_sv=payload.candidate_sv,
        candidate_score=payload.candidate_score,
        analyzer_run_at=payload.analyzer_run_at,
        proposed_python=payload.proposed_python,
        proposed_tests=payload.proposed_tests,
        why=payload.why,
        sim=SimulationResult(
            n=payload.sim.n,
            divergence_p50=payload.sim.divergence_p50,
            divergence_p90=payload.sim.divergence_p90,
            cost_savings_usd=payload.sim.cost_savings_usd,
            latency_savings_ms=payload.sim.latency_savings_ms,
        ),
    )
    return open_proposal(prop)


@router.get("/v1/proposals/{proposal_id}")
def proposals_get(proposal_id: str):
    """Return one proposal by id."""
    from engine.codification import get_proposal
    body = get_proposal(proposal_id)
    if body is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id!r} not found")
    return body


@router.get("/v1/proposals")
def proposals_list(status: Optional[str] = None, limit: int = 200):
    """List proposals, optionally filtered by status."""
    from engine.codification import list_proposals
    limit = max(1, min(limit, 1000))
    items = list_proposals(status=status, limit=limit)
    return {"items": items, "count": len(items), "filter": {"status": status}}


@router.post("/v1/proposals/{proposal_id}/approve")
def proposals_approve(proposal_id: str, payload: ProposalApproveRequest):
    """Record the human decision on a proposal. Idempotent only for new statuses."""
    from engine.codification import approve_proposal
    try:
        return approve_proposal(
            proposal_id,
            approver_user_id=payload.approver_user_id,
            approval_why=payload.approval_why,
            new_status=payload.new_status,
            shipped_pr_url=payload.shipped_pr_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/v1/codification/analyze")
def codification_analyze(payload: AnalyzerRunRequest):
    """Trigger an analyzer run over llm_audit; optionally open top-N candidates as proposals."""
    from engine.codification import analyze, open_candidates_as_proposals
    candidates = analyze(
        min_volume=payload.min_volume,
        score_threshold=payload.score_threshold,
        audit_db_path=payload.audit_db_path,
    )
    opened: list[dict] = []
    if payload.open_top_n_as_proposals > 0 and candidates:
        opened = open_candidates_as_proposals(
            candidates,
            top_n=payload.open_top_n_as_proposals,
            proposals_db_path=payload.proposals_db_path,
            why=payload.why,
        )
    return {
        "candidates": [c.to_dict() for c in candidates],
        "candidate_count": len(candidates),
        "proposals_opened": opened,
        "proposals_opened_count": len(opened),
    }


# ── AI Router HTTP wrapper ──────────────────────────────────────────────────


@router.post("/v1/ai/invoke")
def ai_invoke(payload: AIInvokeRequest):
    """HTTP wrapper around engine.ai_router.invoke.

    Per specs/ai_routing_engine_v0.md §v0→v0.5 graduation criteria: when
    non-Python or cross-repo callers need to use the chokepoint, they go
    through this endpoint instead of importing the package directly. All
    enforcements (CRIT-003 + CRIT-007 + HMAC audit row) happen server-side.
    """
    from engine.ai_router import invoke, ProviderUnavailable
    try:
        result = invoke(
            prompt=payload.prompt,
            provider=payload.provider,
            model=payload.model,
            prompt_version=payload.prompt_version,
            schema_version=payload.schema_version,
            caller_engine=payload.caller_engine,
            caller_function=payload.caller_function,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
            fallback_chain=payload.fallback_chain,
            timeout_seconds=payload.timeout_seconds,
            audit_metadata=payload.audit_metadata,
        )
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "text": result.text,
        "provider_used": result.provider_used,
        "model_used": result.model_used,
        "prompt_version": result.prompt_version,
        "schema_version": result.schema_version,
        "in_tokens": result.in_tokens,
        "out_tokens": result.out_tokens,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "audit_id": result.audit_id,
        "fallback_chain_taken": result.fallback_chain_taken,
    }


# ── Drift Sentinel queries ──────────────────────────────────────────────────


@router.get("/v1/drift/open")
def drift_open(
    severity: Optional[str] = None,
    limit: int = 200,
    scan_id: Optional[str] = None,
):
    """Open drift signals from the most recent scan in drift_history.db.

    Used by the Founder UI drift-triage panel. Returns the most-recent
    scan's violations grouped by severity, with optional filters.

    Per drift_sentinel/drift_scan.py the schema is:
        scans(scan_id, timestamp, sources, total_artifacts,
              critical, major, minor, info)
        violations(id, scan_id, rule_id, severity, artifact, location, excerpt)
    """
    import sqlite3
    from pathlib import Path

    if severity is not None and severity not in {"critical", "major", "minor", "info"}:
        raise HTTPException(
            status_code=422,
            detail="severity must be one of: critical, major, minor, info",
        )
    limit = max(1, min(limit, 1000))

    # drift_history.db lives at <repo>/drift_sentinel/drift_history.db
    db_path = Path(__file__).resolve().parent.parent / "drift_sentinel" / "drift_history.db"
    if not db_path.exists():
        return {
            "scan": None,
            "items": [],
            "count": 0,
            "filter": {"severity": severity, "scan_id": scan_id},
            "note": "drift_history.db not present; scanner hasn't run yet",
        }
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row

        if scan_id is None:
            scan_row = conn.execute(
                "SELECT * FROM scans ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            if scan_row is None:
                return {
                    "scan": None, "items": [], "count": 0,
                    "filter": {"severity": severity, "scan_id": None},
                }
            scan_id = scan_row["scan_id"]
            scan_dict = dict(scan_row)
        else:
            scan_row = conn.execute(
                "SELECT * FROM scans WHERE scan_id = ?", (scan_id,),
            ).fetchone()
            if scan_row is None:
                raise HTTPException(status_code=404, detail=f"scan_id {scan_id!r} not found")
            scan_dict = dict(scan_row)

        # Severity sort: critical > major > minor > info
        sev_order_sql = (
            "CASE severity WHEN 'critical' THEN 0 WHEN 'major' THEN 1 "
            "WHEN 'minor' THEN 2 ELSE 3 END"
        )
        params: list = [scan_id]
        sql = (
            "SELECT * FROM violations WHERE scan_id = ?"
        )
        if severity is not None:
            sql += " AND severity = ?"
            params.append(severity)
        sql += f" ORDER BY {sev_order_sql}, rule_id LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return {
            "scan": scan_dict,
            "items": [dict(r) for r in rows],
            "count": len(rows),
            "filter": {"severity": severity, "scan_id": scan_id},
        }
    finally:
        conn.close()


# ── Doctrine (read-only) ────────────────────────────────────────────────────


@router.get("/v1/doctrine/version")
def doctrine_version():
    """Return version + reconciliation date of canonical first principles.

    Used by Founder UI to surface the current doctrine version and
    detect when a re-render of the doctrine editor is needed.
    """
    import re
    from pathlib import Path

    canon_path = (
        Path(__file__).resolve().parent.parent
        / "drift_sentinel" / "GIGATON_CANONICAL_FIRST_PRINCIPLES.md"
    )
    if not canon_path.exists():
        raise HTTPException(
            status_code=404,
            detail="GIGATON_CANONICAL_FIRST_PRINCIPLES.md not found",
        )
    text = canon_path.read_text(encoding="utf-8")
    # Look for "*Last reconciled: YYYY-MM-DD" — the canonical reconciliation marker
    reconciled = None
    m = re.search(
        r"\*Last reconciled:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE,
    )
    if m:
        reconciled = m.group(1)

    # Count frameworks (matches "### 5.X" pattern) for a quick health check
    frameworks = len(re.findall(r"^### 5\.\d+(?:\s|\.)", text, re.MULTILINE))
    principles = len(re.findall(r"^## 2\.\d+(?:\s|\.)", text, re.MULTILINE))
    return {
        "path": "drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md",
        "last_reconciled": reconciled,
        "framework_count": frameworks,
        "principle_count": principles,
        "size_bytes": len(text.encode("utf-8")),
    }


@router.get("/v1/doctrine")
def doctrine_body(
    include_body: bool = False,
    section: Optional[str] = None,
):
    """Return canonical first principles content (optionally a single section).

    `include_body=true`: returns full markdown body.
    `section=5.19`: returns just the section starting with "### 5.19".

    Without either flag, returns the front-matter summary only.
    """
    import re
    from pathlib import Path

    canon_path = (
        Path(__file__).resolve().parent.parent
        / "drift_sentinel" / "GIGATON_CANONICAL_FIRST_PRINCIPLES.md"
    )
    if not canon_path.exists():
        raise HTTPException(status_code=404, detail="canonical doc not found")
    text = canon_path.read_text(encoding="utf-8")
    out = {
        "path": "drift_sentinel/GIGATON_CANONICAL_FIRST_PRINCIPLES.md",
    }
    if section:
        # Match `### <section>` at the start of a line, capture until the next
        # `### ` heading (or end of doc).
        pattern = r"^### " + re.escape(section) + r"[\s\S]*?(?=^### |\Z)"
        m = re.search(pattern, text, re.MULTILINE)
        if m is None:
            raise HTTPException(
                status_code=404,
                detail=f"section {section!r} not found in canonical doc",
            )
        out["section"] = section
        out["body"] = m.group(0).rstrip()
        return out
    if include_body:
        out["body"] = text
        return out
    # Summary mode: first 30 lines
    out["preview"] = "\n".join(text.splitlines()[:30])
    out["size_bytes"] = len(text.encode("utf-8"))
    return out


# ── Codification sweep + approval ───────────────────────────────────────────


@router.post("/v1/codification/sweep")
def codification_sweep(payload: SweepRunRequest):
    """Run the scheduled codification sweep — analyzer + readiness gate +
    auto-open proposals for ready candidates. This is the entrypoint
    Cloud Scheduler hits to close the Codification Rate flywheel.
    """
    from engine.codification import run_sweep
    report = run_sweep(
        min_volume=payload.min_volume,
        score_threshold=payload.score_threshold,
        audit_db_path=payload.audit_db_path,
        proposals_db_path=payload.proposals_db_path,
        open_proposals=payload.open_proposals,
        why=payload.why,
    )
    return report.to_dict()


@router.post("/v1/proposals/{proposal_id}/approve-and-certify")
def proposals_approve_and_certify(
    proposal_id: str, payload: ProposalApproveAndCertifyRequest
):
    """Approve a proposal and mint the governing CodificationCertificate.

    Authorization is enforced via the sign-off matrix:
      - decision_class='new-module'         → todd@gigaton.ai required
      - decision_class='tuning'             → matt@gigaton.ai required
      - decision_class='doctrine-touching'  → both required (use additional_signers)
    """
    from engine.codification import approve_and_certify
    try:
        return approve_and_certify(
            proposal_id,
            approver_user_id=payload.approver_user_id,
            approval_why=payload.approval_why,
            new_status=payload.new_status,
            decision_class=payload.decision_class,
            evidence_decision_ids=payload.evidence_decision_ids,
            proposed_spec=payload.proposed_spec,
            prompt_version=payload.prompt_version,
            schema_version=payload.schema_version,
            additional_signers=payload.additional_signers,
            shipped_pr_url=payload.shipped_pr_url,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
