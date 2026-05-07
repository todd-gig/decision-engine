"""
api/engine_middleware.py — Pre-AI processing pipeline.

This is the decision engine's entry point into every chat message.
It runs BEFORE the message reaches any AI provider.

Pipeline:
  1. Decode intent  — what is the user actually asking?
  2. Classify domain — which Gigaton system / entity does this touch?
  3. Enrich context — pull relevant entity + user context
  4. Score the query — run a lightweight RTQL-derived trust/relevance score
  5. Assemble engine notes — explicit directives the AI must honour

Output: EngineInsight — a structured context block that is injected into
every provider's encoded prompt via the translation layer.
"""

from __future__ import annotations
import re
from typing import Optional
from api.models import EngineInsight, ConversationSession


# ── Intent Classification ─────────────────────────────────────────────────────

# Maps regex patterns → intent_type label
_INTENT_PATTERNS: list[tuple[str, str]] = [
    (r"\b(price|pricing|rate|cost|fee|quote|revenue|margin|occupancy)\b", "pricing"),
    (r"\b(lead|inquiry|prospect|score|route|qualify|follow.?up)\b",       "lead_management"),
    (r"\b(content|copy|write|description|listing|seo|headline|draft)\b",  "content_generation"),
    (r"\b(decision|approve|block|escalate|execute|verdict|authority)\b",  "decision_governance"),
    (r"\b(report|dashboard|analytics|metric|kpi|performance|insight)\b",  "analytics"),
    (r"\b(automate|workflow|trigger|job|pipeline|schedule)\b",            "automation"),
    (r"\b(property|unit|bedroom|amenity|location|zone|villa|condo)\b",    "property_ops"),
    (r"\b(owner|acquisition|outreach|pitch|contract|deal)\b",             "owner_acquisition"),
    (r"\b(strategy|plan|roadmap|priority|objective|goal)\b",              "strategy"),
    (r"\b(explain|how does|what is|describe|define|help me understand)\b","explanation"),
]

# Maps regex patterns → entity_context label
_ENTITY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(carmen beach|stvr|playa|property|rental|vacation)\b", "carmen_beach"),
    (r"\b(ti solutions|bpo|dialer|outbound|linkedin|lío)\b",    "ti_solutions"),
    (r"\b(liquifex|life settlement|bank note|cagr|fixed income)\b", "liquifex"),
    (r"\b(incontekst|mmm|marketing mix|econometric)\b",          "incontekst"),
    (r"\b(gigaton|platform|engine|system|agent|intelligence)\b", "gigaton"),
]

_DEPTH_SIGNALS: dict[str, str] = {
    "brief":    r"\b(quick|brief|short|summary|tldr|tl;dr|one.?line)\b",
    "detailed": r"\b(detail|explain|breakdown|step.?by.?step|thorough|comprehensive)\b",
    "analytical": r"\b(analyse|analyze|why|root cause|compare|evaluate|trade.?off|data)\b",
}


def _classify_intent(text: str) -> tuple[str, float]:
    """Return (intent_type, confidence) for the user's message."""
    text_lower = text.lower()
    matches: list[str] = []
    for pattern, label in _INTENT_PATTERNS:
        if re.search(pattern, text_lower):
            matches.append(label)
    if not matches:
        return "general", 0.5
    # Most frequent label wins; confidence scales with signal density
    from collections import Counter
    top_label = Counter(matches).most_common(1)[0][0]
    confidence = min(0.6 + len(matches) * 0.08, 0.95)
    return top_label, confidence


def _classify_entity(text: str, session_entity: str) -> str:
    text_lower = text.lower()
    for pattern, label in _ENTITY_PATTERNS:
        if re.search(pattern, text_lower):
            return label
    return session_entity  # fall back to session's established entity


def _classify_depth(text: str) -> str:
    text_lower = text.lower()
    for depth, pattern in _DEPTH_SIGNALS.items():
        if re.search(pattern, text_lower):
            return depth
    # Default: longer messages suggest analytical depth
    word_count = len(text.split())
    if word_count > 60:
        return "analytical"
    if word_count > 20:
        return "detailed"
    return "brief"


def _derive_trust_tier(intent_confidence: float, history_length: int) -> str:
    """
    Lightweight trust proxy. Full RTQL is for formal decisions;
    chat queries use a simplified 3-tier proxy:
      T2 = fresh session, low confidence
      T3 = established session or high confidence
      T4 = high confidence + established context
    """
    if intent_confidence >= 0.85 and history_length >= 4:
        return "T4"
    if intent_confidence >= 0.70 or history_length >= 2:
        return "T3"
    return "T2"


def _build_engine_notes(
    intent_type: str,
    entity_context: str,
    depth: str,
    history: list,
) -> list[str]:
    """
    Explicit directives the AI must honour — injected into every provider's
    system prompt via the translation layer.
    """
    notes: list[str] = []

    # Universal notes
    notes.append("You are operating as part of the Gigaton AI platform. Maintain precision and operational clarity.")
    notes.append("Label any assumptions explicitly. Never present estimates as confirmed data.")

    # Intent-specific notes
    intent_notes: dict[str, str] = {
        "pricing":             "When discussing pricing: always include confidence level, explicit assumptions, and a rationale. Never state a number without its basis.",
        "lead_management":     "When discussing leads: reference intent type, score band, and routing logic. Recommend next action.",
        "content_generation":  "When generating content: respect brand voice (direct, precise, no filler). Offer EN and ES variants if property-related.",
        "decision_governance": "When evaluating decisions: apply D-class framing (D1=tactical through D6=irreversible). State required authority tier.",
        "analytics":           "When presenting analytics: distinguish leading indicators from lagging. Note sample size limitations.",
        "automation":          "When designing automation: specify trigger event, action, idempotency considerations, and failure mode.",
        "owner_acquisition":   "When discussing owner acquisition: reference Ti Solutions outreach framework and Carmen Beach owner economics model.",
        "strategy":            "When responding on strategy: ground recommendations in entity-specific constraints and the codification flywheel model.",
        "explanation":         "Explain clearly and concisely. Match depth to the user's apparent familiarity level from conversation history.",
    }
    if intent_type in intent_notes:
        notes.append(intent_notes[intent_type])

    # Depth notes
    if depth == "brief":
        notes.append("Response requested: brief. Lead with the answer. One paragraph maximum.")
    elif depth == "analytical":
        notes.append("Response requested: analytical. Include reasoning, trade-offs, and supporting evidence.")

    # History-aware note
    if len(history) >= 4:
        notes.append("This is an established conversation. Maintain continuity — do not re-introduce concepts already discussed.")

    return notes


# ── Public Entry Point ────────────────────────────────────────────────────────

def process(
    message: str,
    session: ConversationSession,
) -> EngineInsight:
    """
    Run the pre-AI processing pipeline on a user message.
    Returns an EngineInsight that the translation layer will inject
    into the provider-specific prompt encoding.
    """
    history = [m for m in session.messages if m.role.value == "user"]

    intent_type, intent_confidence = _classify_intent(message)
    entity_context = _classify_entity(message, session.entity_context)
    depth = _classify_depth(message)
    trust_tier = _derive_trust_tier(intent_confidence, len(history))
    engine_notes = _build_engine_notes(intent_type, entity_context, depth, history)

    # Lightweight net value proxy — scales with confidence + session depth
    raw_score = round(intent_confidence * 10 + min(len(history), 5) * 0.5, 2)

    return EngineInsight(
        intent_type=intent_type,
        intent_confidence=intent_confidence,
        entity_context=entity_context,
        relevant_domain=f"{entity_context}:{intent_type}",
        trust_tier=trust_tier,
        suggested_depth=depth,
        engine_notes=engine_notes,
        raw_score=raw_score,
    )
