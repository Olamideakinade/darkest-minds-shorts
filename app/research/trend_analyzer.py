"""Trend intelligence, view velocity measurement, and channel baseline analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.database.db import db
from app.database.models import ResearchedVideo, VideoObservation
from app.utils.logger import logger



@dataclass
class VelocityMetric:
    """Measured view velocity between historical observation snapshots."""
    hourly_velocity: Optional[float]
    daily_velocity: Optional[float]
    has_multiple_observations: bool
    observation_count: int
    elapsed_hours: float
    explanation: str


@dataclass
class ChannelBaselineMetric:
    """Channel baseline context for evaluating outperformance."""
    channel_id: str
    sample_size: int
    median_views: float
    mean_views: float
    is_sufficient_sample: bool
    performance_ratio: Optional[float]
    explanation: str


class TrendAnalyzer:
    """Analyzes public performance trends without assuming virality or fabricating velocity."""

    @staticmethod
    def calculate_view_velocity(video_id: str) -> VelocityMetric:
        """Calculate view velocity ONLY if at least two timestamped observations exist.

        Strictly avoids fabricating velocity when only 1 snapshot exists.
        """
        observations = db.get_video_observations(video_id)
        count = len(observations)

        if count < 2:
            return VelocityMetric(
                hourly_velocity=None,
                daily_velocity=None,
                has_multiple_observations=False,
                observation_count=count,
                elapsed_hours=0.0,
                explanation=(
                    f"View velocity unavailable ({count} snapshot recorded). "
                    "Velocity requires at least 2 distinct observations separated in time."
                ),
            )

        # Sort observations chronologically
        sorted_obs = sorted(observations, key=lambda x: x.observed_at)
        first_obs = sorted_obs[0]
        latest_obs = sorted_obs[-1]

        try:
            t0 = datetime.fromisoformat(first_obs.observed_at.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(latest_obs.observed_at.replace("Z", "+00:00"))
            elapsed_seconds = (t1 - t0).total_seconds()
            elapsed_hours = elapsed_seconds / 3600.0

            # Minimum 30 minutes between snapshots to calculate a meaningful slope
            if elapsed_hours < 0.5:
                return VelocityMetric(
                    hourly_velocity=None,
                    daily_velocity=None,
                    has_multiple_observations=True,
                    observation_count=count,
                    elapsed_hours=elapsed_hours,
                    explanation=(
                        f"Observation interval too brief ({elapsed_hours * 60:.1f} minutes). "
                        "Minimum 30 minutes required for statistically sound slope."
                    ),
                )

            delta_views = latest_obs.view_count - first_obs.view_count
            # In rare cases of YouTube auditing subtracting bot views, floor delta at 0
            delta_views = max(0, delta_views)

            hourly_v = round(delta_views / elapsed_hours, 2)
            daily_v = round(hourly_v * 24.0, 2)

            return VelocityMetric(
                hourly_velocity=hourly_v,
                daily_velocity=daily_v,
                has_multiple_observations=True,
                observation_count=count,
                elapsed_hours=round(elapsed_hours, 2),
                explanation=(
                    f"Estimated velocity: ~{hourly_v:,.0f} views/hour based on "
                    f"{delta_views:,.0f} new views over {elapsed_hours:.1f} hours ({count} observations)."
                ),
            )

        except Exception as e:
            logger.debug(f"Velocity calculation error for {video_id}: {e}")
            return VelocityMetric(
                hourly_velocity=None,
                daily_velocity=None,
                has_multiple_observations=True,
                observation_count=count,
                elapsed_hours=0.0,
                explanation=f"Error parsing observation timestamps: {e}",
            )

    @staticmethod
    def calculate_channel_baseline(channel_id: str, current_video_views: int) -> ChannelBaselineMetric:
        """Compare a video's view count against its channel's recent observed baseline."""
        videos = db.get_channel_videos(channel_id)
        sample_size = len(videos)

        if sample_size < 2:
            return ChannelBaselineMetric(
                channel_id=channel_id,
                sample_size=sample_size,
                median_views=float(current_video_views),
                mean_views=float(current_video_views),
                is_sufficient_sample=False,
                performance_ratio=None,
                explanation=f"Insufficient channel baseline data ({sample_size} video recorded for channel).",
            )

        views_list = sorted([v.view_count for v in videos if v.view_count > 0])
        if not views_list:
            views_list = [current_video_views]

        mean_v = sum(views_list) / len(views_list)
        n = len(views_list)
        median_v = views_list[n // 2] if n % 2 != 0 else (views_list[n // 2 - 1] + views_list[n // 2]) / 2.0

        if median_v > 0:
            ratio = round(current_video_views / median_v, 2)
        else:
            ratio = 1.0

        if ratio >= 1.5:
            perf_note = f"Outperforming channel median by {ratio:.1f}x"
        elif ratio <= 0.6:
            perf_note = f"Underperforming channel median ({ratio:.1f}x)"
        else:
            perf_note = f"Performing within normal channel range ({ratio:.1f}x)"

        return ChannelBaselineMetric(
            channel_id=channel_id,
            sample_size=sample_size,
            median_views=round(median_v, 1),
            mean_views=round(mean_v, 1),
            is_sufficient_sample=True,
            performance_ratio=ratio,
            explanation=f"{perf_note} (channel median: {median_v:,.0f} views across {sample_size} videos).",
        )

    @staticmethod
    def detect_topic_momentum(topic: str, all_videos: List[ResearchedVideo]) -> Dict[str, Any]:
        """Detect cross-source interest: whether a topic appears across multiple channels."""
        normalized_topic = topic.lower()
        matching_videos = []
        unique_channels = set()

        # Split topic into meaningful keyword tokens (len >= 4)
        tokens = [t.strip("?,!.:'\"") for t in normalized_topic.split() if len(t) >= 4]

        for v in all_videos:
            v_title = v.title.lower()
            # If 2 or more major tokens match, consider related
            matches = sum(1 for token in tokens if token in v_title)
            if matches >= 2 or (len(tokens) == 1 and tokens[0] in v_title):
                matching_videos.append(v)
                unique_channels.add(v.channel_id)

        count = len(matching_videos)
        channel_count = len(unique_channels)

        return {
            "related_video_count": count,
            "unique_channels_count": channel_count,
            "has_cross_channel_momentum": channel_count >= 2,
            "matching_video_ids": [v.video_id for v in matching_videos[:5]],
            "explanation": (
                f"Topic appeared in {count} videos across {channel_count} distinct channels."
                if count > 0
                else "Single standalone video observation so far."
            ),
        }
