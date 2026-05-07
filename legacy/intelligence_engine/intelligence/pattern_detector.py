"""
intelligence/pattern_detector.py
Scans SQLite decisions + outcomes tables to find recurring patterns.
A pattern is a statistically significant recurrence of
(decision_class, outcome_cluster, variance_direction) triples.
"""

import sys
import os
import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence.db import DatabaseManager


@dataclass
class Pattern:
    pattern_id: str
    pattern_type: str           # "recurrence" | "outcome_cluster" | "trust_gap" | "verdict_cluster"
    decision_class: str
    description: str
    supporting_decision_ids: list[str]
    confidence_score: float     # 0.0 - 1.0
    occurrence_count: int
    first_seen: str
    last_seen: str
    status: str = "active"


def _fingerprint(pattern_type: str, decision_class: str, description: str) -> str:
    """Deterministic ID for deduplication."""
    import hashlib
    raw = f"{pattern_type}:{decision_class}:{description}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def detect_verdict_clusters(db: DatabaseManager, min_occurrences: int = 2) -> list[Pattern]:
    """
    Find recurring (decision_class, verdict) combinations.
    A verdict cluster means the same class consistently produces the same verdict.
    """
    decisions = db.get_all_decisions()
    patterns: list[Pattern] = []

    if not decisions:
        return patterns

    # Group by (class, verdict)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for d in decisions:
        key = (d["decision_class"], d["verdict"])
        groups[key].append(d)

    class_totals = Counter(d["decision_class"] for d in decisions)

    for (dclass, verdict), members in groups.items():
        if len(members) < min_occurrences:
            continue

        total_in_class = class_totals.get(dclass, 1)
        consistency = len(members) / total_in_class
        confidence = min(1.0, consistency * (len(members) / max(3, len(members))))

        desc = f"{dclass} decisions consistently produce verdict '{verdict}' ({len(members)}/{total_in_class})"
        pid = _fingerprint("verdict_cluster", dclass, desc)

        patterns.append(Pattern(
            pattern_id=pid,
            pattern_type="verdict_cluster",
            decision_class=dclass,
            description=desc,
            supporting_decision_ids=[m["decision_id"] for m in members],
            confidence_score=round(confidence, 3),
            occurrence_count=len(members),
            first_seen=min(m["created_at"] for m in members),
            last_seen=max(m["created_at"] for m in members),
        ))

    return patterns


def detect_trust_gap_patterns(db: DatabaseManager, low_trust_threshold: float = 15.0) -> list[Pattern]:
    """
    Find decision classes where trust_total is systematically low.
    Signals poor scoring inputs or miscalibrated thresholds.
    """
    decisions = db.get_all_decisions()
    patterns: list[Pattern] = []

    if not decisions:
        return patterns

    by_class: dict[str, list[dict]] = defaultdict(list)
    for d in decisions:
        by_class[d["decision_class"]].append(d)

    for dclass, members in by_class.items():
        trusts = [m["trust_total"] for m in members if m["trust_total"] is not None]
        if len(trusts) < 2:
            continue

        avg_trust = sum(trusts) / len(trusts)
        low_count = sum(1 for t in trusts if t < low_trust_threshold)

        if low_count / len(trusts) >= 0.5:
            confidence = low_count / len(trusts)
            desc = (
                f"{dclass} decisions have systematically low trust_total "
                f"(avg={avg_trust:.1f}, {low_count}/{len(trusts)} below {low_trust_threshold})"
            )
            pid = _fingerprint("trust_gap", dclass, desc)

            patterns.append(Pattern(
                pattern_id=pid,
                pattern_type="trust_gap",
                decision_class=dclass,
                description=desc,
                supporting_decision_ids=[m["decision_id"] for m in members],
                confidence_score=round(confidence, 3),
                occurrence_count=low_count,
                first_seen=min(m["created_at"] for m in members),
                last_seen=max(m["created_at"] for m in members),
            ))

    return patterns


def detect_outcome_correlation_patterns(db: DatabaseManager, min_outcomes: int = 2) -> list[Pattern]:
    """
    Join decisions + outcomes to find which trust_tier predicts positive variance.
    Which decision_class has the highest risk_surprise rate?
    """
    paired = db.get_decisions_with_outcomes()
    patterns: list[Pattern] = []

    if len(paired) < min_outcomes:
        return patterns

    # Group by (class, trust_tier) → variance direction
    by_tier: dict[tuple, list[dict]] = defaultdict(list)
    for row in paired:
        key = (row["decision_class"], row["trust_tier"])
        by_tier[key].append(row)

    for (dclass, tier), rows in by_tier.items():
        if len(rows) < min_outcomes:
            continue

        pos = sum(1 for r in rows if (r["composite_variance_score"] or 0) > 0)
        neg = sum(1 for r in rows if (r["composite_variance_score"] or 0) < 0)
        direction = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        confidence = abs(pos - neg) / len(rows)

        if confidence < 0.3:
            continue

        desc = (
            f"{dclass} decisions at trust tier {tier} show {direction} outcome variance "
            f"({pos} positive, {neg} negative of {len(rows)} outcomes)"
        )
        pid = _fingerprint("outcome_cluster", dclass, desc)

        patterns.append(Pattern(
            pattern_id=pid,
            pattern_type="outcome_cluster",
            decision_class=dclass,
            description=desc,
            supporting_decision_ids=[r["decision_id"] for r in rows],
            confidence_score=round(confidence, 3),
            occurrence_count=len(rows),
            first_seen=min(r["created_at"] for r in rows),
            last_seen=max(r["created_at"] for r in rows),
        ))

    # Risk surprise pattern
    risk_surprises = [r for r in paired if r.get("risk_surprise") == 1]
    if len(risk_surprises) >= min_outcomes:
        class_counts = Counter(r["decision_class"] for r in risk_surprises)
        for dclass, count in class_counts.items():
            if count >= min_outcomes:
                total = sum(1 for r in paired if r["decision_class"] == dclass)
                rate = count / total
                if rate >= 0.3:
                    desc = (
                        f"{dclass} has elevated risk_surprise rate: "
                        f"{count}/{total} ({rate:.0%}) outcomes had unexpected risk materialization"
                    )
                    pid = _fingerprint("risk_surprise", dclass, desc)
                    patterns.append(Pattern(
                        pattern_id=pid,
                        pattern_type="outcome_cluster",
                        decision_class=dclass,
                        description=desc,
                        supporting_decision_ids=[r["decision_id"] for r in risk_surprises
                                                  if r["decision_class"] == dclass],
                        confidence_score=round(rate, 3),
                        occurrence_count=count,
                        first_seen=datetime.utcnow().isoformat(),
                        last_seen=datetime.utcnow().isoformat(),
                    ))

    return patterns


def detect_patterns(db: DatabaseManager, min_occurrences: int = 2) -> list[Pattern]:
    """
    Master pattern detection — runs all detectors and persists results.
    Returns deduplicated list of active patterns.
    """
    all_patterns: list[Pattern] = []
    all_patterns.extend(detect_verdict_clusters(db, min_occurrences))
    all_patterns.extend(detect_trust_gap_patterns(db))
    all_patterns.extend(detect_outcome_correlation_patterns(db, min_occurrences))

    # Persist to DB (deduplication via INSERT OR REPLACE on pattern_id)
    for p in all_patterns:
        db.store_pattern({
            "pattern_id": p.pattern_id,
            "pattern_type": p.pattern_type,
            "decision_class": p.decision_class,
            "description": p.description,
            "supporting_decision_ids": p.supporting_decision_ids,
            "confidence_score": p.confidence_score,
            "occurrence_count": p.occurrence_count,
            "first_seen": p.first_seen,
            "last_seen": p.last_seen,
            "status": p.status,
        })

    return all_patterns
