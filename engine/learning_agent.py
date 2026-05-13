"""
learning_agent.py
Processes context provided by human agents, extracts structured knowledge,
updates memory files, and adjusts decision weights over time.

Fact extraction uses Claude when ANTHROPIC_API_KEY is set, falling back to
heuristic regex extraction so the system works in offline/air-gapped contexts.

Runtime governance: every LLM call carries provider, model, prompt_version,
and schema_version, and is wrapped by `_invoke_llm` which emits an audit
record (per Gigaton Canonical First Principles §6).
"""

from __future__ import annotations
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .memory_manager import MemoryManager
from .decision_engine import DecisionRecord, DecisionStatus

try:
    import anthropic as _anthropic_module
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_anthropic_client: "Any | None" = None
_audit_log = logging.getLogger("decision_engine.llm_audit")

PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-opus-4-6"
PROMPT_VERSION_FACT_EXTRACT = "fact_extract.v1.0"
SCHEMA_VERSION_FACT_EXTRACT = "facts_array.v1"


def _get_anthropic_client() -> "Any":
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = _anthropic_module.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
    return _anthropic_client


def _claude_available() -> bool:
    return _ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _invoke_llm(
    *,
    provider: str,
    model: str,
    prompt: str,
    prompt_version: str,
    schema_version: str,
    max_tokens: int = 512,
) -> str:
    """Provider-agnostic LLM invocation with mandatory audit envelope."""
    if provider != "anthropic":
        raise NotImplementedError(f"Provider {provider!r} not wired yet")
    client = _get_anthropic_client()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text if message.content else ""
    _audit_log.info(
        "llm_call provider=%s model=%s prompt_version=%s schema_version=%s "
        "in_chars=%d out_chars=%d",
        provider, model, prompt_version, schema_version,
        len(prompt), len(text),
    )
    return text


@dataclass
class LearningEvent:
    event_id: str
    agent_uid: str
    domain: str
    raw_input: str
    extracted_facts: list[str]
    memory_ids_updated: list[str]
    confidence_delta: float      # how much trust changed as a result
    created_at: str

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "agent_uid": self.agent_uid,
            "domain": self.domain,
            "raw_input": self.raw_input,
            "extracted_facts": self.extracted_facts,
            "memory_ids_updated": self.memory_ids_updated,
            "confidence_delta": self.confidence_delta,
            "created_at": self.created_at,
        }


class LearningAgent:
    """
    Accepts natural-language context from human agents.
    Extracts facts, updates memory, and provides feedback signals
    back to the decision engine (via confidence adjustments).
    """

    def __init__(self, memory: MemoryManager, domain_weights: dict[str, float] | None = None):
        self.memory = memory
        # Per-domain confidence weight adjustments (start neutral)
        self.domain_weights: dict[str, float] = domain_weights or {}
        self._event_log: list[LearningEvent] = []

    # ── Ingestion ─────────────────────────────────────────────────────────────
    def ingest(self, raw_input: str, domain: str, agent_uid: str = "human") -> LearningEvent:
        """
        Main entry point. Accepts free-form human agent context,
        extracts structured facts, writes to memory.
        """
        facts = self._extract_facts(raw_input)
        memory_ids: list[str] = []
        confidence_delta = 0.0

        if facts:
            # Write each fact cluster to memory
            for fact in facts:
                entry = self.memory.upsert(
                    domain=domain,
                    title=self._title_from_fact(fact),
                    body=self._format_fact_body(fact, raw_input, agent_uid),
                    tags=[domain, "human_agent", "learned"],
                    confidence=0.75,
                    source="human_agent",
                )
                memory_ids.append(entry.memory_id)

            # Positive signal: human is providing context → raise domain weight
            confidence_delta = min(0.05, len(facts) * 0.01)
            self.domain_weights[domain] = min(
                1.0, self.domain_weights.get(domain, 1.0) + confidence_delta
            )

        event = LearningEvent(
            event_id=str(uuid.uuid4()),
            agent_uid=agent_uid,
            domain=domain,
            raw_input=raw_input,
            extracted_facts=facts,
            memory_ids_updated=memory_ids,
            confidence_delta=confidence_delta,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._event_log.append(event)
        return event

    def feedback_on_decision(
        self,
        record: DecisionRecord,
        approved: bool,
        agent_uid: str = "human",
        reason: str = "",
    ) -> LearningEvent:
        """
        Called when a human approves or rejects an escalated decision.
        Updates memory with outcome and adjusts domain weights.
        """
        domain = record.context.domain
        outcome = "approved" if approved else "rejected"
        delta = 0.02 if approved else -0.03

        self.domain_weights[domain] = max(
            0.5, min(1.0, self.domain_weights.get(domain, 1.0) + delta)
        )

        body = (
            f"## Decision feedback\n\n"
            f"**Outcome:** {outcome}\n"
            f"**Reason:** {reason or 'none provided'}\n"
            f"**Action:** {record.selected_option.action if record.selected_option else 'none'}\n"
            f"**Confidence at decision time:** {record.confidence:.2f}\n"
            f"**Situation:** {record.context.situation}\n"
        )

        entry = self.memory.create(
            domain=domain,
            title=f"Feedback: {outcome} — {record.selected_option.action if record.selected_option else 'unknown'}",
            body=body,
            tags=[domain, "feedback", outcome, "human_agent"],
            confidence=0.9,
            source="human_agent",
        )

        event = LearningEvent(
            event_id=str(uuid.uuid4()),
            agent_uid=agent_uid,
            domain=domain,
            raw_input=reason,
            extracted_facts=[f"{outcome}: {reason}"],
            memory_ids_updated=[entry.memory_id],
            confidence_delta=delta,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._event_log.append(event)
        return event

    def bulk_ingest(self, entries: list[dict[str, str]]) -> list[LearningEvent]:
        """
        entries: list of {"input": str, "domain": str, "agent_uid": str}
        """
        return [
            self.ingest(e["input"], e.get("domain", "general"), e.get("agent_uid", "human"))
            for e in entries
        ]

    # ── Fact extraction ───────────────────────────────────────────────────────
    def _extract_facts(self, text: str) -> list[str]:
        """
        Extract discrete, actionable facts from free-form human agent input.

        Uses Claude when available for higher-quality semantic extraction.
        Falls back to heuristic regex extraction in offline/unconfigured contexts.
        """
        if _claude_available():
            return self._extract_facts_claude(text)
        return self._extract_facts_heuristic(text)

    def _extract_facts_claude(self, text: str) -> list[str]:
        """Use Claude to extract structured facts from human agent input."""
        try:
            prompt = (
                "Extract the discrete, actionable facts from this human agent input. "
                "Return ONLY a JSON array of strings — each string is one fact. "
                "Omit filler, meta-commentary, and anything not directly useful as "
                "institutional knowledge.\n\n"
                f"INPUT:\n{text}\n\n"
                "Return ONLY a JSON array like: [\"fact 1\", \"fact 2\"]"
            )
            raw = _invoke_llm(
                provider=PROVIDER,
                model=DEFAULT_MODEL,
                prompt=prompt,
                prompt_version=PROMPT_VERSION_FACT_EXTRACT,
                schema_version=SCHEMA_VERSION_FACT_EXTRACT,
                max_tokens=512,
            )
            match = re.search(r"\[[\s\S]*\]", raw or "[]")
            if match:
                import json
                facts = json.loads(match.group(0))
                if isinstance(facts, list):
                    return [str(f) for f in facts if str(f).strip()]
        except Exception:
            pass  # fall through to heuristic
        return self._extract_facts_heuristic(text)

    def _extract_facts_heuristic(self, text: str) -> list[str]:
        """
        Heuristic extraction of discrete facts from free-form text.
        Each sentence/bullet that looks like a fact is kept.
        """
        facts: list[str] = []

        # Split on bullets, numbered lists, or sentence boundaries
        chunks = re.split(r"(?:^|\n)\s*[-*•\d+\.]\s+|\.\s+", text)
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 12:
                continue
            # Skip meta-commentary phrases
            if re.match(r"^(i think|just to|note that|fyi|btw|also)", chunk.lower()):
                continue
            facts.append(chunk)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for f in facts:
            key = re.sub(r"\s+", " ", f.lower())
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    def _title_from_fact(self, fact: str) -> str:
        # Use first 72 characters of the fact as title
        title = re.sub(r"\s+", " ", fact.strip())
        return title[:72] + ("…" if len(title) > 72 else "")

    def _format_fact_body(self, fact: str, raw_input: str, agent_uid: str) -> str:
        return (
            f"## Learned fact\n\n{fact}\n\n"
            f"## Original context\n\n{raw_input.strip()}\n\n"
            f"## Source\n\nHuman agent: `{agent_uid}`\n"
        )

    # ── Introspection ─────────────────────────────────────────────────────────
    @property
    def events(self) -> list[LearningEvent]:
        return list(self._event_log)

    def domain_weight(self, domain: str) -> float:
        return self.domain_weights.get(domain, 1.0)

    def summary(self) -> dict:
        return {
            "total_events": len(self._event_log),
            "domain_weights": dict(self.domain_weights),
            "memory_stats": self.memory.stats(),
        }
