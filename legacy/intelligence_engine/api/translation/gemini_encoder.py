"""
api/translation/gemini_encoder.py — Google Gemini-specific prompt encoder.

GEMINI RECEPTION PROFILE:
  Gemini uses a strict separation between system_instruction and user contents.
  system_instruction is a top-level field — NOT a message in the contents array.
  Contents array uses {role: "user" | "model", parts: [{text: "..."}]} format.
  Gemini responds well to task-framing that is explicit about output structure.
  Safety settings can be configured to prevent over-filtering on business content.
  generationConfig controls temperature, topP, topK, maxOutputTokens.

ENCODING STRATEGY:
  - system_instruction: role + constraints (separate from contents)
  - Context + directives: in the system_instruction (not injected into user turn)
  - Contents: clean user message — no context pollution in the user role
  - History: "user"/"model" (not "assistant") role keys
  - Safety settings: business-appropriate thresholds
"""

from __future__ import annotations
from api.models import ChatMessage, EngineInsight, AIProvider
from api.translation.base import ProviderEncoder, EncodedPrompt


_GEMINI_TEMPERATURE: dict[str, float] = {
    "pricing":             0.1,
    "lead_management":     0.2,
    "decision_governance": 0.0,
    "analytics":           0.1,
    "content_generation":  0.8,
    "explanation":         0.4,
    "strategy":            0.5,
    "automation":          0.2,
    "general":             0.4,
}


class GeminiEncoder(ProviderEncoder):

    @property
    def provider(self) -> AIProvider:
        return AIProvider.GEMINI

    def encode(
        self,
        user_message: str,
        engine_insight: EngineInsight,
        history: list[ChatMessage],
        entity_context: str,
    ) -> EncodedPrompt:

        system_instruction = self._build_system_instruction(engine_insight, entity_context)
        contents = self._build_contents(history)
        temperature = _GEMINI_TEMPERATURE.get(engine_insight.intent_type, 0.4)

        return EncodedPrompt(
            provider=AIProvider.GEMINI,
            system_prompt=system_instruction,
            messages=contents,
            user_message=user_message,
            metadata={
                "model": "gemini-2.0-flash",
                "generationConfig": {
                    "temperature": temperature,
                    "topP": 0.95,
                    "topK": 40,
                    "maxOutputTokens": 2048,
                },
                # Business content safety — block only explicit harm, not business terms
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
                ],
            },
        )

    def _build_system_instruction(self, insight: EngineInsight, entity_context: str) -> str:
        """
        Gemini system_instruction: full context + directives here,
        keeping the user contents array clean.
        """
        directives = self._format_engine_notes(insight.engine_notes)
        return (
            f"You are the Gigaton AI assistant operating within the {insight.entity_context} entity context.\n\n"
            f"OPERATIONAL CONTEXT:\n"
            f"Domain: {insight.relevant_domain}\n"
            f"Intent: {insight.intent_type} (confidence: {insight.intent_confidence:.0%})\n"
            f"Trust tier: {insight.trust_tier}\n"
            f"Requested depth: {insight.suggested_depth}\n\n"
            f"DIRECTIVES:\n{directives}\n\n"
            f"RESPONSE RULES:\n"
            f"- Lead with the answer. No preamble.\n"
            f"- Label all assumptions explicitly.\n"
            f"- Depth: {insight.suggested_depth}.\n"
            f"- No filler affirmations."
        )

    def _build_contents(self, history: list[ChatMessage]) -> list[dict]:
        """
        Gemini contents array. Note: role key is 'model', not 'assistant'.
        """
        tail = self._history_tail(history)
        result = []
        for msg in tail:
            if msg.role.value == "user":
                result.append({"role": "user",  "parts": [{"text": msg.content}]})
            elif msg.role.value == "assistant":
                result.append({"role": "model", "parts": [{"text": msg.content}]})
        return result
