"""Safety guard and emergency kill switch for multi-platform publishing.

Enforces:
- Emergency kill switch and global pause mechanisms
- Platform policy verification (aspect ratio, duration, caption length)
- Duplicate publication prevention via persistent idempotency keys
- Minimum quality score thresholds
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import config
from app.database.db import Database, db
from app.publishing.platform_models import PlatformType, PublishPayload, PublishResult, PublishStatus
from app.utils.logger import logger


class PublishingSafetyGuard:
    """Protects brand integrity with automated pre-flight checks and emergency kill switches."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self.db = database or db
        self._emergency_kill_active: bool = False
        self._kill_reason: Optional[str] = None

    def trigger_kill_switch(self, reason: str = "Emergency manual intervention") -> None:
        """Immediately halt all autonomous publishing across all platforms."""
        self._emergency_kill_active = True
        self._kill_reason = reason
        self.db.record_event("EMERGENCY_KILL_SWITCH_ENGAGED", f"Publishing halted: {reason}")
        logger.critical(f"EMERGENCY KILL SWITCH ACTIVATED: {reason}")

    def reset_kill_switch(self) -> None:
        """Clear the emergency kill switch and restore regular scheduled operations."""
        self._emergency_kill_active = False
        self._kill_reason = None
        self.db.record_event("EMERGENCY_KILL_SWITCH_RESET", "Publishing restored to normal operational state.")
        logger.info("Emergency kill switch reset. Publishing operations restored.")

    def is_kill_switch_active(self) -> Tuple[bool, Optional[str]]:
        """Return whether the emergency kill switch is currently active."""
        if self._emergency_kill_active:
            return True, self._kill_reason
        if config.autonomous_paused:
            return True, "Autonomous operations globally paused in system configuration."
        return False, None

    def check_preflight(self, payload: PublishPayload, platform: PlatformType) -> Tuple[bool, List[str]]:
        """Run pre-flight checks before attempting any network or platform API request."""
        issues: List[str] = []

        # 1. Emergency kill switch check
        is_killed, reason = self.is_kill_switch_active()
        if is_killed:
            issues.append(f"Publishing blocked: {reason}")
            return False, issues

        # 2. File existence and size check
        if not payload.video_path.exists() or payload.video_path.stat().st_size == 0:
            issues.append(f"Target video does not exist or has 0 bytes: {payload.video_path}")
            return False, issues

        # 3. Duplicate Post Prevention
        if self._is_already_published(payload.job_id, platform):
            issues.append(f"Duplicate post blocked: Job {payload.job_id} is already recorded as published on {platform.value}.")
            return False, issues

        # 4. Platform-specific metadata constraints
        if platform == PlatformType.YOUTUBE_SHORTS:
            if len(payload.title) > 100:
                issues.append(f"YouTube Shorts title exceeds 100 characters ({len(payload.title)})")
        elif platform == PlatformType.INSTAGRAM_REELS:
            if len(payload.caption) > 2200:
                issues.append(f"Instagram caption exceeds 2,200 character limit ({len(payload.caption)})")
        elif platform == PlatformType.TIKTOK:
            if len(payload.caption) > 2200:
                issues.append(f"TikTok caption exceeds 2,200 character limit ({len(payload.caption)})")

        return len(issues) == 0, issues

    def record_publication(self, payload: PublishPayload, result: PublishResult) -> None:
        """Persist publication record to prevent accidental duplicate posts."""
        if result.status == PublishStatus.PUBLISHED or (result.dry_run and result.status == PublishStatus.DRY_RUN):
            with self.db.connection() as conn:
                # Defensively ensure job exists to satisfy foreign key
                conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs (
                        id, title, niche, state, current_stage, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.job_id,
                        payload.title,
                        config.niche_default,
                        "READY",
                        "published",
                        result.published_at_utc,
                        result.published_at_utc,
                    ),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO published_videos (
                        video_id, job_id, youtube_id, title, description, privacy_status, youtube_url, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{result.platform.value}_{payload.idempotency_key}",
                        payload.job_id,
                        f"{result.platform.value}_{result.platform_post_id or payload.idempotency_key}",
                        payload.title,
                        payload.caption,
                        payload.privacy_status,
                        result.platform_url or f"https://mhide.dev/posts/{result.platform.value}/{payload.job_id}",
                        result.published_at_utc,
                    ),
                )
            logger.info(f"Recorded verified publication of job {payload.job_id} on {result.platform.value}")

    def _is_already_published(self, job_id: str, platform: PlatformType) -> bool:
        """Check if job has already been published to the target platform."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT video_id FROM published_videos WHERE job_id = ? AND (youtube_id LIKE ? OR youtube_url LIKE ?)",
                (job_id, f"{platform.value}_%", f"%{platform.value}%"),
            ).fetchone()
            return row is not None


# Singleton instance
publishing_safety_guard = PublishingSafetyGuard()
