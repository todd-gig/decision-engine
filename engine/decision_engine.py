"""
decision_engine.py
Core decision-making engine. Evaluates options against trust certificates,
auto-executes when confidence exceeds threshold, escalates otherwise.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from .trust_certificates import TrustCertificate, TrustLevel, CertificateAuthority
from .memory_manager import MemoryManager


class DecisionStatus(str, Enum):
    PENDING   = "pending"
    EXECUTED  = "executed"
    ESCALATED = "escalated"
    REJECTED  = "rejected"


@dataclass
class Option:
    action: str                  # action type name
    description: str
    payload: dict[str, Any]      # execution parameters
    estimated_impact: float      # 0.0–1.0 (low→high impact/risk)
    confidence: float = 0.0      # filled by engine scoring


@dataclass
class DecisionContext:
    situation: str               # natural language description
    domain: str
    urgency: float               # 0.0–1.0
    options: list[Option]
    agent_uid: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionRecord:
    decision_id: str
    context: DecisionContext
    cert_id: str | None
    selected_option: Option | None
    status: DecisionStatus
    confidence: float
    reasoning: str
    created_at: str
    executed_at: str | None = None
    human_override: str | None = None

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "domain": self.context.domain,
            "situation": self.context.situation,
            "cert_id": self.cert_id,
            "selected_action": self.selected_option.action if self.selected_option else None,
            "selected_payload": self.selected_option.payload if self.selected_option else None,
            "status": self.status.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "agent_uid": self.context.agent_uid,
            "human_override": self.human_override,
        }


# Action executor type: (action, payload) -> result
ActionExecutor = Callable[[str, dict[str, Any]], Any]


class DecisionEngine:
    def __init__(
        self,
        ca: CertificateAuthority,
        memory: MemoryManager,
        executor: ActionExecutor | None = None,
    ):
        self.ca = ca
        self.memory = memory
        self.executor = executor
        self._certificates: dict[str, TrustCertificate] = {}
        self._decision_log: list[DecisionRecord] = []
        self._escalation_hooks: list[Callable[[DecisionRecord], None]] = []

    # ── Certificate management ─────────────────────────────────────────────────
    def load_certificate(self, cert: TrustCertificate) -> bool:
        """
        Load a certificate into the engine.
        Requires ALL of:
          1. Valid HMAC signature (cryptographic integrity)
          2. Not expired
          3. MD file present on disk (audit trail exists)
          4. MD file signature matches cert (no tamper / file swap)
        """
        if not self.ca.verify(cert):
            return False
        if not cert.md_file_exists():
            return False
        if not cert.md_file_valid():
            return False
        self._certificates[cert.cert_id] = cert
        return True

    def load_certificates(self, certs: list[TrustCertificate]) -> int:
        return sum(1 for c in certs if self.load_certificate(c))

    def _find_cert(self, domain: str, action: str) -> TrustCertificate | None:
        # Re-validate MD file on every lookup — catches files deleted after load
        candidates = [
            c for c in self._certificates.values()
            if c.domain == domain
            and c.allows_action(action)
            and not c.is_expired()
            and c.md_file_valid()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda c: int(c.trust_level))

    # ── Scoring ────────────────────────────────────────────────────────────────
    def _score_option(self, option: Option, cert: TrustCertificate, context: DecisionContext) -> float:
        """
        Score = base_confidence adjusted by:
        - memory relevance (past decisions in domain)
        - urgency boost
        - impact penalty
        - trust level multiplier
        """
        # Start from option's self-reported confidence (or 0.5 if not set)
        score = option.confidence if option.confidence > 0 else 0.5

        # Urgency boost — high urgency leans toward action
        score += context.urgency * 0.1

        # Impact penalty — high-impact actions need more confidence
        score -= option.estimated_impact * 0.15

        # Memory boost — if we've done this action successfully before
        past = self.memory.full_text_search(f"{context.domain} {option.action}", limit=5)
        successful = [m for m in past if "success" in m.body.lower() or "executed" in m.body.lower()]
        score += min(len(successful) * 0.04, 0.12)

        # Trust level multiplier (higher trust = more willing to act)
        trust_mult = {1: 0.5, 2: 0.7, 3: 0.85, 4: 0.95, 5: 1.0}
        score *= trust_mult.get(int(cert.trust_level), 1.0)

        return max(0.0, min(1.0, score))

    # ── Decision pipeline ──────────────────────────────────────────────────────
    def decide(self, context: DecisionContext) -> DecisionRecord:
        now = datetime.now(timezone.utc).isoformat()
        record = DecisionRecord(
            decision_id=str(uuid.uuid4()),
            context=context,
            cert_id=None,
            selected_option=None,
            status=DecisionStatus.PENDING,
            confidence=0.0,
            reasoning="",
            created_at=now,
        )

        if not context.options:
            record.status = DecisionStatus.REJECTED
            record.reasoning = "No options provided."
            self._log(record)
            return record

        # Score each option against its certificate
        best_option: Option | None = None
        best_score = 0.0
        best_cert: TrustCertificate | None = None

        for option in context.options:
            cert = self._find_cert(context.domain, option.action)
            if cert is None:
                continue
            score = self._score_option(option, cert, context)
            option.confidence = score
            if score > best_score:
                best_score = score
                best_option = option
                best_cert = cert

        if best_option is None or best_cert is None:
            # Diagnose: are certs loaded but MD files missing?
            domain_certs = [
                c for c in self._certificates.values()
                if c.domain == context.domain and not c.is_expired()
            ]
            if domain_certs:
                missing_md = [c for c in domain_certs if not c.md_file_exists()]
                invalid_md = [c for c in domain_certs if c.md_file_exists() and not c.md_file_valid()]
                if missing_md:
                    record.reasoning = (
                        f"Certificate(s) for domain '{context.domain}' exist but required MD file(s) "
                        f"are missing: {[c.cert_id[:8] for c in missing_md]}. "
                        f"Restore the MD file or re-issue the certificate."
                    )
                elif invalid_md:
                    record.reasoning = (
                        f"Certificate MD file(s) for domain '{context.domain}' failed signature "
                        f"verification — possible tampering: {[c.cert_id[:8] for c in invalid_md]}."
                    )
                else:
                    record.reasoning = f"No certificate covers the requested action in domain '{context.domain}'."
            else:
                record.reasoning = f"No valid certificate loaded for domain '{context.domain}'. Escalating to human."
            record.status = DecisionStatus.ESCALATED
            self._escalate(record)
            self._log(record)
            return record

        record.cert_id = best_cert.cert_id
        record.selected_option = best_option
        record.confidence = best_score

        # Auto-execute or escalate
        if best_score >= best_cert.auto_execute_threshold and int(best_cert.trust_level) >= TrustLevel.ASSIST:
            record.reasoning = (
                f"Confidence {best_score:.2f} ≥ threshold {best_cert.auto_execute_threshold:.2f}. "
                f"Auto-executing '{best_option.action}' under trust level {int(best_cert.trust_level)}."
            )
            self._execute(record)
        else:
            record.status = DecisionStatus.ESCALATED
            record.reasoning = (
                f"Confidence {best_score:.2f} < threshold {best_cert.auto_execute_threshold:.2f} "
                f"or trust level {int(best_cert.trust_level)} insufficient. Escalating."
            )
            self._escalate(record)

        self._log(record)
        return record

    def _execute(self, record: DecisionRecord) -> None:
        record.status = DecisionStatus.EXECUTED
        record.executed_at = datetime.now(timezone.utc).isoformat()
        if self.executor and record.selected_option:
            try:
                result = self.executor(record.selected_option.action, record.selected_option.payload)
                # Persist execution to memory
                self.memory.upsert(
                    domain=record.context.domain,
                    title=f"Decision: {record.selected_option.action}",
                    body=(
                        f"## Situation\n{record.context.situation}\n\n"
                        f"## Action executed\n`{record.selected_option.action}`\n\n"
                        f"## Result\n{result}\n\n"
                        f"## Confidence\n{record.confidence:.2f}\n\n"
                        f"## Status\nexecuted"
                    ),
                    tags=[record.context.domain, record.selected_option.action, "executed"],
                    confidence=record.confidence,
                    source="engine",
                )
            except Exception as exc:
                record.status = DecisionStatus.ESCALATED
                record.reasoning += f" Execution failed: {exc}"
                self._escalate(record)

    def _escalate(self, record: DecisionRecord) -> None:
        for hook in self._escalation_hooks:
            try:
                hook(record)
            except Exception:
                pass

    def on_escalation(self, hook: Callable[[DecisionRecord], None]) -> None:
        self._escalation_hooks.append(hook)

    def _log(self, record: DecisionRecord) -> None:
        self._decision_log.append(record)

    def human_override(self, decision_id: str, approved: bool, reason: str = "", action: str | None = None, payload: dict | None = None) -> DecisionRecord | None:
        record = next((r for r in self._decision_log if r.decision_id == decision_id), None)
        if not record:
            return None
        record.human_override = reason
        if approved:
            if action and payload and record.selected_option:
                record.selected_option.action = action
                record.selected_option.payload = payload or {}
            self._execute(record)
        else:
            record.status = DecisionStatus.REJECTED
        return record

    @property
    def log(self) -> list[DecisionRecord]:
        return list(self._decision_log)

    def pending(self) -> list[DecisionRecord]:
        return [r for r in self._decision_log if r.status == DecisionStatus.ESCALATED]
