"""
api/providers/gemini_provider.py — Google Gemini adapter.
"""

from __future__ import annotations
import os
from typing import AsyncIterator
from api.models import AIProvider
from api.providers.base import AIProviderAdapter
from api.translation.base import EncodedPrompt


class GeminiProvider(AIProviderAdapter):

    def __init__(self) -> None:
        self._api_key = os.getenv("GEMINI_API_KEY", "")

    @property
    def provider(self) -> AIProvider:
        return AIProvider.GEMINI

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    async def complete(self, prompt: EncodedPrompt) -> str:
        if not self.is_available:
            return self._mock_response(prompt)
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        gen_config = prompt.metadata.get("generationConfig", {})
        safety = prompt.metadata.get("safetySettings", [])
        model = genai.GenerativeModel(
            model_name=prompt.metadata.get("model", "gemini-2.0-flash"),
            system_instruction=prompt.system_prompt,
            generation_config=gen_config,
            safety_settings=safety,
        )
        # Build contents: history + new user turn
        contents = list(prompt.messages) + [
            {"role": "user", "parts": [{"text": prompt.user_message}]}
        ]
        response = await model.generate_content_async(contents)
        return response.text

    async def stream(self, prompt: EncodedPrompt) -> AsyncIterator[str]:
        if not self.is_available:
            yield self._mock_response(prompt)
            return
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        gen_config = prompt.metadata.get("generationConfig", {})
        safety = prompt.metadata.get("safetySettings", [])
        model = genai.GenerativeModel(
            model_name=prompt.metadata.get("model", "gemini-2.0-flash"),
            system_instruction=prompt.system_prompt,
            generation_config=gen_config,
            safety_settings=safety,
        )
        contents = list(prompt.messages) + [
            {"role": "user", "parts": [{"text": prompt.user_message}]}
        ]
        async for chunk in await model.generate_content_async(contents, stream=True):
            if chunk.text:
                yield chunk.text

    def _mock_response(self, prompt: EncodedPrompt) -> str:
        return (
            "[MOCK — GEMINI_API_KEY not set] "
            f"Gemini would respond here. User message: {prompt.user_message[:100]}..."
        )
