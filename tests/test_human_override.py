"""human_override — recorder + classification taxonomy + v0.5 hardening.

v0.5 adds: HMAC signing, reasoning length validation, append-only
enforcement, pattern detection, nightly sweep, calibration emission,
drift signal, rate-limit alert, anonymized cross-org view.

penrose_signal: weakens
penrose_dimension: override_rate
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.human_override import (
    MIN_REASONING_CHARS,
    NotSupported,
    OverrideRecord,
    OverrideType,
    ReasoningTooShort,
    classify_override,
    delete_override,
    record_override,
)
from engine.human_override import (
    anonymize,
    calibration_emit,
    drift_signal,
    patterns,
    rate_limit,
    signing,
    storage,
    sweep,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "human_overrides.db")


@pytest.fixture
def tmp_calibration_log(tmp_path: Path, monkeypatch) -> Path:
    log = tmp_path / "calibration.jsonl"
    monkeypatch.setenv("OVERRIDE_CALIBRATION_LOG", str(log))
    # Also patch the module-level default since it's resolved on import.
    monkeypatch.setattr(calibration_emit, "_default_log_path", lambda: log)
    return log


@pytest.fixture
def tmp_codification_db(tmp_path: Path) -> str:
    return str(tmp_path / "codification.db")


def _new_record(**overrides) -> OverrideRecord:
    defaults = dict(
        decision_id="DEC-1234",
        decision_certificate_id="EC-1234",
        override_type=OverrideType.REVERSAL.value,
        overridden_by_user_id="user-uuid",
        overridden_at=datetime.now(tz=timezone.utc).isoformat(),
        source_engine="sales-os",
        surface="operator_dashboard:opportunity_detail",
        original_action="auto_send_proposal",
        override_action="hold_for_review",
        user_reasoning="pricing exceeded client budget",
    )
    defaults.update(overrides)
    return OverrideRecord(**defaults)


# ── v0 classification + persistence ────────────────────────────────────────


def test_classify_reversal_is_3x():
    cls = classify_override(_new_record(override_type="reversal"))
    assert cls.ovs_weight == 3.0
    assert cls.codification_action == "open_exception_case_now"


def test_classify_modification_is_2x():
    cls = classify_override(_new_record(override_type="modification"))
    assert cls.ovs_weight == 2.0


def test_classify_rejection_is_2x():
    cls = classify_override(_new_record(override_type="rejection"))
    assert cls.ovs_weight == 2.0


def test_classify_silent_inaction_is_1_5x():
    cls = classify_override(_new_record(override_type="silent_inaction"))
    assert cls.ovs_weight == 1.5


def test_classify_repeated_override_is_4x_and_escalates():
    cls = classify_override(_new_record(override_type="repeated_override"))
    assert cls.ovs_weight == 4.0
    assert cls.codification_action == "escalate_to_founder"


def test_classify_rejects_unknown_type():
    with pytest.raises(ValueError, match="unknown override_type"):
        classify_override(_new_record(override_type="bogus"))


def test_record_override_writes_row(tmp_db, tmp_calibration_log):
    rec = _new_record()
    out = record_override(rec, db_path=tmp_db)
    assert out["override_id"] == rec.override_id
    assert out["classification"]["ovs_weight"] == 3.0
    assert out["signature"]  # v0.5

    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT classification, signature FROM human_overrides")
        row = cur.fetchone()
        assert row is not None
        cls = json.loads(row[0])
        assert cls["type"] == "reversal"
        assert cls["ovs_weight"] == 3.0
        assert row[1]  # signature persisted


def test_record_override_persists_user_reasoning(tmp_db, tmp_calibration_log):
    rec = _new_record(user_reasoning="this is the always-record-WHY field")
    record_override(rec, db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT user_reasoning FROM human_overrides")
        row = cur.fetchone()
        assert "always-record-WHY" in row[0]


def test_record_override_persists_freeform_metadata_as_json(
    tmp_db, tmp_calibration_log,
):
    rec = _new_record(freeform_metadata={"opportunity_id": "opp-1", "amount": 25000})
    record_override(rec, db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT freeform_metadata FROM human_overrides")
        meta = json.loads(cur.fetchone()[0])
        assert meta["opportunity_id"] == "opp-1"
        assert meta["amount"] == 25000


def test_two_records_both_persist(tmp_db, tmp_calibration_log):
    record_override(_new_record(decision_id="DEC-1"), db_path=tmp_db)
    record_override(_new_record(decision_id="DEC-2", override_type="modification"),
                    db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM human_overrides").fetchone()[0]
        assert n == 2


# ── v0.5 — HMAC signing + tamper detection ─────────────────────────────────


def test_signing_round_trip():
    rec = _new_record()
    sig = signing.sign(rec)
    assert signing.verify(rec, sig) is True


def test_signing_tamper_detection_changes_action():
    rec = _new_record()
    sig = signing.sign(rec)
    # Tamper: change the override action; old signature must no longer verify.
    rec.override_action = "auto_send_proposal_NO_REVIEW"
    assert signing.verify(rec, sig) is False


def test_signing_tamper_detection_changes_reasoning():
    rec = _new_record()
    sig = signing.sign(rec)
    rec.user_reasoning = "I just felt like it because I was bored today"
    assert signing.verify(rec, sig) is False


def test_signing_tamper_detection_changes_metadata():
    rec = _new_record(freeform_metadata={"a": 1})
    sig = signing.sign(rec)
    rec.freeform_metadata = {"a": 1, "b": 2}
    assert signing.verify(rec, sig) is False


def test_signing_empty_signature_rejected():
    rec = _new_record()
    assert signing.verify(rec, "") is False
    assert signing.verify(rec, None) is False  # type: ignore[arg-type]


# ── v0.5 — Reasoning length validation ─────────────────────────────────────


def test_short_reasoning_rejected(tmp_db, tmp_calibration_log):
    rec = _new_record(user_reasoning="ok")
    with pytest.raises(ReasoningTooShort) as excinfo:
        record_override(rec, db_path=tmp_db)
    assert "≥20" in str(excinfo.value)


def test_none_reasoning_rejected(tmp_db, tmp_calibration_log):
    rec = _new_record(user_reasoning=None)
    with pytest.raises(ReasoningTooShort):
        record_override(rec, db_path=tmp_db)


def test_whitespace_reasoning_rejected(tmp_db, tmp_calibration_log):
    rec = _new_record(user_reasoning="   \t\n   ")
    with pytest.raises(ReasoningTooShort):
        record_override(rec, db_path=tmp_db)


def test_reasoning_threshold_is_20_chars(tmp_db, tmp_calibration_log):
    assert MIN_REASONING_CHARS == 20
    # 19 chars should fail; 20 should pass.
    rec19 = _new_record(user_reasoning="a" * 19)
    with pytest.raises(ReasoningTooShort):
        record_override(rec19, db_path=tmp_db)
    rec20 = _new_record(user_reasoning="b" * 20)
    out = record_override(rec20, db_path=tmp_db)
    assert out["override_id"] == rec20.override_id


# ── v0.5 — Append-only enforcement ─────────────────────────────────────────


def test_delete_override_raises_not_supported():
    with pytest.raises(NotSupported, match="append-only"):
        delete_override("some-id")


def test_delete_module_not_exported_from_storage():
    # storage.delete_override should be importable but always raise.
    with pytest.raises(NotSupported):
        storage.delete_override("any-id")


# ── v0.5 — Calibration emission ────────────────────────────────────────────


def test_calibration_emission_on_reversal(tmp_db, tmp_calibration_log):
    rec = _new_record(override_type="reversal")
    record_override(rec, db_path=tmp_db)
    contents = tmp_calibration_log.read_text().strip().splitlines()
    assert len(contents) == 1
    payload = json.loads(contents[0])
    assert payload["source"] == "override"
    assert payload["weight"] == 3.0
    assert payload["override_id"] == rec.override_id
    assert payload["override_type"] == "reversal"
    assert payload["reasoning"] == rec.user_reasoning


def test_calibration_emission_modification_weight_2x(tmp_db, tmp_calibration_log):
    rec = _new_record(override_type="modification")
    record_override(rec, db_path=tmp_db)
    payload = json.loads(tmp_calibration_log.read_text().strip())
    assert payload["weight"] == 2.0


def test_calibration_emission_silent_inaction_weight_1_5x(
    tmp_db, tmp_calibration_log,
):
    rec = _new_record(override_type="silent_inaction")
    record_override(rec, db_path=tmp_db)
    payload = json.loads(tmp_calibration_log.read_text().strip())
    assert payload["weight"] == 1.5


def test_calibration_emission_disabled(tmp_db, tmp_calibration_log):
    rec = _new_record()
    record_override(rec, db_path=tmp_db, emit_to_calibration=False)
    assert not tmp_calibration_log.exists() or tmp_calibration_log.read_text() == ""


def test_calibration_emission_carries_decision_class_from_metadata(
    tmp_db, tmp_calibration_log,
):
    rec = _new_record(
        freeform_metadata={"decision_class": "pricing.dynamic.carmen-beach"},
    )
    record_override(rec, db_path=tmp_db)
    payload = json.loads(tmp_calibration_log.read_text().strip())
    assert payload["decision_class"] == "pricing.dynamic.carmen-beach"


# ── v0.5 — Pattern detection ───────────────────────────────────────────────


def _seed_pattern(
    tmp_db: str,
    *,
    n: int,
    decision_class: str = "pricing.x",
    override_type: str = "reversal",
    original_action: str = "auto_send_proposal",
    override_action: str = "hold_for_review",
    span_seconds: int = 60,
    start: datetime | None = None,
    user_id: str = "user-uuid",
) -> None:
    """Insert n synthetic overrides matching one cluster shape."""
    base = start or (datetime.now(tz=timezone.utc) - timedelta(days=1))
    step = timedelta(seconds=span_seconds // max(n - 1, 1)) if n > 1 else timedelta()
    for i in range(n):
        ts = (base + step * i).isoformat()
        rec = OverrideRecord(
            decision_id=f"DEC-{i}",
            decision_certificate_id=f"EC-{i}",
            override_type=override_type,
            overridden_by_user_id=user_id,
            overridden_at=ts,
            source_engine="sales-os",
            surface="dashboard",
            original_action=original_action,
            override_action=override_action,
            user_reasoning=f"clustering scenario row #{i:03d}",
            freeform_metadata={"decision_class": decision_class},
        )
        record_override(rec, db_path=tmp_db, emit_to_calibration=False)


def test_patterns_below_min_cluster_not_returned(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=2)  # min cluster is 3
    found = patterns.detect_patterns(window_days=30, db_path=tmp_db)
    assert found == []


def test_patterns_three_events_cluster_boundary(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=3)
    found = patterns.detect_patterns(window_days=30, db_path=tmp_db)
    assert len(found) == 1
    p = found[0]
    assert p.cluster_size == 3
    assert p.polarity == "negative"  # all override_actions identical
    assert "hold_for_review" in p.recommended_action


def test_patterns_five_events_cluster_boundary(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=5)
    found = patterns.detect_patterns(window_days=30, db_path=tmp_db)
    assert len(found) == 1
    assert found[0].cluster_size == 5


def test_patterns_distinct_override_actions_make_positive_polarity(
    tmp_db, tmp_calibration_log,
):
    base = datetime.now(tz=timezone.utc) - timedelta(days=1)
    for i, action in enumerate(["yes", "no", "maybe"]):
        rec = OverrideRecord(
            decision_id=f"DEC-{i}",
            decision_certificate_id=f"EC-{i}",
            override_type="reversal",
            overridden_by_user_id="user-uuid",
            overridden_at=(base + timedelta(seconds=i * 30)).isoformat(),
            source_engine="sales-os",
            surface="dashboard",
            original_action="auto_send_proposal",
            override_action=action,
            user_reasoning=f"varying corrections - this is row {i}",
            freeform_metadata={"decision_class": "pricing.x"},
        )
        record_override(rec, db_path=tmp_db, emit_to_calibration=False)
    found = patterns.detect_patterns(window_days=30, db_path=tmp_db)
    assert len(found) == 1
    assert found[0].polarity == "positive"
    assert "investigate" in found[0].recommended_action


def test_patterns_outside_window_excluded(tmp_db, tmp_calibration_log):
    old_start = datetime.now(tz=timezone.utc) - timedelta(days=14)
    _seed_pattern(tmp_db, n=3, start=old_start)
    # Default window = 7 days; old cluster shouldn't surface.
    assert patterns.detect_patterns(window_days=7, db_path=tmp_db) == []
    # But a wider window does.
    assert patterns.detect_patterns(window_days=30, db_path=tmp_db) != []


# ── v0.5 — Nightly sweep ───────────────────────────────────────────────────


def test_nightly_sweep_emits_codification_for_stable_pattern(
    tmp_db, tmp_calibration_log, tmp_codification_db,
):
    # Stable: 5 events spanning ≥48h. Place the cluster fully inside
    # the last 5 days so window_days=7 covers it generously.
    start = datetime.now(tz=timezone.utc) - timedelta(hours=120)
    _seed_pattern(tmp_db, n=5, span_seconds=50 * 3600, start=start)
    summary = sweep.run_nightly_sweep(
        window_days=7, db_path=tmp_db,
        codification_db_path=tmp_codification_db,
    )
    assert summary["patterns_detected"] >= 1
    assert summary["codification_proposals_opened"] == 1

    # Verify the proposal exists in the codification queue.
    with sqlite3.connect(tmp_codification_db) as conn:
        rows = conn.execute(
            "SELECT why FROM codification_proposals"
        ).fetchall()
        assert len(rows) == 1
        assert "Negative-polarity" in rows[0][0]


def test_nightly_sweep_skips_short_span(
    tmp_db, tmp_calibration_log, tmp_codification_db,
):
    # 5 events but spanning only 5 minutes — burst, not stable.
    _seed_pattern(tmp_db, n=5, span_seconds=300)
    summary = sweep.run_nightly_sweep(
        window_days=7, db_path=tmp_db,
        codification_db_path=tmp_codification_db,
    )
    assert summary["codification_proposals_opened"] == 0


def test_nightly_sweep_skips_small_cluster(
    tmp_db, tmp_calibration_log, tmp_codification_db,
):
    # Only 3 events — meets pattern boundary but below stable threshold (5).
    start = datetime.now(tz=timezone.utc) - timedelta(hours=120)
    _seed_pattern(tmp_db, n=3, span_seconds=49 * 3600, start=start)
    summary = sweep.run_nightly_sweep(
        window_days=7, db_path=tmp_db,
        codification_db_path=tmp_codification_db,
    )
    assert summary["patterns_detected"] >= 1
    assert summary["codification_proposals_opened"] == 0


def test_nightly_sweep_skips_positive_polarity(
    tmp_db, tmp_calibration_log, tmp_codification_db,
):
    # 5 events, long span, but distinct override_actions → positive polarity.
    base = datetime.now(tz=timezone.utc) - timedelta(hours=120)
    for i in range(5):
        rec = OverrideRecord(
            decision_id=f"DEC-{i}",
            decision_certificate_id=f"EC-{i}",
            override_type="reversal",
            overridden_by_user_id="user-uuid",
            overridden_at=(base + timedelta(hours=i * 11)).isoformat(),
            source_engine="sales-os",
            surface="dashboard",
            original_action="auto_send_proposal",
            override_action=f"action_{i}",  # all distinct
            user_reasoning=f"varying corrections detail row {i:03d}",
            freeform_metadata={"decision_class": "pricing.x"},
        )
        record_override(rec, db_path=tmp_db, emit_to_calibration=False)
    summary = sweep.run_nightly_sweep(
        window_days=7, db_path=tmp_db,
        codification_db_path=tmp_codification_db,
    )
    assert summary["codification_proposals_opened"] == 0


# ── v0.5 — Rate-limit alert ────────────────────────────────────────────────


def test_rate_limit_below_threshold_returns_none(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=5)
    alert = rate_limit.check_rate("user-uuid", db_path=tmp_db)
    assert alert is None


def test_rate_limit_eleventh_override_in_hour_triggers_alert(
    tmp_db, tmp_calibration_log,
):
    # Seed 10 in the last 10 minutes.
    base = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    for i in range(10):
        rec = OverrideRecord(
            decision_id=f"DEC-{i}",
            decision_certificate_id=f"EC-{i}",
            override_type="reversal",
            overridden_by_user_id="hot-user",
            overridden_at=(base + timedelta(seconds=i * 10)).isoformat(),
            source_engine="sales-os",
            surface="dashboard",
            original_action="x",
            override_action="y",
            user_reasoning=f"rate limit fixture row #{i:03d} OK",
            freeform_metadata={"decision_class": "pricing.x"},
        )
        record_override(rec, db_path=tmp_db, emit_to_calibration=False)
    # 11th — should breach.
    rec11 = OverrideRecord(
        decision_id="DEC-11",
        decision_certificate_id="EC-11",
        override_type="reversal",
        overridden_by_user_id="hot-user",
        overridden_at=datetime.now(tz=timezone.utc).isoformat(),
        source_engine="sales-os",
        surface="dashboard",
        original_action="x",
        override_action="y",
        user_reasoning="this 11th override should breach the per-hour cap",
        freeform_metadata={"decision_class": "pricing.x"},
    )
    record_override(rec11, db_path=tmp_db, emit_to_calibration=False)
    # Manually call check_rate to see the alert payload.
    alert = rate_limit.check_rate("hot-user", db_path=tmp_db)
    assert alert is not None
    assert alert["severity"] == "WARNING"
    assert alert["count_in_window"] == 11
    assert alert["overrider_user_id"] == "hot-user"


def test_rate_limit_does_not_block_override(tmp_db, tmp_calibration_log):
    # Seed 11; the 12th must still persist successfully.
    base = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    for i in range(11):
        rec = OverrideRecord(
            decision_id=f"DEC-{i}",
            decision_certificate_id=f"EC-{i}",
            override_type="reversal",
            overridden_by_user_id="hot-user",
            overridden_at=(base + timedelta(seconds=i * 10)).isoformat(),
            source_engine="sales-os",
            surface="dashboard",
            original_action="x",
            override_action="y",
            user_reasoning=f"non-blocking rate limit row {i:03d}",
            freeform_metadata={"decision_class": "pricing.x"},
        )
        record_override(rec, db_path=tmp_db, emit_to_calibration=False)
    rec12 = _new_record(overridden_by_user_id="hot-user")
    out = record_override(rec12, db_path=tmp_db, emit_to_calibration=False)
    assert out["override_id"] == rec12.override_id


# ── v0.5 — Drift signal ────────────────────────────────────────────────────


def test_drift_signal_fires_when_rate_at_threshold(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=10, decision_class="pricing.decay")
    # 10 overrides on a class that had 100 decisions → 10% → meets threshold.
    signals = drift_signal.detect_drift_signals(
        decision_counts={"pricing.decay": 100},
        db_path=tmp_db,
    )
    assert len(signals) == 1
    s = signals[0]
    assert s.rule_id == "OVERRIDE-RATE-DECAY"
    assert s.decision_class == "pricing.decay"
    assert s.override_rate_14d == 0.10
    assert s.sample_size == 100


def test_drift_signal_silent_below_threshold(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=5, decision_class="pricing.healthy")
    # 5/100 = 5% — below threshold.
    signals = drift_signal.detect_drift_signals(
        decision_counts={"pricing.healthy": 100},
        db_path=tmp_db,
    )
    assert signals == []


def test_drift_signal_skips_small_samples(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=3, decision_class="pricing.tiny")
    # Total decisions 5 → below MIN_SAMPLE_SIZE.
    signals = drift_signal.detect_drift_signals(
        decision_counts={"pricing.tiny": 5},
        db_path=tmp_db,
    )
    assert signals == []


# ── v0.5 — Anonymization / cross-org view ──────────────────────────────────


def test_hash_user_id_is_stable():
    a = anonymize.hash_user_id("matt@gigaton.ai")
    b = anonymize.hash_user_id("matt@gigaton.ai")
    assert a == b
    assert a.startswith("anon:")
    assert "matt" not in a
    assert "gigaton" not in a


def test_hash_user_id_differs_per_user():
    a = anonymize.hash_user_id("matt@gigaton.ai")
    b = anonymize.hash_user_id("bella@gigaton.ai")
    assert a != b


def test_redact_row_removes_raw_user_id():
    row = {
        "override_id": "abc",
        "overridden_by_user_id": "matt@gigaton.ai",
        "override_type": "reversal",
    }
    redacted = anonymize.redact_row(row)
    assert "matt@gigaton.ai" not in str(redacted.values())
    assert redacted["overridden_by_user_id"].startswith("anon:")
    # Original dict not mutated:
    assert row["overridden_by_user_id"] == "matt@gigaton.ai"


def test_cross_org_view_redacts_all_user_ids(tmp_db, tmp_calibration_log):
    _seed_pattern(tmp_db, n=3, user_id="matt@gigaton.ai")
    _seed_pattern(
        tmp_db, n=3, user_id="bella@gigaton.ai",
        decision_class="other.class",
    )
    # Read everything and redact.
    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM human_overrides"
        ).fetchall()]
    redacted = [anonymize.redact_row(r) for r in rows]
    serialized = json.dumps(redacted)
    assert "matt@gigaton.ai" not in serialized
    assert "bella@gigaton.ai" not in serialized
    for r in redacted:
        assert r["overridden_by_user_id"].startswith("anon:")
