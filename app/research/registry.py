"""Research registry for storytelling keywords, competitor channels, and search filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any

# Curated starter search queries focused on Darkest Minds 101 Dark Rankings & Extreme Mysteries
DEFAULT_RESEARCH_QUERIES = [
    # Viral Dark Rankings & Extremes (High Completion / Comment Traps)
    "most dangerous forbidden places on earth ranked",
    "top 5 scariest places on earth where survival is zero",
    "ranking the deepest darkest ocean trenches shorts",
    "top 5 mysterious abandoned places you cannot visit",
    "ranking the most dangerous islands in the world",
    "top 5 unexplained disappearances ranked by creepiness",
    "most isolated places on earth ranking shorts",
    "scariest anomalies found in nature ranked",
    # Classic unsolved mysteries & strange disappearances
    "unsolved mysteries real life documented",
    "strange disappearances unexplained evidence",
    "most bizarre cold cases in history",
    "flannan isles lighthouse mystery documentary",
    "dyatlov pass incident unexplained facts",
    # Internet rabbit holes & cryptic anomalies
    "internet rabbit holes unsolved",
    "mysterious radio signals numbers stations",
    "disturbing true mysteries shorts",
]

# Starter competitor channel benchmarks in the Dark Rankings & Extreme Mysteries niche
DEFAULT_COMPETITOR_CHANNELS: List[Dict[str, str]] = [
    {"channel_id": "UCi9a0a3B3L9l1wW109GqX7Q", "handle": "@Dark5Docs", "title": "Dark5", "niche": "Dark Countdowns & Classified Mysteries"},
    {"channel_id": "UCU_W0oE_odyqCpdBs65wQ7g", "handle": "@Top5Unknowns", "title": "Top 5 Unknowns", "niche": "Unexplained Phenomena & Creepy Countdowns"},
    {"channel_id": "UCrDkAvwZum-UTjHmzDI2iIw", "handle": "@UnveilMedia", "title": "Unveil", "niche": "Dangerous Places & Extreme Survival Rankings"},
    {"channel_id": "UCDkW7b4yvIuF56sUq0f0iGA", "handle": "@ReigarwComparisons", "title": "Reigarw Comparisons", "niche": "Scale Comparisons & Deadliest Zones"},
    {"channel_id": "UC_wKlsfZq1e9D8pT2U6Fzlg", "handle": "@Wendigoon", "title": "Wendigoon", "niche": "Dark Mysteries, Icebergs & Theories"},
    {"channel_id": "UC5pG7Z0q0mJz9Vvj8A1b2cQ", "handle": "@Nexpo", "title": "Nexpo", "niche": "Disturbing Media & Internet Mysteries"},
    {"channel_id": "UCv0035ucTrUgyS3V1L8l9mA", "handle": "@FernTV", "title": "Fern", "niche": "Geographic Anomalies & Forbidden Borders"},
    {"channel_id": "UCzQUP1qoWDoEbmsQxvdjxgQ", "handle": "@TheInfographicsShow", "title": "The Infographics Show", "niche": "Rankings, Survival Scenarios & Deadliest Spots"},
]

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
