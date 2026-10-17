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
                video_file = None
                video_path_str = job.payload.get("video_path")
                if video_path_str and Path(video_path_str).exists():
                    video_file = Path(video_path_str)
                else:
                    job_specific = config.output_dir / "jobs" / job.id / "short_1080x1920.mp4"
                    if job_specific.exists():
                        video_file = job_specific
                    else:
                        job_mp4s = list((config.output_dir / "jobs" / job.id).glob("*.mp4"))
                        if job_mp4s:
                            video_file = job_mp4s[0]
                        else:
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
                        "categoryId": "24",  # Entertainment / Mystery Storytelling
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

                # Upgrade 1: Post Algorithmic Comment Trap (Pinned Comment)
                pinned_comment = job.payload.get("pinned_comment")
                if pinned_comment:
                    try:
                        comment_body = {
                            "snippet": {
                                "videoId": yt_id,
                                "topLevelComment": {
                                    "snippet": {
                                        "textOriginal": pinned_comment
                                    }
                                }
                            }
                        }
                        service.commentThreads().insert(part="snippet", body=comment_body).execute()
                        logger.info(f"Algorithmic Comment Trap posted to video {yt_id}: '{pinned_comment[:50]}...'")
                    except Exception as ce:
                        logger.warning(f"Could not post comment trap: {ce}")

                msg = f"Video published successfully to YouTube ({privacy_status}): {video_url}"
                logger.info(msg)

                # Send Telegram notification with video link
                try:
                    from app.telegram.notifier import notifier
                    notifier.notify_video_published(title=metadata["title"], url=video_url, privacy=privacy_status)
                except Exception as ne:
                    logger.warning(f"Telegram notification note: {ne}")

                return True, msg, {"youtube_id": yt_id, "url": video_url, "privacy": privacy_status}

            except Exception as e:
                err_msg = f"YouTube API upload failed: {e}"
                logger.error(err_msg)
                return False, err_msg, {"blocker": "API_ERROR", "error": str(e)}

        # If running locally in test environment without live credentials
        msg = f"Channel authenticated, but credentials/token not present on disk: {token_file}"
        return False, msg, {"blocker": "TOKEN_FILE_MISSING"}

    @staticmethod
    def format_viral_short_title(raw_title: str) -> str:
        """Strip any existing survival tag or #shorts and format a clean title under 65 chars."""
        import re
        if not raw_title:
            return "Top 3 Forbidden Places (Survival Is 0%) ⚠️ #shorts"

        suffix = " (Survival Is 0%) ⚠️ #shorts"
        # Suffix is 28 chars. To ensure total length <= 64 chars, base phrase must be <= 36 chars.
        max_base_len = 36

        cleaned = raw_title
        cleaned = re.sub(r"\(Survival[^\)]*\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"where survival is \d+%", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"where survival i\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"where survival\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"#\S+", "", cleaned)
        cleaned = re.sub(r"[⚠️💀🕯️👇❌🚨]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Ensure base title is a complete phrase under max_base_len characters
        if len(cleaned) > max_base_len:
            words = cleaned.split()
            truncated = []
            cur_len = 0
            for w in words:
                word_len = len(w) + (1 if truncated else 0)
                if cur_len + word_len <= max_base_len:
                    truncated.append(w)
                    cur_len += word_len
                else:
                    break
            cleaned = " ".join(truncated).strip() or cleaned[:max_base_len].strip()

        return f"{cleaned}{suffix}"

    def _generate_metadata(self, job: Job) -> Dict[str, Any]:
        """Generate high-retention metadata optimized for YouTube Shorts indexing."""
        topic = job.payload.get("topic") or job.title
        raw_title = job.payload.get("optimized_title") or job.payload.get("title") or topic
        title = self.format_viral_short_title(raw_title)

        description = job.payload.get("description_text")
        if not description:
            description = (
                f"{topic}\n\n"
                "Darkest Minds 101 — Extreme world countdowns, forbidden locations, and terrifying mysteries.\n"
                "Subscribe and enter the darker side of the unknown. 🕯️\n\n"
                "#Shorts #Rankings #Top3 #ForbiddenPlaces #MostDangerousPlaces #Survival #DarkestMinds #UnsolvedMysteries"
            )

        tags = job.payload.get("target_tags")
        if not tags or not isinstance(tags, list):
            tags = [
                "forbidden places", "scariest places on earth", "places you cannot visit",
                "snake island", "north sentinel island", "paris catacombs",
                "most dangerous places in the world", "survival ranking", "ranking shorts",
                "top 3", "darkest minds 101", "creepy places", "unsolved mysteries", "zero survival", "shorts"
            ]
        return {
            "title": title,
            "description": description,
            "tags": tags,
        }


# Singleton instance
publisher = YouTubePublisher()

