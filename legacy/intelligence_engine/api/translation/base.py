"""
api/translation/base.py — Abstract encoder interface.

DESIGN PRINCIPLE (Speech Communication 101):
  It is the job of the SENDER to encode the message in the way
  it will be best received.
  Best = maximum net accuracy of information transfer.

Every AI provider has a different "language":
  - Different system prompt formats
  - Different context structuring conventions
  - Different optimal instruction patterns
  - Different signal-to-noise sensitivities

The encoder's responsibility is to take the same semantic content
(user message + engine insight + conversation history) and
re-encode it into the form that maximises fidelity of reception
by THAT specific provider.

This is NOT about adding filler or decoration.
It is about signal architecture — removing noise, amplifying signal,
and structuring the transmission channel correctly for the receiver.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from api.models import ChatMessage, EngineInsight, AIProvider


@dataclass
class EncodedPrompt:
    """
    Provider-ready prompt structure.
    Each provider adapter receives this and maps it to its own API format.
    """
    provider: AIProvider
    system_prompt: str                      # The encoded system/instruction block
    messages: list[dict]                    # Provider-formatted message history
    user_message: str                       # The final user turn content
    metadata: dict                          # Provider-specific config (temperature, etc.)


class ProviderEncoder(ABC):
    """
    Base encoder. Subclasses implement the provider-specific encoding strategy.

    The encode() method is the implementation of Speech 101:
    take identical semantic content, produce optimal provider-specific encoding.
    """

    @property
    @abstractmethod
    def provider(self) -> AIProvider:
        ...

    @abstractmethod
    def encode(
        self,
        user_message: str,
        engine_insight: EngineInsight,
        history: list[ChatMessage],
        entity_context: str,
    ) -> EncodedPrompt:
        """
        Encode the message + context into the format this provider
        receives with maximum accuracy.
        """
        ...

    def _format_engine_notes(self, notes: list[str]) -> str:
        """Formats engine notes as a numbered directive list."""
        return "\n".join(f"{i+1}. {note}" for i, note in enumerate(notes))

    def _history_tail(self, history: list[ChatMessage], max_turns: int = 10) -> list[ChatMessage]:
        """Return the last N turns, excluding system messages."""
        user_assistant = [m for m in history if m.role.value in ("user", "assistant")]
        return user_assistant[-max_turns:]
