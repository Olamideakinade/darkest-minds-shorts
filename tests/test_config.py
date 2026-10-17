"""Unit tests for configuration loading and secrets protection."""

import os
from pathlib import Path
from app.config import Config


def test_config_defaults(tmp_path: Path):
    cfg = Config(base_dir=tmp_path)
    assert cfg.app_env in ("local", "staging", "production")
    assert cfg.min_disk_free_gb >= 1.0
    assert cfg.youtube_publish_mode in ("disabled", "review-required", "autonomous", "autonomous_public", "private_test")
    assert cfg.paid_apis_enabled is False


def test_config_secrets_redaction(tmp_path: Path):
    cfg = Config(
        base_dir=tmp_path,
        youtube_api_key="AIzaSyA_SECRET_KEY_1234567890ABCDEF",
        telegram_bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456789",
        gemini_api_key="AIzaSyB_MOCK_GEMINI_KEY_987654321",
    )
    safe = cfg.to_safe_dict()
    assert "youtube_api_key" not in safe
    assert "telegram_bot_token" not in safe
    assert "gemini_api_key" not in safe
    assert safe["youtube_api_key_configured"] is True
    assert safe["telegram_bot_configured"] is True
    assert safe["gemini_api_key_configured"] is True


def test_config_directory_creation(tmp_path: Path):
    test_base = tmp_path / "custom_base"
    cfg = Config(
        base_dir=test_base,
        data_dir=test_base / "data",
        output_dir=test_base / "output",
        logs_dir=test_base / "logs",
        credentials_dir=test_base / "credentials",
    )
    assert cfg.data_dir.exists()
    assert cfg.output_dir.exists()
    assert cfg.logs_dir.exists()
    assert cfg.credentials_dir.exists()
