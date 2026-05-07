"""
Translation layer — provider-specific prompt encoders.

Implements the Speech 101 principle:
  The sender's responsibility is to encode the message
  in the form it will be best received by that specific receiver.
"""

from api.translation.base import ProviderEncoder, EncodedPrompt
from api.translation.claude_encoder import ClaudeEncoder
from api.translation.openai_encoder import OpenAIEncoder
from api.translation.gemini_encoder import GeminiEncoder
from api.models import AIProvider


_ENCODERS: dict[AIProvider, ProviderEncoder] = {
    AIProvider.CLAUDE:  ClaudeEncoder(),
    AIProvider.OPENAI:  OpenAIEncoder(),
    AIProvider.GEMINI:  GeminiEncoder(),
}


def get_encoder(provider: AIProvider) -> ProviderEncoder:
    encoder = _ENCODERS.get(provider)
    if encoder is None:
        raise ValueError(f"No encoder registered for provider: {provider}")
    return encoder
