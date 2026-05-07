from api.providers.base import AIProviderAdapter
from api.providers.claude_provider import ClaudeProvider
from api.providers.openai_provider import OpenAIProvider
from api.providers.gemini_provider import GeminiProvider
from api.models import AIProvider

_PROVIDERS: dict[AIProvider, AIProviderAdapter] = {
    AIProvider.CLAUDE: ClaudeProvider(),
    AIProvider.OPENAI: OpenAIProvider(),
    AIProvider.GEMINI: GeminiProvider(),
}


def get_provider(provider: AIProvider) -> AIProviderAdapter:
    p = _PROVIDERS.get(provider)
    if p is None:
        raise ValueError(f"No provider registered for: {provider}")
    return p


def available_providers() -> list[str]:
    return [p.value for p, adapter in _PROVIDERS.items() if adapter.is_available]
