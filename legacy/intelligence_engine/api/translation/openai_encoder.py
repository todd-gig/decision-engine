"""
api/translation/openai_encoder.py — OpenAI/ChatGPT-specific prompt encoder.

OPENAI RECEPTION PROFILE:
  OpenAI models receive best with a concise, direct system role message.
  Overly long system prompts dilute instruction weight — keep it dense.
  Context is best delivered inline within the user turn (not in system).
  Role definition ("You are a ...") is the highest-weight instruction.
  JSON mode available for structured output requests.

ENCODING STRATEGY:
  - System message: concise role + critical constraints only
  - Context + engine directives: injected as a "context block" prefixed to
    the user's actual message (inside the user turn, not system)
  - History: standard OpenAI messages array
  - Separate context injection from user intent so the model parses both cleanly
  - Temperature calibrated per intent, lower than Claude defaults (less verbose)
"""

from __future__ import annotations
from api.models import ChatMessage, EngineInsight, AIProvider
from api.translation.base import ProviderEncoder, EncodedPrompt


_OPENAI_TEMPERATURE: dict[str, float] = {
    "pricing":             0.1,
    "lead_management":     0.2,
    "decision_governance": 0.0,
    "analytics":           0.1,
    "content_generation":  0.7,
    "explanation":         0.3,
    "strategy":            0.4,
    "automation":          0.1,
    "general":             0.4,
}

_OPENAI_MODEL: dict[str, str] = {
    "content_generation": "gpt-4o",
    "strategy":           "gpt-4o",
    "default":            "gpt-4o",
}


class OpenAIEncoder(ProviderEncoder):

    @property
    def provider(self) -> AIProvider:
        return AIProvider.OPENAI

    def encode(
        self,
        user_message: str,
        engine_insight: EngineInsight,
        history: list[ChatMessage],
        entity_context: str,
    ) -> EncodedPrompt:

        system_prompt = self._build_system_prompt(engine_insight)
        messages = self._build_messages(history)
        enriched_user_message = self._enrich_user_message(user_message, engine_insight)
        temperature = _OPENAI_TEMPERATURE.get(engine_insight.intent_type, 0.4)
        model = _OPENAI_MODEL.get(engine_insight.intent_type, _OPENAI_MODEL["default"])

        return EncodedPrompt(
            provider=AIProvider.OPENAI,
            system_prompt=system_prompt,
            messages=messages,
            user_message=enriched_user_message,
            metadata={
                "model": model,
                "max_tokens": 2048,
                "temperature": temperature,
            },
        )

    def _build_system_prompt(self, insight: EngineInsight) -> str:
        """
        OpenAI system: role definition + critical rules only.
        Dense and directive — not verbose.
        """
        return (
            f"You are the Gigaton AI assistant for the {insight.entity_context} entity. "
            f"You provide precise, operational intelligence. "
            f"Rules: label all assumptions explicitly; no filler affirmations; "
            f"lead with the most useful information; "
            f"match response depth to: {insight.suggested_depth}."
        )

    def _enrich_user_message(self, user_message: str, insight: EngineInsight) -> str:
        """
        For OpenAI: inject context + directives into the user turn.
        Keeps system prompt short while delivering full context to the model.
        """
        directives = self._format_engine_notes(insight.engine_notes)
        return (
            f"[CONTEXT]\n"
            f"Domain: {insight.relevant_domain} | "
            f"Intent: {insight.intent_type} ({insight.intent_confidence:.0%}) | "
            f"Trust: {insight.trust_tier}\n\n"
            f"[ENGINE DIRECTIVES]\n{directives}\n\n"
            f"[USER REQUEST]\n{user_message}"
        )

    def _build_messages(self, history: list[ChatMessage]) -> list[dict]:
        """OpenAI messages array — history only, enriched user message added by provider."""
        tail = self._history_tail(history)
        result = []
        for msg in tail:
            if msg.role.value in ("user", "assistant"):
                result.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })
        return result
