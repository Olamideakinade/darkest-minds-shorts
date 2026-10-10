"""Application configuration manager for Mhide Story Intelligence.

Loads settings from environment variables and .env file with strong defaults,
safe validation, and secrets redaction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Base directory is workspace root
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)


@dataclass
class Config:
    """Strongly typed application configuration."""

    # Paths
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    output_dir: Path = BASE_DIR / "output"
    logs_dir: Path = BASE_DIR / "logs"
    credentials_dir: Path = BASE_DIR / "credentials"
    db_path: Path = BASE_DIR / "data" / "mhide.db"

    # Application settings
    app_env: str = os.getenv("APP_ENV", "local").lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    timezone: str = os.getenv("TIMEZONE", "Africa/Lagos")
    min_disk_free_gb: float = float(os.getenv("MIN_DISK_FREE_GB", "10.0"))

    # AI / LLM Provider (Zero-Cost Local Default)
    model_provider: str = os.getenv("MODEL_PROVIDER", "ollama").lower()
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    ollama_reasoning_model: str = os.getenv("OLLAMA_REASONING_MODEL", "qwen2.5-coder:7b")
    paid_apis_enabled: bool = os.getenv("PAID_APIS_ENABLED", "false").lower() in ("true", "1", "yes")

    # Local TTS Voiceover Engine
    tts_provider: str = os.getenv("TTS_PROVIDER", "edge-tts").lower()
    tts_voice: str = os.getenv("TTS_VOICE", "en-US-ChristopherNeural")
    tts_rate: str = os.getenv("TTS_RATE", "+0%")
    tts_volume: str = os.getenv("TTS_VOLUME", "+0%")

    # YouTube Data API v3 & OAuth
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    youtube_client_secrets_file: Path = BASE_DIR / os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "credentials/client_secrets.json")
    youtube_token_file: Path = BASE_DIR / os.getenv("YOUTUBE_TOKEN_FILE", "data/youtube_token.json")
    youtube_publish_mode: str = os.getenv("YOUTUBE_PUBLISH_MODE", "disabled").lower()
    youtube_default_privacy: str = os.getenv("YOUTUBE_DEFAULT_PRIVACY", "private").lower()

    # Telegram Control Room
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_allowed_user_ids: List[int] = field(default_factory=list)

    # Strategy & Production Quotas
    niche_default: str = os.getenv("NICHE_DEFAULT", "Strange History & Unsolved Mysteries")
    daily_shorts_target: int = int(os.getenv("DAILY_SHORTS_TARGET", "1"))
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "5"))
    render_concurrency: int = int(os.getenv("RENDER_CONCURRENCY", "1"))
    target_video_duration_min: int = int(os.getenv("TARGET_VIDEO_DURATION_MIN", "25"))
    target_video_duration_max: int = int(os.getenv("TARGET_VIDEO_DURATION_MAX", "55"))

    def __post_init__(self) -> None:
        # Parse telegram allowed user IDs
        raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
        if raw_ids:
            parsed: List[int] = []
            for item in raw_ids.split(","):
                cleaned = item.strip()
                if cleaned.isdigit():
                    parsed.append(int(cleaned))
            self.telegram_allowed_user_ids = parsed

        # Ensure essential directories exist
        for d in [self.data_dir, self.output_dir, self.logs_dir, self.credentials_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def validate(self) -> List[str]:
        """Validate configuration settings and return any warning/error messages."""
        warnings: List[str] = []

        if self.youtube_publish_mode not in ("disabled", "review-required", "autonomous"):
            warnings.append(
                f"Invalid YOUTUBE_PUBLISH_MODE '{self.youtube_publish_mode}'. Defaulting to 'disabled'."
            )
            self.youtube_publish_mode = "disabled"

        if self.youtube_default_privacy not in ("private", "unlisted", "public"):
            warnings.append(
                f"Invalid YOUTUBE_DEFAULT_PRIVACY '{self.youtube_default_privacy}'. Defaulting to 'private'."
            )
            self.youtube_default_privacy = "private"

        if not self.youtube_api_key:
            warnings.append("YouTube API Key not configured. Research will be restricted until key is provided.")

        if not self.telegram_bot_token:
            warnings.append("Telegram Bot Token not configured. Telegram control room is disabled.")

        return warnings

    def to_safe_dict(self) -> Dict[str, Any]:
        """Return configuration dictionary with all secret values redacted."""
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "timezone": self.timezone,
            "base_dir": str(self.base_dir),
            "data_dir": str(self.data_dir),
            "output_dir": str(self.output_dir),
            "min_disk_free_gb": self.min_disk_free_gb,
            "model_provider": self.model_provider,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "ollama_reasoning_model": self.ollama_reasoning_model,
            "paid_apis_enabled": self.paid_apis_enabled,
            "tts_provider": self.tts_provider,
            "tts_voice": self.tts_voice,
            "tts_rate": self.tts_rate,
            "youtube_publish_mode": self.youtube_publish_mode,
            "youtube_default_privacy": self.youtube_default_privacy,
            "youtube_api_key_configured": bool(self.youtube_api_key),
            "youtube_client_secrets_exists": self.youtube_client_secrets_file.exists(),
            "telegram_bot_configured": bool(self.telegram_bot_token),
            "telegram_allowed_users_count": len(self.telegram_allowed_user_ids),
            "daily_shorts_target": self.daily_shorts_target,
            "max_queue_size": self.max_queue_size,
            "render_concurrency": self.render_concurrency,
        }


# Singleton configuration instance
config = Config()
