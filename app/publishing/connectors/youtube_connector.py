"""YouTube Shorts publishing connector."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.config import config
from app.publishing.platform_models import PlatformType, PublishPayload, PublishResult, PublishStatus
from app.utils.logger import logger
from app.youtube.publisher import YouTubePublisher, publisher as yt_pub


class YouTubeShortsConnector:
    """Official YouTube Data API v3 publisher connector for Shorts."""

    def __init__(self, publisher_inst: Optional[YouTubePublisher] = None) -> None:
        self.publisher = publisher_inst or yt_pub

    def publish(self, payload: PublishPayload, dry_run: bool = False) -> PublishResult:
        """Publish or dry-run a Short to YouTube."""
        mode = config.youtube_publish_mode

        if dry_run or mode == "disabled":
            logger.info(f"YouTube publishing in non-public/dry-run mode (Mode: {mode}) for job {payload.job_id}")
            return PublishResult(
                platform=PlatformType.YOUTUBE_SHORTS,
                status=PublishStatus.DRY_RUN,
                platform_post_id=f"dry_yt_{payload.job_id[:8]}",
                platform_url=f"https://youtube.com/shorts/mock_{payload.job_id[:8]}",
                dry_run=True,
                details={"mode": mode, "privacy": payload.privacy_status},
            )

        try:
            from app.database.models import Job
            # When publish mode is private_test or autonomous_public
            privacy = "private" if mode == "private_test" else payload.privacy_status
            job = self.publisher.db.get_job(payload.job_id) or Job(id=payload.job_id, title=payload.title)
            success, message, details = self.publisher.publish_video(job, privacy_status=privacy)

            if success:
                video_id = details.get("video_id", "")
                return PublishResult(
                    platform=PlatformType.YOUTUBE_SHORTS,
                    status=PublishStatus.PUBLISHED,
                    platform_post_id=video_id,
                    platform_url=f"https://youtube.com/shorts/{video_id}",
                    dry_run=False,
                    details=details,
                )
            else:
                return PublishResult(
                    platform=PlatformType.YOUTUBE_SHORTS,
                    status=PublishStatus.FAILED,
                    error_message=message,
                    dry_run=False,
                    details=details,
                )
        except Exception as e:
            logger.exception(f"YouTube connector exception: {e}")
            return PublishResult(
                platform=PlatformType.YOUTUBE_SHORTS,
                status=PublishStatus.FAILED,
                error_message=str(e),
                dry_run=False,
            )
