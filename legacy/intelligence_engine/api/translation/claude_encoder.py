"""
api/translation/claude_encoder.py — Claude-specific prompt encoder.

CLAUDE RECEPTION PROFILE:
  Claude receives XML-structured prompts with highest fidelity.
  Distinct tagged blocks eliminate ambiguity about role boundaries.
  Explicit reasoning scaffolding increases output precision.
  Detailed context = better response; Claude is not penalised for long system prompts.

ENCODING STRATEGY:
  - System prompt uses XML tag structure: <role>, <context>, <engine_directives>, <format>
  - Context block carries entity + domain + trust tier
  - Engine directives are numbered and explicit
  - Conversation history is passed as Anthropic messages array (not inlined)
  - Temperature is calibrated to intent type
"""

from __future__ import annotations
from api.models import ChatMessage, EngineInsight, AIProvider
from api.translation.base import ProviderEncoder, EncodedPrompt


# Intent → temperature mapping for Claude
_CLAUDE_TEMPERATURE: dict[str, float] = {
    "pricing":             0.2,   # precise, low variance
    "lead_management":     0.3,
    "decision_governance": 0.1,   # deterministic
    "analytics":           0.2,
    "content_generation":  0.7,   # creative latitude
    "explanation":         0.4,
    "strategy":            0.5,
    "automation":          0.2,
    "general":             0.5,
}


class ClaudeEncoder(ProviderEncoder):

    @property
    def provider(self) -> AIProvider:
        return AIProvider.CLAUDE

    def encode(
        self,
        user_message: str,
        engine_insight: EngineInsight,
        history: list[ChatMessage],
        entity_context: str,
    ) -> EncodedPrompt:

        system_prompt = self._build_system_prompt(engine_insight, entity_context)
        messages = self._build_messages(history)
        temperature = _CLAUDE_TEMPERATURE.get(engine_insight.intent_type, 0.5)

        return EncodedPrompt(
            provider=AIProvider.CLAUDE,
            system_prompt=system_prompt,
            messages=messages,
            user_message=user_message,
            metadata={
                "model": "claude-opus-4-6",
                "max_tokens": 4096,
                "temperature": temperature,
            },
        )

    def _build_system_prompt(self, insight: EngineInsight, entity_context: str) -> str:
        directives = self._format_engine_notes(insight.engine_notes)

        return f"""<role>
You are the Gigaton AI assistant — an intelligence layer embedded in the Gigaton platform.
You operate in the context of a live decision engine that has already analysed this request
before it reached you. Your role is to provide precise, operational intelligence — not
generic advice.
</role>

<context>
Entity: {insight.entity_context}
Domain: {insight.relevant_domain}
Intent classified: {insight.intent_type} (confidence: {insight.intent_confidence:.0%})
Trust tier: {insight.trust_tier}
Response depth: {insight.suggested_depth}
Engine score: {insight.raw_score}
</context>

<engine_directives>
The decision engine has pre-processed this request and issued the following directives.
You MUST honour all of them in your response:

{directives}
</engine_directives>

<format>
- Lead with the most operationally useful information first
- Use structured formatting (headers, tables, bullets) for analytical responses
- For brief requests: one concise paragraph, no preamble
- Always label assumptions explicitly. Never present estimates as facts.
- Avoid filler phrases: "Certainly!", "Great question!", "Of course!" are not permitted
</format>"""

    def _build_messages(self, history: list[ChatMessage]) -> list[dict]:
        """Convert session history to Anthropic messages array format."""
        tail = self._history_tail(history)
        result = []
        for msg in tail:
            if msg.role.value in ("user", "assistant"):
                result.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })
        return result
