"""Unit tests for LLM providers and fallback behavior."""

from app.intelligence.model_provider import ModelResponse
from app.intelligence.ollama_client import FallbackProvider, OllamaProvider, get_model_provider


def test_fallback_provider():
    provider = FallbackProvider()
    assert provider.is_available() is True
    res = provider.generate("Tell me a story.")
    assert isinstance(res, ModelResponse)
    assert res.is_fallback is True
    assert "Mona Lisa" in res.content
    assert res.provider == "fallback"


def test_get_model_provider():
    provider = get_model_provider()
    assert provider is not None
    # Must provide is_available and generate methods
    assert hasattr(provider, "is_available")
    assert hasattr(provider, "generate")
