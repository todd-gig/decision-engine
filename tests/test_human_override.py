"""human_override — recorder + classification taxonomy."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.human_override import (
    OverrideRecord,
    OverrideType,
    classify_override,
    record_override,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "human_overrides.db")


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


def test_record_override_writes_row(tmp_db):
    rec = _new_record()
    out = record_override(rec, db_path=tmp_db)
    assert out["override_id"] == rec.override_id
    assert out["classification"]["ovs_weight"] == 3.0

    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT classification FROM human_overrides")
        row = cur.fetchone()
        assert row is not None
        cls = json.loads(row[0])
        assert cls["type"] == "reversal"
        assert cls["ovs_weight"] == 3.0


def test_record_override_persists_user_reasoning(tmp_db):
    rec = _new_record(user_reasoning="this is the always-record-WHY field")
    record_override(rec, db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT user_reasoning FROM human_overrides")
        row = cur.fetchone()
        assert "always-record-WHY" in row[0]


def test_record_override_persists_freeform_metadata_as_json(tmp_db):
    rec = _new_record(freeform_metadata={"opportunity_id": "opp-1", "amount": 25000})
    record_override(rec, db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT freeform_metadata FROM human_overrides")
        meta = json.loads(cur.fetchone()[0])
        assert meta["opportunity_id"] == "opp-1"
        assert meta["amount"] == 25000


def test_two_records_both_persist(tmp_db):
    record_override(_new_record(decision_id="DEC-1"), db_path=tmp_db)
    record_override(_new_record(decision_id="DEC-2", override_type="modification"),
                    db_path=tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM human_overrides").fetchone()[0]
        assert n == 2
