from functools import lru_cache

from app.core.config import get_settings
from app.services.ai.base import AIProvider
from app.services.ai.mock_provider import MockAIProvider


@lru_cache
def get_ai_provider() -> AIProvider:
    """Single place that decides which AI backend is live.

    Add a new provider by writing a class + one new branch here — routers
    and services never need to know which provider is active.
    """
    settings = get_settings()
    provider = settings.AI_PROVIDER.lower()

    if provider == "mock":
        return MockAIProvider()
    if provider == "ollama":
        from app.services.ai.ollama_provider import OllamaProvider

        return OllamaProvider()
    if provider == "hybrid":
        from app.services.ai.hybrid_provider import HybridAIProvider

        return HybridAIProvider()
    if provider == "openai":
        from app.services.ai.openai_provider import OpenAIProvider

        return OpenAIProvider()

    raise ValueError(f"Unknown AI_PROVIDER '{provider}'. Add a provider in services/ai/.")


def reset_ai_provider_cache() -> None:
    """Forget the cached provider (used by tests to switch providers)."""
    get_ai_provider.cache_clear()
