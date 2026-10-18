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

    # External Media Tools
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    ffprobe_path: str = os.getenv("FFPROBE_PATH", "ffprobe")

    # Application settings
    app_env: str = os.getenv("APP_ENV", "local").lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    timezone: str = os.getenv("TIMEZONE", "Africa/Lagos")
    min_disk_free_gb: float = float(os.getenv("MIN_DISK_FREE_GB", "10.0"))

    # AI / LLM Provider (Zero-Cost Local Default or Google Gemini)
    model_provider: str = os.getenv("MODEL_PROVIDER", "ollama").lower()
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    ollama_reasoning_model: str = os.getenv("OLLAMA_REASONING_MODEL", "qwen2.5-coder:7b")
    paid_apis_enabled: bool = os.getenv("PAID_APIS_ENABLED", "false").lower() in ("true", "1", "yes")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    # Image model for scene visuals: "gemini-2.5-flash-image" (Nano Banana) or an "imagen-*" model
    gemini_image_model: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    pixabay_api_key: str = os.getenv("PIXABAY_API_KEY", "")
    pexels_api_key: str = os.getenv("PEXELS_API_KEY", "")

    # Neural Voiceover Engine (ElevenLabs, Google Gemini TTS, Fish Audio, or Edge-TTS)
    tts_provider: str = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
    tts_voice: str = os.getenv("TTS_VOICE", "en-US-ChristopherNeural")
    tts_rate: str = os.getenv("TTS_RATE", "+8%")
    tts_pitch: str = os.getenv("TTS_PITCH", "-6Hz")
    tts_volume: str = os.getenv("TTS_VOLUME", "+0%")

    # High-Retention Cinematic Voices (ElevenLabs / Fish Audio / OpenAI)
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Default: Adam (dark documentary narrator)
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
    fish_audio_api_key: str = os.getenv("FISH_AUDIO_API_KEY", "")
    fish_audio_voice_id: str = os.getenv("FISH_AUDIO_VOICE_ID", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_tts_voice: str = os.getenv("OPENAI_TTS_VOICE", "onyx")

    # YouTube Data API v3 & OAuth
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    youtube_client_secrets_file: Path = BASE_DIR / os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "credentials/client_secrets.json")
    youtube_token_file: Path = BASE_DIR / os.getenv("YOUTUBE_TOKEN_FILE", "data/youtube_token.json")
    youtube_publish_mode: str = os.getenv("YOUTUBE_PUBLISH_MODE", "disabled").lower()
    youtube_default_privacy: str = os.getenv("YOUTUBE_DEFAULT_PRIVACY", "private").lower()

    # Multi-Platform Publishing & Autonomous Engine Controls (Stage 10)
    instagram_publish_mode: str = os.getenv("INSTAGRAM_PUBLISH_MODE", "disabled").lower()
    tiktok_publish_mode: str = os.getenv("TIKTOK_PUBLISH_MODE", "disabled").lower()
    auto_publish_enabled: bool = os.getenv("AUTO_PUBLISH_ENABLED", "false").lower() in ("true", "1", "yes")
    auto_publish_daily_limit: int = int(os.getenv("AUTO_PUBLISH_DAILY_LIMIT", os.getenv("MAX_DAILY_UPLOADS", "2")))
    auto_publish_min_interval_hours: float = float(os.getenv("AUTO_PUBLISH_MIN_INTERVAL_HOURS", "4.0"))
    auto_publish_max_daily_spend: float = float(os.getenv("AUTO_PUBLISH_MAX_DAILY_SPEND", "0.0"))
    auto_publish_allowed_hours: str = os.getenv("AUTO_PUBLISH_ALLOWED_HOURS", "09-22")
    auto_publish_timezone: str = os.getenv("AUTO_PUBLISH_TIMEZONE", os.getenv("TIMEZONE", "Africa/Lagos"))
    auto_publish_failure_limit: int = int(os.getenv("AUTO_PUBLISH_FAILURE_LIMIT", "3"))
    auto_cleanup_artifacts: bool = os.getenv("AUTO_CLEANUP_ARTIFACTS", "true").lower() in ("true", "1", "yes")

    # Telegram Control Room
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_allowed_user_ids: List[int] = field(default_factory=list)

    # Creator Brand & Content Strategy
    creator_brand: str = os.getenv("CREATOR_BRAND", "Darkest Minds 101")
    niche_default: str = os.getenv("NICHE_DEFAULT", "Unsolved Mysteries & Strange Disappearances")
    daily_shorts_target: int = int(os.getenv("DAILY_SHORTS_TARGET", "2"))
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "5"))
    render_concurrency: int = int(os.getenv("RENDER_CONCURRENCY", "1"))
    target_video_duration_min: int = int(os.getenv("TARGET_VIDEO_DURATION_MIN", "25"))
    target_video_duration_max: int = int(os.getenv("TARGET_VIDEO_DURATION_MAX", "55"))

    # Phase 2: YouTube Research Engine Settings
    research_max_videos_per_run: int = int(os.getenv("RESEARCH_MAX_VIDEOS_PER_RUN", "25"))
    research_max_api_requests: int = int(os.getenv("RESEARCH_MAX_API_REQUESTS", "5"))
    research_cache_ttl_hours: int = int(os.getenv("RESEARCH_CACHE_TTL_HOURS", "6"))
    research_lookback_days: int = int(os.getenv("RESEARCH_LOOKBACK_DAYS", "30"))

    # Autonomous Channel Operator Settings
    autonomous_research_interval_hours: int = int(os.getenv("AUTONOMOUS_RESEARCH_INTERVAL_HOURS", "24"))
    autonomous_production_interval_hours: int = int(os.getenv("AUTONOMOUS_PRODUCTION_INTERVAL_HOURS", "12"))
    autonomous_paused: bool = os.getenv("AUTONOMOUS_PAUSED", "false").lower() in ("true", "1", "yes")
    max_daily_uploads: int = int(os.getenv("MAX_DAILY_UPLOADS", "2"))

    def __post_init__(self) -> None:
        # Normalize and align publishing mode aliases
        mode = self.youtube_publish_mode.lower()
        if mode in ("autonomous", "autonomous_public", "public"):
            self.youtube_publish_mode = "autonomous_public"
        elif mode in ("review-required", "private_test", "review_required", "private"):
            self.youtube_publish_mode = "private_test"
        else:
            self.youtube_publish_mode = "disabled"

        if self.instagram_publish_mode not in ("disabled", "dry_run", "publish"):
            self.instagram_publish_mode = "disabled"

        if self.tiktok_publish_mode not in ("disabled", "dry_run", "publish"):
            self.tiktok_publish_mode = "disabled"

        self.max_daily_uploads = self.auto_publish_daily_limit

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

        valid_modes = ("disabled", "private_test", "autonomous_public")
        if self.youtube_publish_mode not in valid_modes:
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
            "creator_brand": self.creator_brand,
            "niche_default": self.niche_default,
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
            "gemini_api_key_configured": bool(self.gemini_api_key),
            "gemini_model": self.gemini_model,
            "pixabay_api_key_configured": bool(self.pixabay_api_key),
            "elevenlabs_api_key_configured": bool(self.elevenlabs_api_key),
            "fish_audio_api_key_configured": bool(self.fish_audio_api_key),
            "openai_api_key_configured": bool(self.openai_api_key),
            "tts_provider": self.tts_provider,
            "tts_voice": self.tts_voice,
            "tts_rate": self.tts_rate,
            "youtube_publish_mode": self.youtube_publish_mode,
            "youtube_default_privacy": self.youtube_default_privacy,
            "youtube_api_key_configured": bool(self.youtube_api_key),
            "youtube_client_secrets_exists": self.youtube_client_secrets_file.exists(),
            "instagram_publish_mode": self.instagram_publish_mode,
            "tiktok_publish_mode": self.tiktok_publish_mode,
            "auto_publish_enabled": self.auto_publish_enabled,
            "auto_publish_daily_limit": self.auto_publish_daily_limit,
            "auto_publish_min_interval_hours": self.auto_publish_min_interval_hours,
            "auto_publish_max_daily_spend": self.auto_publish_max_daily_spend,
            "auto_publish_allowed_hours": self.auto_publish_allowed_hours,
            "auto_publish_timezone": self.auto_publish_timezone,
            "auto_publish_failure_limit": self.auto_publish_failure_limit,
            "telegram_bot_configured": bool(self.telegram_bot_token),
            "telegram_allowed_users_count": len(self.telegram_allowed_user_ids),
            "daily_shorts_target": self.daily_shorts_target,
            "max_queue_size": self.max_queue_size,
            "render_concurrency": self.render_concurrency,
            "research_max_videos_per_run": self.research_max_videos_per_run,
            "research_max_api_requests": self.research_max_api_requests,
            "research_cache_ttl_hours": self.research_cache_ttl_hours,
            "research_lookback_days": self.research_lookback_days,
            "autonomous_paused": self.autonomous_paused,
            "max_daily_uploads": self.max_daily_uploads,
        }




# Singleton configuration instance
config = Config()
