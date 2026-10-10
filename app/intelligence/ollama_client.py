"""Ollama client implementing local LLM generation for macOS."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from app.config import config
from app.intelligence.model_provider import ModelProvider, ModelResponse
from app.utils.logger import logger


class OllamaProvider(ModelProvider):
    """Local LLM provider interacting with Ollama HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: int = 90,
    ) -> None:
        self.base_url = (base_url or config.ollama_base_url).rstrip("/")
        self.model = model or config.ollama_model
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        """Check if Ollama service is reachable and has the requested model."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    # Check exact or partial match (e.g. llama3.2:1b)
                    return any(self.model in m or m in self.model for m in models) if models else True
        except Exception as e:
            logger.debug(f"Ollama availability check failed: {e}")
        return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> ModelResponse:
        """Generate response using local Ollama model."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status == 200:
                    result = json.loads(resp.read().decode("utf-8"))
                    text = result.get("response", "").strip()
                    return ModelResponse(
                        content=text,
                        model_name=self.model,
                        provider="ollama",
                        is_fallback=False,
                        metadata={
                            "total_duration": result.get("total_duration"),
                            "load_duration": result.get("load_duration"),
                            "eval_count": result.get("eval_count"),
                        },
                    )
        except Exception as e:
            logger.warning(f"Ollama generation failed ({e}). Falling back to rule-based template.")

        # If Ollama is unavailable or fails, use explicit Fallback
        return FallbackProvider().generate(prompt=prompt, system_prompt=system_prompt)


class FallbackProvider(ModelProvider):
    """Rule-based fallback provider when local LLM is offline.

    Explicitly labeled as fallback to avoid misrepresenting generated text as AI reasoning.
    """

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> ModelResponse:
        logger.info("Using rule-based fallback generation (Ollama offline).")
        fallback_text = (
            "In 1911, the Mona Lisa vanished from the Louvre. "
            "For two years, the greatest detectives on earth suspected everybody—even Pablo Picasso. "
            "The real thief? A handyman who hid in a broom closet and walked out with the painting under his coat. "
            "He was caught trying to sell it in Florence. The heist didn't ruin the painting—it made it the most famous artwork in history."
        )
        return ModelResponse(
            content=fallback_text,
            model_name="rule-based-template-v1",
            provider="fallback",
            is_fallback=True,
            metadata={"note": "Generated via deterministic fallback template. Local LLM offline."},
        )


def get_model_provider() -> ModelProvider:
    """Return configured model provider instance."""
    if config.model_provider == "ollama":
        provider = OllamaProvider()
        if provider.is_available():
            return provider
        logger.warning(
            f"Ollama provider configured but '{config.ollama_model}' not available or service stopped. Using FallbackProvider."
        )
        return FallbackProvider()

    return FallbackProvider()
