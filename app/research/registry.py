"""Research registry for storytelling keywords, competitor channels, and search filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any

# Curated starter search queries focused on developer culture and programming niches
DEFAULT_RESEARCH_QUERIES = [
    # Shared-experience developer confessions & mistakes
    "developer confessions funny",
    "worst coding mistakes production",
    "git push force production story",
    "junior developer vs senior developer reality",
    "programmer debugging for hours",
    # Programming humour & relatable situations
    "funny programming moments",
    "coding memes relatable",
    "software engineer friday deploy",
    "why software engineers hate meetings",
    # AI-assisted coding experiments & tech commentary
    "building an app with ai in 60 seconds",
    "coding with ai tools reality",
    "github copilot funny fails",
    "new programming language explained simply",
    # Website building & web dev challenges
    "frontend vs backend reality",
    "javascript weird behavior explained",
    "python tricks you didn't know",
    # Strange & verified history (legacy support)
    "bizarre technology history facts",
    "unexpected inventions that changed history",
]

# Starter competitor channel suggestions (empty by default; easily populated via config or CLI)
# Users can add verified competitor channel IDs using: ./run.sh research --add-channel <id> <title>
DEFAULT_COMPETITOR_CHANNELS: List[Dict[str, str]] = []

# Allowed content categories for YouTube video filtering
ALLOWED_CATEGORIES = [
    "27",  # Education
    "28",  # Science & Technology
    "24",  # Entertainment
    "22",  # People & Blogs
]


@dataclass
class ResearchConfig:
    """Configurable research registry and query parameters."""
    queries: List[str] = field(default_factory=lambda: list(DEFAULT_RESEARCH_QUERIES))
    competitor_channel_ids: List[str] = field(default_factory=list)
    max_videos_per_run: int = 25
    max_api_requests: int = 5
    cache_ttl_hours: int = 6
    lookback_days: int = 30
    min_evidence_observations: int = 1
    target_max_duration_sec: int = 60  # YouTube Shorts target duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_count": len(self.queries),
            "competitor_channels_count": len(self.competitor_channel_ids),
            "max_videos_per_run": self.max_videos_per_run,
            "max_api_requests": self.max_api_requests,
            "cache_ttl_hours": self.cache_ttl_hours,
            "lookback_days": self.lookback_days,
            "target_max_duration_sec": self.target_max_duration_sec,
        }
