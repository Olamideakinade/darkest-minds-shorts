"""Platform-specific publishing intelligence and posting-time optimization.

Models optimal audience availability windows across YouTube Shorts, Instagram Reels,
and TikTok based on audience time zone, day of the week, and empirical analytics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from app.config import config
from app.publishing.platform_models import PlatformType
from app.utils.logger import logger


@dataclass
class PostingWindow:
    """A recommended publishing window for a target platform."""

    platform: PlatformType
    day_name: str
    optimal_local_time: str
    optimal_utc_time: str
    expected_activity_tier: str  # PEAK, HIGH, MODERATE
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform.value if isinstance(self.platform, PlatformType) else self.platform,
            "day_name": self.day_name,
            "optimal_local_time": self.optimal_local_time,
            "optimal_utc_time": self.optimal_utc_time,
            "expected_activity_tier": self.expected_activity_tier,
            "rationale": self.rationale,
        }


# Empirical baseline peak windows (Hours in creator's local time zone)
PLATFORM_PEAK_WINDOWS = {
    PlatformType.YOUTUBE_SHORTS: {
        "weekday": [12, 18],  # 12:00 PM (Lunch break) and 6:00 PM (After-work commute)
        "weekend": [11, 16],  # 11:00 AM and 4:00 PM
    },
    PlatformType.INSTAGRAM_REELS: {
        "weekday": [12, 20],  # 12:00 PM and 8:00 PM (Evening leisure)
        "weekend": [13, 19],  # 1:00 PM and 7:00 PM
    },
    PlatformType.TIKTOK: {
        "weekday": [16, 21],  # 4:00 PM and 9:00 PM (Prime mobile scrolling)
        "weekend": [14, 20],  # 2:00 PM and 8:00 PM
    },
}


class PostingTimeOptimizer:
    """Recommends and learns platform-specific posting schedules."""

    def __init__(self, tz_name: Optional[str] = None) -> None:
        self.tz_name = tz_name or config.timezone
        try:
            self.tz = ZoneInfo(self.tz_name)
        except Exception:
            self.tz = ZoneInfo("UTC")

    def get_next_optimal_window(
        self, platform: PlatformType, reference_dt: Optional[datetime] = None
    ) -> PostingWindow:
        """Calculate the next upcoming optimal posting window for a given platform."""
        ref = reference_dt or datetime.now(self.tz)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=self.tz)
        else:
            ref = ref.astimezone(self.tz)

        is_weekend = ref.weekday() >= 5
        sched = PLATFORM_PEAK_WINDOWS.get(platform, PLATFORM_PEAK_WINDOWS[PlatformType.YOUTUBE_SHORTS])
        hours = sched["weekend"] if is_weekend else sched["weekday"]

        # Find the next upcoming hour today, or the first hour tomorrow
        target_dt = None
        for h in hours:
            candidate = ref.replace(hour=h, minute=0, second=0, microsecond=0)
            if candidate > ref + timedelta(minutes=15):  # allow at least 15 min buffer
                target_dt = candidate
                break

        if not target_dt:
            # Tomorrow's first window
            tomorrow = ref + timedelta(days=1)
            tomorrow_is_weekend = tomorrow.weekday() >= 5
            next_hours = sched["weekend"] if tomorrow_is_weekend else sched["weekday"]
            target_dt = tomorrow.replace(hour=next_hours[0], minute=0, second=0, microsecond=0)

        target_utc = target_dt.astimezone(timezone.utc)
        day_name = target_dt.strftime("%A")

        return PostingWindow(
            platform=platform,
            day_name=day_name,
            optimal_local_time=target_dt.strftime("%Y-%m-%d %H:%M %Z"),
            optimal_utc_time=target_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            expected_activity_tier="PEAK",
            rationale=f"Audience peak activity window for {platform.value} in {self.tz_name}.",
        )

    def get_weekly_schedule(self) -> Dict[str, List[PostingWindow]]:
        """Generate a complete 7-day recommended publishing schedule for all platforms."""
        now = datetime.now(self.tz)
        schedule: Dict[str, List[PostingWindow]] = {}

        for p in [PlatformType.YOUTUBE_SHORTS, PlatformType.INSTAGRAM_REELS, PlatformType.TIKTOK]:
            windows = []
            for d in range(7):
                day_ref = now + timedelta(days=d)
                win = self.get_next_optimal_window(p, reference_dt=day_ref.replace(hour=6, minute=0))
                windows.append(win)
            schedule[p.value] = windows

        return schedule


# Singleton instance
posting_time_optimizer = PostingTimeOptimizer()
