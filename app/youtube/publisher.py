"""YouTube video publisher with autonomous safety guards and metadata generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import uuid

from app.config import config
from app.database.db import Database, db
from app.database.models import Job, PublishedVideo, utc_now_iso
from app.utils.logger import logger
from app.youtube.channel_manager import OwnerChannelManager, YOUTUBE_SCOPES, channel_manager


class YouTubePublisher:
    """Publishes qualifying rendered Shorts according to autonomous policy."""

    def __init__(self, database: Optional[Database] = None, ch_manager: Optional[OwnerChannelManager] = None) -> None:
        self.db = database or db
        self.channel_manager = ch_manager or channel_manager

    def publish_video(self, job: Job, privacy_status: str = "public") -> Tuple[bool, str, Dict[str, Any]]:
        """Publish or record a video for the specified job.

        Returns:
            Tuple of (success: bool, message: str, details: Dict[str, Any])
        """
        # 1. Verify channel connection
        status = self.channel_manager.get_connection_status()
        if not status.is_connected:
            msg = (
                "Upload blocked: Owner YouTube channel is not connected via OAuth 2.0. "
                "See './run.sh channel-status' for instructions."
            )
            logger.warning(msg)
            return False, msg, {"blocker": "OAUTH_NOT_CONNECTED"}

        # 2. Check for existing upload record to strictly prevent duplicates
        existing = self.db.get_published_video_by_job(job.id)
        if existing:
            msg = f"Duplicate upload prevented: Job {job.id} already uploaded as video {existing.youtube_id}."
            logger.warning(msg)
            return False, msg, {"blocker": "DUPLICATE_UPLOAD", "existing_video_id": existing.youtube_id}

        # 3. Generate YouTube Shorts metadata
        metadata = self._generate_metadata(job)

        # 4. Attempt real upload via YouTube Data API v3 if credentials are fully valid
        token_file = config.youtube_token_file
        if token_file.exists():
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload

                with open(token_file, "r", encoding="utf-8") as f:
                    token_info = json.load(f)

                creds = Credentials.from_authorized_user_info(token_info, scopes=YOUTUBE_SCOPES)
                service = build("youtube", "v3", credentials=creds)

                # Find rendered video file in output or payload
                video_path_str = job.payload.get("video_path")
                if video_path_str and Path(video_path_str).exists():
                    video_file = Path(video_path_str)
                else:
                    # Look for any rendered mp4 in output directory
                    output_files = list(config.output_dir.glob("*.mp4"))
                    video_file = output_files[0] if output_files else None

                if not video_file or not video_file.exists():
                    msg = f"Upload blocked: Rendered video file not found for job {job.id}."
                    logger.error(msg)
                    return False, msg, {"blocker": "FILE_NOT_FOUND"}

                body = {
                    "snippet": {
                        "title": metadata["title"],
                        "description": metadata["description"],
                        "tags": metadata["tags"],
                        "categoryId": "27",  # Education / Documentary
                    },
                    "status": {
                        "privacyStatus": privacy_status,
                        "selfDeclaredMadeForKids": False,
                    },
                }

                media = MediaFileUpload(str(video_file), chunksize=-1, resumable=True)
                request = service.videos().insert(part="snippet,status", body=body, media_body=media)
                response = request.execute()

                yt_id = response.get("id", f"yt-{uuid.uuid4().hex[:8]}")
                video_url = f"https://youtube.com/shorts/{yt_id}"

                pub_record = PublishedVideo(
                    job_id=job.id,
                    youtube_id=yt_id,
                    title=metadata["title"],
                    description=metadata["description"],
                    privacy_status=privacy_status,
                    youtube_url=video_url,
                )
                self.db.save_published_video(pub_record)

                msg = f"Video published successfully to YouTube ({privacy_status}): {video_url}"
                logger.info(msg)
                return True, msg, {"youtube_id": yt_id, "url": video_url, "privacy": privacy_status}

            except Exception as e:
                err_msg = f"YouTube API upload failed: {e}"
                logger.error(err_msg)
                return False, err_msg, {"blocker": "API_ERROR", "error": str(e)}

        # If running locally in test environment without live credentials
        msg = f"Channel authenticated, but credentials/token not present on disk: {token_file}"
        return False, msg, {"blocker": "TOKEN_FILE_MISSING"}

    def _generate_metadata(self, job: Job) -> Dict[str, Any]:
        """Generate high-retention metadata optimized for YouTube Shorts indexing."""
        topic = job.payload.get("topic") or job.title
        # Title must be under 70 chars for mobile vertical display + #Shorts
        clean_topic = topic[:55].strip()
        title = f"{clean_topic} #Shorts"

        description = (
            f"{topic}\n\n"
            "An untold story from the historical record.\n\n"
            "#Shorts #History #StrangeHistory #Mystery #Documentary"
        )
        tags = [
            "Shorts",
            "History",
            "Strange History",
            "Documentary",
            "Mystery",
            "True Story",
            "Curiosity",
        ]
        return {
            "title": title,
            "description": description,
            "tags": tags,
        }


# Singleton instance
publisher = YouTubePublisher()

