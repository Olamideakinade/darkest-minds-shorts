"""Google Gemini API model provider for high-velocity script generation and trend intelligence."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from app.config import config
from app.intelligence.model_provider import ModelProvider, ModelResponse
from app.utils.logger import logger


class GoogleGeminiProvider(ModelProvider):
    """Google Gemini AI provider supporting Gemini 2.0 Flash / 1.5 Flash."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: int = 45,
    ) -> None:
        self.api_key = api_key if api_key is not None else getattr(config, "gemini_api_key", "")
        self.model = model if model is not None else getattr(config, "gemini_model", "gemini-flash-lite-latest")
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        """Return True if an API key is present."""
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> ModelResponse:
        """Generate text completion from Google Gemini API with candidate model failover."""
        if not self.is_available():
            logger.warning("GeminiProvider: GEMINI_API_KEY is not configured. Falling back to default provider.")
            from app.intelligence.ollama_client import FallbackProvider
            return FallbackProvider().generate(prompt=prompt, system_prompt=system_prompt)

        # Build list of candidate models starting with requested model
        candidate_models = [self.model]
        for fallback_m in ("gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash"):
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        req_data = json.dumps(payload).encode("utf-8")

        for current_model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts).strip()
                            if text:
                                return ModelResponse(
                                    content=text,
                                    model_name=current_model,
                                    provider="gemini",
                                    is_fallback=False,
                                    metadata={
                                        "finish_reason": candidates[0].get("finishReason"),
                                        "usage_metadata": data.get("usageMetadata", {}),
                                    },
                                )
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8")
                except Exception:
                    pass
                logger.warning(
                    f"Gemini API model {current_model} error HTTP {e.code}: {e.reason} ({err_body[:100]}). Trying next candidate..."
                )
                continue
            except Exception as e:
                logger.warning(f"Gemini API model {current_model} request failed: {e}. Trying next candidate...")
                continue

        logger.warning("All Gemini candidate models failed. Falling back to rule-based generation.")
        from app.intelligence.ollama_client import FallbackProvider
        return FallbackProvider().generate(prompt=prompt, system_prompt=system_prompt)
