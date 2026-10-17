"""Multi-platform publishing service orchestrating YouTube, Instagram, and TikTok distributions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.db import Database, db
from app.publishing.connectors.instagram_connector import InstagramReelsConnector
from app.publishing.connectors.tiktok_connector import TikTokConnector
from app.publishing.connectors.youtube_connector import YouTubeShortsConnector
from app.publishing.platform_models import PlatformType, PublishPayload, PublishResult, PublishStatus
from app.publishing.safety_guard import PublishingSafetyGuard, publishing_safety_guard
from app.utils.logger import logger


class MultiPlatformPublisherService:
    """Orchestrates safe, policy-compliant, multi-platform publishing."""

    def __init__(
        self,
        database: Optional[Database] = None,
        safety_guard: Optional[PublishingSafetyGuard] = None,
    ) -> None:
        self.db = database or db
        self.safety = safety_guard or publishing_safety_guard
        self.yt_connector = YouTubeShortsConnector()
        self.ig_connector = InstagramReelsConnector()
        self.tt_connector = TikTokConnector()

    def publish_to_platform(
        self,
        payload: PublishPayload,
        platform: PlatformType,
        dry_run: bool = False,
    ) -> PublishResult:
        """Publish payload to a single target platform with strict safety pre-flight."""
        # 1. Pre-flight safety check
        passed, issues = self.safety.check_preflight(payload, platform, dry_run=dry_run)
        if not passed:
            logger.warning(f"Publishing pre-flight rejected for {platform.value}: {'; '.join(issues)}")
            return PublishResult(
                platform=platform,
                status=PublishStatus.PAUSED_SAFETY,
                error_message="; ".join(issues),
                dry_run=dry_run,
            )

        # 2. Check for ambiguous upload already present on remote platform before retrying
        already_uploaded, remote_id = self.safety.reconcile_ambiguous_upload(payload, platform)
        if already_uploaded and remote_id:
            logger.info(f"Reconciliation: Job {payload.job_id} already exists on {platform.value} ({remote_id}). Skipping re-upload.")
            return PublishResult(
                platform=platform,
                status=PublishStatus.PUBLISHED,
                platform_post_id=remote_id,
                platform_url=f"https://youtube.com/shorts/{remote_id}" if platform == PlatformType.YOUTUBE_SHORTS else f"https://mhide.dev/posts/{platform.value}/{remote_id}",
                dry_run=False,
                details={"reconciled": True, "remote_id": remote_id},
            )

        # 3. Dispatch to specific connector
        logger.info(f"Publishing job {payload.job_id} to {platform.value} (Dry-run: {dry_run})...")
        if platform == PlatformType.YOUTUBE_SHORTS:
            res = self.yt_connector.publish(payload, dry_run=dry_run)
        elif platform == PlatformType.INSTAGRAM_REELS:
            res = self.ig_connector.publish(payload, dry_run=dry_run)
        elif platform == PlatformType.TIKTOK:
            res = self.tt_connector.publish(payload, dry_run=dry_run)
        else:
            res = PublishResult(
                platform=platform,
                status=PublishStatus.FAILED,
                error_message=f"Unsupported platform: {platform}",
            )

        # 3. Record publication in database
        self.safety.record_publication(payload, res)
        return res

    def publish_multi_platform(
        self,
        payload: PublishPayload,
        platforms: Optional[List[PlatformType]] = None,
        dry_run: bool = False,
    ) -> Dict[str, PublishResult]:
        """Publish to all requested platforms simultaneously."""
        targets = platforms or [
            PlatformType.YOUTUBE_SHORTS,
            PlatformType.INSTAGRAM_REELS,
            PlatformType.TIKTOK,
        ]
        results: Dict[str, PublishResult] = {}
        for p in targets:
            results[p.value] = self.publish_to_platform(payload, p, dry_run=dry_run)
        return results


# Singleton instance
multi_platform_publisher = MultiPlatformPublisherService()
