"""Abstract interface for LLM providers with safety guards and fallback tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ModelResponse:
    """Standardized response from any model provider."""
    content: str
    model_name: str
    provider: str
    is_fallback: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.content


class ModelProvider(ABC):
    """Abstract interface for all model providers (Ollama, local, future cloud)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is currently reachable and ready."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> ModelResponse:
        """Generate text completion from prompt."""
        pass
