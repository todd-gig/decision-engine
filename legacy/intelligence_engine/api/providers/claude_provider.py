"""
api/providers/claude_provider.py — Anthropic Claude adapter.
"""

from __future__ import annotations
import os
from typing import AsyncIterator
from api.models import AIProvider
from api.providers.base import AIProviderAdapter
from api.translation.base import EncodedPrompt


class ClaudeProvider(AIProviderAdapter):

    def __init__(self) -> None:
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def provider(self) -> AIProvider:
        return AIProvider.CLAUDE

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    async def complete(self, prompt: EncodedPrompt) -> str:
        if not self.is_available:
            return self._mock_response(prompt)
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        messages = list(prompt.messages) + [
            {"role": "user", "content": prompt.user_message}
        ]
        response = await client.messages.create(
            model=prompt.metadata.get("model", "claude-opus-4-6"),
            max_tokens=prompt.metadata.get("max_tokens", 4096),
            temperature=prompt.metadata.get("temperature", 0.5),
            system=prompt.system_prompt,
            messages=messages,
        )
        return response.content[0].text

    async def stream(self, prompt: EncodedPrompt) -> AsyncIterator[str]:
        if not self.is_available:
            yield self._mock_response(prompt)
            return
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        messages = list(prompt.messages) + [
            {"role": "user", "content": prompt.user_message}
        ]
        async with client.messages.stream(
            model=prompt.metadata.get("model", "claude-opus-4-6"),
            max_tokens=prompt.metadata.get("max_tokens", 4096),
            temperature=prompt.metadata.get("temperature", 0.5),
            system=prompt.system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def _mock_response(self, prompt: EncodedPrompt) -> str:
        return (
            "[MOCK — ANTHROPIC_API_KEY not set] "
            f"Claude would respond here. System prompt length: {len(prompt.system_prompt)} chars. "
            f"User message: {prompt.user_message[:100]}..."
        )
