"""Unit tests for Google Gemini AI model provider."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from app.config import config
from app.intelligence.gemini_client import GoogleGeminiProvider
from app.intelligence.ollama_client import get_model_provider


def test_gemini_provider_availability():
    provider_no_key = GoogleGeminiProvider(api_key="")
    assert provider_no_key.is_available() is False

    provider_short_key = GoogleGeminiProvider(api_key="123")
    assert provider_short_key.is_available() is False

    provider_valid_key = GoogleGeminiProvider(api_key="AIzaSyA_VALID_TEST_KEY_123456789")
    assert provider_valid_key.is_available() is True


def test_gemini_provider_generate_success():
    provider = GoogleGeminiProvider(api_key="test_key_valid", model="gemini-2.0-flash")

    mock_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Rank 3: Snake Island. Survival is nearly impossible."}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 15,
            "candidatesTokenCount": 12,
            "totalTokenCount": 27,
        },
    }

    mock_resp = io.BytesIO(json.dumps(mock_response_data).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        resp = provider.generate("Give me rank 3 script", system_prompt="You are a mystery storyteller")

        assert resp.is_fallback is False
        assert resp.provider == "gemini"
        assert resp.model_name == "gemini-2.0-flash"
        assert "Snake Island" in resp.content
        assert mock_urlopen.called


def test_gemini_provider_fallback_on_http_error():
    provider = GoogleGeminiProvider(api_key="test_key_valid", model="gemini-2.0-flash")

    http_error = urllib.error.HTTPError(
        url="https://generativelanguage.googleapis.com",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(b'{"error": {"message": "API key not valid."}}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        resp = provider.generate("Generate script")

        assert resp.is_fallback is True
        assert resp.provider == "fallback"
        assert resp.content != ""


def test_gemini_provider_fallback_when_unconfigured():
    provider = GoogleGeminiProvider(api_key="")
    resp = provider.generate("Generate script")

    assert resp.is_fallback is True
    assert resp.provider == "fallback"


def test_get_model_provider_selects_gemini(monkeypatch):
    monkeypatch.setattr(config, "model_provider", "gemini")
    monkeypatch.setattr(config, "gemini_api_key", "AIzaSyA_TEST_KEY_GEMINI_1234567")

    provider = get_model_provider()
    assert isinstance(provider, GoogleGeminiProvider)
    assert provider.is_available() is True
