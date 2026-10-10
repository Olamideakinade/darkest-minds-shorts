"""Official YouTube Data API v3 client with quota budgeting, caching, and rate limiting."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.config import config
from app.database.db import db
from app.database.models import ResearchedVideo, utc_now_iso
from app.utils.logger import logger

# ISO 8601 duration parser regex (e.g. PT1M25S, PT45S, PT1H2M3S)
DURATION_REGEX = re.compile(
    r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
)


def parse_iso8601_duration(duration_str: str) -> int:
    """Parse ISO 8601 video duration (e.g. 'PT45S', 'PT1M15S') into total seconds."""
    match = DURATION_REGEX.match(duration_str)
    if not match:
        return 0
    parts = match.groupdict()
    days = int(parts.get("days") or 0)
    hours = int(parts.get("hours") or 0)
    minutes = int(parts.get("minutes") or 0)
    seconds = int(parts.get("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


@dataclass
class ApiCallResult:
    """Standardized response from YouTube Data API call."""
    success: bool
    data: Dict[str, Any]
    error_message: Optional[str] = None
    is_cached: bool = False
    quota_spent: int = 0


class YouTubeResearchClient:
    """Public metadata research client for YouTube Data API v3.

    Strictly handles public competitor metadata research.
    Decoupled from the owner's private channel analytics.
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_requests_per_run: int = 5,
        cache_ttl_hours: int = 6,
        timeout_sec: int = 15,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.youtube_api_key
        self.max_requests_per_run = max_requests_per_run
        self.cache_ttl_hours = cache_ttl_hours
        self.timeout_sec = timeout_sec
        self.requests_made_this_run = 0

    @property
    def is_configured(self) -> bool:
        """Return True if an API key is provided."""
        return bool(self.api_key and self.api_key.strip())

    # --------------------------------------------------------------------------
    # Public Research Methods
    # --------------------------------------------------------------------------

    def search_story_videos(
        self,
        query: str,
        max_results: int = 15,
        order: str = "relevance",
        video_duration: str = "short",  # 'short' is < 4 minutes in YouTube API
    ) -> ApiCallResult:
        """Search public videos using keywords.

        Quota cost: 100 units.
        """
        if not self.is_configured:
            return ApiCallResult(
                success=False,
                data={"items": []},
                error_message="YouTube API Key not configured. Research is operating in offline/demo mode.",
                quota_spent=0,
            )

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "maxResults": min(max_results, 50),
            "videoDuration": video_duration,
        }

        # Cache key based on endpoint and parameters
        cache_key = self._generate_cache_key("search", params)
        cached_json = db.get_cached_api_response(cache_key)
        if cached_json:
            logger.debug(f"Cache hit for search query: '{query}'")
            return ApiCallResult(
                success=True,
                data=json.loads(cached_json),
                is_cached=True,
                quota_spent=0,
            )

        # Enforce rate/request limit per run
        if self.requests_made_this_run >= self.max_requests_per_run:
            return ApiCallResult(
                success=False,
                data={"items": []},
                error_message=f"Reached maximum API requests limit ({self.max_requests_per_run}) for this run.",
                quota_spent=0,
            )

        res = self._execute_request("search", params, quota_cost=100)
        if res.success:
            db.set_cached_api_response(
                cache_key=cache_key,
                endpoint="search",
                response_json=json.dumps(res.data),
                ttl_hours=self.cache_ttl_hours,
            )
        return res

    def get_video_details_batch(self, video_ids: List[str]) -> ApiCallResult:
        """Fetch snippet, contentDetails (duration), and statistics for up to 50 videos in 1 call.

        Quota cost: 1 unit per batch of 50.
        """
        if not video_ids:
            return ApiCallResult(success=True, data={"items": []})

        if not self.is_configured:
            return ApiCallResult(
                success=False,
                data={"items": []},
                error_message="YouTube API Key not configured. Batch details unavailable.",
                quota_spent=0,
            )

        clean_ids = [vid.strip() for vid in video_ids if vid.strip()][:50]
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(clean_ids),
        }

        cache_key = self._generate_cache_key("videos", params)
        cached_json = db.get_cached_api_response(cache_key)
        if cached_json:
            return ApiCallResult(
                success=True,
                data=json.loads(cached_json),
                is_cached=True,
                quota_spent=0,
            )

        res = self._execute_request("videos", params, quota_cost=1)
        if res.success:
            db.set_cached_api_response(
                cache_key=cache_key,
                endpoint="videos",
                response_json=json.dumps(res.data),
                ttl_hours=self.cache_ttl_hours,
            )
        return res

    def get_channel_metadata(self, channel_id: str) -> ApiCallResult:
        """Fetch public subscriber count and total videos for a competitor channel.

        Quota cost: 1 unit.
        """
        if not self.is_configured:
            return ApiCallResult(
                success=False,
                data={"items": []},
                error_message="YouTube API Key not configured.",
                quota_spent=0,
            )

        params = {
            "part": "snippet,statistics",
            "id": channel_id.strip(),
        }

        cache_key = self._generate_cache_key("channels", params)
        cached_json = db.get_cached_api_response(cache_key)
        if cached_json:
            return ApiCallResult(
                success=True,
                data=json.loads(cached_json),
                is_cached=True,
                quota_spent=0,
            )

        res = self._execute_request("channels", params, quota_cost=1)
        if res.success:
            db.set_cached_api_response(
                cache_key=cache_key,
                endpoint="channels",
                response_json=json.dumps(res.data),
                ttl_hours=self.cache_ttl_hours * 4,  # Channels change slowly, cache longer
            )
        return res

    # --------------------------------------------------------------------------
    # Parsing & Normalization
    # --------------------------------------------------------------------------

    def parse_video_item(self, item: Dict[str, Any]) -> Optional[ResearchedVideo]:
        """Convert a raw YouTube API item into a strongly typed ResearchedVideo."""
        video_id = item.get("id")
        if isinstance(video_id, dict):
            video_id = video_id.get("videoId")
        if not video_id:
            return None

        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        statistics = item.get("statistics", {})

        title = snippet.get("title", "").strip()
        channel_id = snippet.get("channelId", "").strip()
        channel_title = snippet.get("channelTitle", "").strip()
        published_at = snippet.get("publishedAt", utc_now_iso())

        raw_duration = content_details.get("duration", "PT0S")
        duration_sec = parse_iso8601_duration(raw_duration)

        view_count = int(statistics.get("viewCount", 0))
        like_count = int(statistics.get("likeCount", 0))
        comment_count = int(statistics.get("commentCount", 0))
        tags = snippet.get("tags", [])

        return ResearchedVideo(
            video_id=video_id,
            channel_id=channel_id,
            channel_title=channel_title,
            title=title,
            published_at=published_at,
            duration_sec=duration_sec,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            topic_tags=tags,
            hook_summary=title[:120],
            created_at=utc_now_iso(),
        )

    # --------------------------------------------------------------------------
    # Internal HTTP Request Execution with Backoff & Quota Tracking
    # --------------------------------------------------------------------------

    def _execute_request(
        self,
        endpoint: str,
        params: Dict[str, Any],
        quota_cost: int,
        max_retries: int = 3,
    ) -> ApiCallResult:
        """Execute HTTP request with exponential backoff and quota recording."""
        query_params = dict(params)
        query_params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}?{urllib.parse.urlencode(query_params)}"

        self.requests_made_this_run += 1
        backoff_sec = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "MhideStoryIntelligence/1.0", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read().decode("utf-8"))
                        # Track quota spent
                        db.record_quota_usage(units=quota_cost)
                        return ApiCallResult(success=True, data=payload, quota_spent=quota_cost)

            except urllib.error.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")
                    err_json = json.loads(error_body)
                    reason = err_json.get("error", {}).get("errors", [{}])[0].get("reason", "")
                except Exception:
                    reason = str(e)

                # Quota Exhaustion Check
                if e.code == 403 and "quotaExceeded" in str(error_body):
                    logger.error(
                        "YouTube API daily quota exhausted (HTTP 403 quotaExceeded). "
                        "Halting API requests until quota resets."
                    )
                    return ApiCallResult(
                        success=False,
                        data={},
                        error_message="YouTube API quota exhausted (HTTP 403 quotaExceeded). Requests paused.",
                    )

                # Invalid Key Check
                if e.code in (400, 401, 403) and ("keyInvalid" in str(error_body) or "API_KEY_INVALID" in str(error_body)):
                    logger.error(f"Invalid YouTube API key provided: {reason}")
                    return ApiCallResult(
                        success=False,
                        data={},
                        error_message="Invalid YouTube API key. Please check your key in Google Cloud Console.",
                    )

                # Server error (5xx) or Rate Limit (429) -> Retry with exponential backoff
                if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    logger.warning(f"HTTP {e.code} error from YouTube API. Retrying in {backoff_sec:.1f}s (attempt {attempt}/{max_retries})...")
                    time.sleep(backoff_sec)
                    backoff_sec *= 2.0
                    continue

                return ApiCallResult(
                    success=False,
                    data={},
                    error_message=f"YouTube API HTTP error {e.code}: {reason or e.reason}",
                )

            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < max_retries:
                    logger.warning(f"Network error: {e}. Retrying in {backoff_sec:.1f}s...")
                    time.sleep(backoff_sec)
                    backoff_sec *= 2.0
                    continue
                return ApiCallResult(
                    success=False,
                    data={},
                    error_message=f"Network connection failed: {e}",
                )

        return ApiCallResult(
            success=False,
            data={},
            error_message="Exceeded maximum retries contacting YouTube API.",
        )

    def _generate_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Create a deterministic hash key for API request parameters."""
        sorted_pairs = sorted([(k, str(v)) for k, v in params.items() if k != "key"])
        raw = f"{endpoint}:" + "&".join(f"{k}={v}" for k, v in sorted_pairs)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def get_quota_guide() -> Dict[str, Any]:
        """Documentation on assigned quotas in Google Cloud."""
        today_usage = db.get_today_quota_usage()
        return {
            "default_standard_quota": 10000,
            "estimated_used_today": today_usage["units_used"],
            "requests_made_today": today_usage["request_count"],
            "last_updated": today_usage["last_updated"],
            "unit_costs": {
                "search.list": 100,
                "videos.list": 1,
                "channels.list": 1,
            },
            "how_to_verify_quota": [
                "1. Go to Google Cloud Console (https://console.cloud.google.com/).",
                "2. Navigate to 'APIs & Services' -> 'YouTube Data API v3'.",
                "3. Click 'Quotas & System Limits' to view your project's exact daily quota and current usage.",
                "4. Note: Some new Google Cloud projects may receive different quotas (e.g. 10,000 queries/day).",
            ],
        }
