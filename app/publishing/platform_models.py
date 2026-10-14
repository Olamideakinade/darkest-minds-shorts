"""Platform publishing models and schema for YouTube, Instagram, and TikTok."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class PlatformType(str, Enum):
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    TIKTOK = "tiktok"


class PublishStatus(str, Enum):
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    DRY_RUN = "DRY_RUN"
    FAILED = "FAILED"
    PAUSED_SAFETY = "PAUSED_SAFETY"


@dataclass
class PublishPayload:
    """Standardized multi-platform publishing payload."""

    job_id: str
    video_path: Path
    title: str
    caption: str
    hashtags: List[str] = field(default_factory=lambda: ["#programming", "#developer", "#coding", "#softwareengineer", "#tech"])
    scheduled_time_utc: Optional[str] = None
    privacy_status: str = "private"  # private, unlisted, public
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    thumbnail_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "video_path": str(self.video_path),
            "title": self.title,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "scheduled_time_utc": self.scheduled_time_utc,
            "privacy_status": self.privacy_status,
            "idempotency_key": self.idempotency_key,
            "thumbnail_path": str(self.thumbnail_path) if self.thumbnail_path else None,
        }


@dataclass
class PublishResult:
    """Result of an autonomous or scheduled publication attempt."""

    platform: PlatformType
    status: PublishStatus
    platform_post_id: Optional[str] = None
    platform_url: Optional[str] = None
    error_message: Optional[str] = None
    published_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dry_run: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform.value if isinstance(self.platform, PlatformType) else self.platform,
            "status": self.status.value if isinstance(self.status, PublishStatus) else self.status,
            "platform_post_id": self.platform_post_id,
            "platform_url": self.platform_url,
            "error_message": self.error_message,
            "published_at_utc": self.published_at_utc,
            "dry_run": self.dry_run,
            "details": self.details,
        }
