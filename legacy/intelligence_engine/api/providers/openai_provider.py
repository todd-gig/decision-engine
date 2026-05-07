"""
api/providers/openai_provider.py — OpenAI adapter.
"""

from __future__ import annotations
import os
from typing import AsyncIterator
from api.models import AIProvider
from api.providers.base import AIProviderAdapter
from api.translation.base import EncodedPrompt


class OpenAIProvider(AIProviderAdapter):

    def __init__(self) -> None:
        self._api_key = os.getenv("OPENAI_API_KEY", "")

    @property
    def provider(self) -> AIProvider:
        return AIProvider.OPENAI

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    async def complete(self, prompt: EncodedPrompt) -> str:
        if not self.is_available:
            return self._mock_response(prompt)
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._api_key)
        messages = (
            [{"role": "system", "content": prompt.system_prompt}]
            + list(prompt.messages)
            + [{"role": "user", "content": prompt.user_message}]
        )
        response = await client.chat.completions.create(
            model=prompt.metadata.get("model", "gpt-4o"),
            messages=messages,
            temperature=prompt.metadata.get("temperature", 0.4),
            max_tokens=prompt.metadata.get("max_tokens", 2048),
        )
        return response.choices[0].message.content or ""

    async def stream(self, prompt: EncodedPrompt) -> AsyncIterator[str]:
        if not self.is_available:
            yield self._mock_response(prompt)
            return
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._api_key)
        messages = (
            [{"role": "system", "content": prompt.system_prompt}]
            + list(prompt.messages)
            + [{"role": "user", "content": prompt.user_message}]
        )
        stream = await client.chat.completions.create(
            model=prompt.metadata.get("model", "gpt-4o"),
            messages=messages,
            temperature=prompt.metadata.get("temperature", 0.4),
            max_tokens=prompt.metadata.get("max_tokens", 2048),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def _mock_response(self, prompt: EncodedPrompt) -> str:
        return (
            "[MOCK — OPENAI_API_KEY not set] "
            f"GPT-4o would respond here. User message: {prompt.user_message[:100]}..."
        )
