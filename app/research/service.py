"""High-level service coordinating YouTube research, trend scoring, and persistence."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import config
from app.database.db import db
from app.database.models import OpportunityAnalysis, ResearchedVideo, VideoObservation, utc_now_iso
from app.research.opportunity_scorer import OpportunityScorer
from app.research.registry import DEFAULT_RESEARCH_QUERIES, ResearchConfig
from app.research.reporter import ResearchReporter
from app.research.youtube_client import YouTubeResearchClient
from app.utils.logger import logger


# Verified Darkest Minds 101 storytelling sample dataset for offline / testing / uncredentialed demonstration
DEMO_STORY_DATA = [
    {
        "video_id": "demo_vid_001",
        "channel_id": "demo_chan_darkestminds",
        "channel_title": "Darkest Minds 101",
        "title": "The Three Keepers Who Vanished from Flannan Isle",
        "published_at": "2026-10-01T14:00:00Z",
        "duration_sec": 28,
        "view_count": 820000,
        "like_count": 68200,
        "comment_count": 5150,
        "tags": ["unsolved mystery", "strange disappearance", "flannan isles", "dark stories", "history mystery"],
    },
    {
        "video_id": "demo_dev_002",
        "channel_id": "demo_chan_darkestminds",
        "channel_title": "Darkest Minds 101",
        "title": "The Bizarre Lead Masks Case of Vintém Hill",
        "published_at": "2026-10-04T16:30:00Z",
        "duration_sec": 29,
        "view_count": 640000,
        "like_count": 52400,
        "comment_count": 3820,
        "tags": ["unsolved mystery", "lead masks", "unexplained event", "true mystery", "strange death"],
    },
    {
        "video_id": "demo_dev_003",
        "channel_id": "demo_chan_darkestminds",
        "channel_title": "Darkest Minds 101",
        "title": "The Unexplained Anomaly at Dyatlov Pass",
        "published_at": "2026-10-07T11:15:00Z",
        "duration_sec": 31,
        "view_count": 980000,
        "like_count": 87000,
        "comment_count": 6900,
        "tags": ["dyatlov pass", "unsolved mystery", "strange event", "blizzard disappearance", "investigation"],
    },
    {
        "video_id": "demo_dev_004",
        "channel_id": "demo_chan_darkestminds",
        "channel_title": "Darkest Minds 101",
        "title": "The Ghost Ship Mary Celeste: Floating With No Crew",
        "published_at": "2026-10-10T09:00:00Z",
        "duration_sec": 24,
        "view_count": 290000,
        "like_count": 22100,
        "comment_count": 1420,
        "tags": ["mary celeste", "ghost ship", "unsolved disappearance", "maritime mystery", "abandoned"],
    },
]


class ResearchService:
    """Orchestrates public YouTube research, historical tracking, and opportunity scoring."""

    def __init__(
        self,
        api_client: Optional[YouTubeResearchClient] = None,
        scorer: Optional[OpportunityScorer] = None,
        database: Optional[Database] = None,
    ) -> None:
        self.db = database or db
        self.api_client = api_client or YouTubeResearchClient()
        self.scorer = scorer or OpportunityScorer()

    def run_research(
        self,
        query: Optional[str] = None,
        max_videos: int = 15,
        use_demo_if_unconfigured: bool = True,
    ) -> Dict[str, Any]:
        """Execute a full research cycle for a query or default registry."""
        search_query = query or DEFAULT_RESEARCH_QUERIES[0]
        logger.info(f"Initiating research cycle for query: '{search_query}'")

        researched_videos: List[ResearchedVideo] = []
        is_demo_mode = False

        if self.api_client.is_configured:
            # 1. Real YouTube API search
            search_res = self.api_client.search_story_videos(query=search_query, max_results=max_videos)
            if not search_res.success:
                logger.warning(f"YouTube search failed: {search_res.error_message}")
                return {
                    "success": False,
                    "error": search_res.error_message,
                    "videos": [],
                    "opportunities": [],
                }

            items = search_res.data.get("items", [])
            video_ids = []
            for it in items:
                v_id = it.get("id", {}).get("videoId") if isinstance(it.get("id"), dict) else it.get("id")
                if v_id:
                    video_ids.append(v_id)

            # 2. Batch fetch detailed stats and duration (1 quota unit for up to 50 videos)
            if video_ids:
                details_res = self.api_client.get_video_details_batch(video_ids)
                detail_items = details_res.data.get("items", []) if details_res.success else items
                for it in detail_items:
                    v = self.api_client.parse_video_item(it)
                    if v:
                        researched_videos.append(v)
        else:
            if not use_demo_if_unconfigured:
                return {
                    "success": False,
                    "error": "YouTube API key not configured. Operating in live-only mode.",
                    "videos": [],
                    "opportunities": [],
                }
            logger.info("YouTube API key not configured. Using explicit offline verified sample dataset for demonstration.")
            is_demo_mode = True
            for demo_item in DEMO_STORY_DATA:
                v = ResearchedVideo(
                    video_id=demo_item["video_id"],
                    channel_id=demo_item["channel_id"],
                    channel_title=demo_item["channel_title"],
                    title=demo_item["title"],
                    published_at=demo_item["published_at"],
                    duration_sec=demo_item["duration_sec"],
                    view_count=demo_item["view_count"],
                    like_count=demo_item["like_count"],
                    comment_count=demo_item["comment_count"],
                    topic_tags=demo_item["tags"],
                    hook_summary=demo_item["title"],
                    created_at=utc_now_iso(),
                )
                researched_videos.append(v)

        # 3. Persist videos and point-in-time observations in SQLite
        for v in researched_videos:
            self.db.save_researched_video(v)
            # Create timestamped observation snapshot
            obs = VideoObservation(
                video_id=v.video_id,
                channel_id=v.channel_id,
                view_count=v.view_count,
                like_count=v.like_count,
                comment_count=v.comment_count,
                observed_at=utc_now_iso(),
                search_query=search_query,
                discovery_source="demo_dataset" if is_demo_mode else "youtube_api_search",
            )
            self.db.record_observation(obs)

        # 4. Evaluate each video with OpportunityScorer
        opportunities: List[OpportunityAnalysis] = []
        for v in researched_videos:
            opp = self.scorer.evaluate_video(video=v, all_videos=researched_videos)
            self.db.save_opportunity_analysis(opp)
            opportunities.append(opp)

        # Sort opportunities by composite score descending
        opportunities.sort(key=lambda x: x.composite_score, reverse=True)

        logger.info(
            f"Research complete: {len(researched_videos)} videos analyzed, "
            f"{len(opportunities)} opportunities formulated (Top score: {opportunities[0].composite_score if opportunities else 0})."
        )

        return {
            "success": True,
            "query": search_query,
            "is_demo_mode": is_demo_mode,
            "videos": researched_videos,
            "opportunities": opportunities,
            "report_text": ResearchReporter.generate_text_report(
                opportunities=opportunities,
                videos=researched_videos,
                api_client=self.api_client,
                search_query=search_query,
            ),
        }

    def get_latest_report(self) -> str:
        """Fetch latest opportunities and videos from DB to generate a current report."""
        opportunities = self.db.list_opportunity_analyses(limit=20)
        videos = self.db.get_researched_videos(limit=50)
        return ResearchReporter.generate_text_report(
            opportunities=opportunities,
            videos=videos,
            api_client=self.api_client,
            search_query="Stored Research History",
        )

    def list_top_opportunities(self, limit: int = 10) -> List[OpportunityAnalysis]:
        """Fetch top ranked opportunity records from SQLite."""
        return self.db.list_opportunity_analyses(limit=limit)

