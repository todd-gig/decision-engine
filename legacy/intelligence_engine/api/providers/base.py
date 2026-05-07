"""
api/providers/base.py — Abstract AI provider interface.

All three providers (Claude, OpenAI, Gemini) implement this interface.
The chat routes only depend on this abstraction — never on a specific provider SDK.
Swap providers without touching any domain code.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator
from api.models import AIProvider
from api.translation.base import EncodedPrompt


class AIProviderAdapter(ABC):

    @property
    @abstractmethod
    def provider(self) -> AIProvider:
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider API key is configured."""
        ...

    @abstractmethod
    async def complete(self, prompt: EncodedPrompt) -> str:
        """Non-streaming completion. Returns full response text."""
        ...

    @abstractmethod
    async def stream(self, prompt: EncodedPrompt) -> AsyncIterator[str]:
        """Streaming completion. Yields text chunks as they arrive."""
        ...
