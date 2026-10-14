"""Competitor Intelligence module for MhideDev creator brand.

Manages curated, public competitor channel tracking across programming and developer
culture on YouTube, Instagram, and TikTok, adhering strictly to platform terms and
public data limitations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.db import Database, db
from app.utils.logger import logger


@dataclass
class CompetitorProfile:
    """Public profile information for a tracked developer culture creator."""

    handle: str
    platform: str  # youtube, instagram, tiktok
    profile_url: str
    niche: str  # developer_humour, tech_commentary, coding_tutorials, faceless_engineering
    posting_frequency: str  # daily, 3_per_week, weekly
    primary_formats: List[str] = field(default_factory=list)
    observed_editing_style: str = ""
    public_subscriber_or_follower_count: int = 0
    recent_public_topics: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    saturation_risks: List[str] = field(default_factory=list)
    research_notes: str = ""
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    limitations: str = "Private retention, watch time, and impression metrics not publicly accessible."
    tracked_since: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Verified developer culture creators with distinct formats
CURATED_DEV_COMPETITORS: List[CompetitorProfile] = [
    CompetitorProfile(
        handle="@Fireship",
        platform="youtube",
        profile_url="https://youtube.com/@Fireship",
        niche="tech_commentary_and_developer_news",
        posting_frequency="3_per_week",
        primary_formats=["Code Report 60s", "100 Seconds of Code", "Dev Memes"],
        observed_editing_style="Extreme high cut density (1.2s-2.0s), kinetic zooms, rapid punchlines, green-screen memes.",
        public_subscriber_or_follower_count=3200000,
        recent_public_topics=["AI agent drama", "JavaScript framework fatigue", "Linux kernel bugs"],
        strengths=["Immediate hook in <1 second", "Ironclad developer credibility", "Topical velocity"],
        saturation_risks=["High visual noise can alienate beginners", "Format imitation is crowded"],
    ),
    CompetitorProfile(
        handle="@t3dotgg",
        platform="youtube",
        profile_url="https://youtube.com/@t3dotgg",
        niche="developer_opinion_and_engineering_culture",
        posting_frequency="daily",
        primary_formats=["Hot Takes", "Library Critiques", "Full-Stack Dev Rants"],
        observed_editing_style="Authentic screen-focused cuts, real GitHub repo audits, direct camera/screen split.",
        public_subscriber_or_follower_count=450000,
        recent_public_topics=["React server components", "Next.js updates", "Why junior devs struggle"],
        strengths=["Deep technical honesty", "High comment engagement and debates"],
        saturation_risks=["Heavy reliance on creator personality (less faceless-friendly)"],
    ),
    CompetitorProfile(
        handle="@NeetCode",
        platform="youtube",
        profile_url="https://youtube.com/@NeetCode",
        niche="coding_tutorials_and_career_humour",
        posting_frequency="3_per_week",
        primary_formats=["LeetCode in 60s", "Tech Interview Realities", "Algorithm Breakdown"],
        observed_editing_style="Clean code annotations, animated pointer arrows, calm deadpan comedic timing.",
        public_subscriber_or_follower_count=980000,
        recent_public_topics=["Two Sum explained simply", "Big O notation in 30 seconds", "FAANG interview traps"],
        strengths=["Highly bookmarkable/shareable educational value", "Deadpan humor resonates with engineers"],
        saturation_risks=["Standard interview questions can become repetitive"],
    ),
    CompetitorProfile(
        handle="@DevHumor",
        platform="instagram",
        profile_url="https://instagram.com/devhumor",
        niche="developer_humour",
        posting_frequency="daily",
        primary_formats=["Relatable Confessions", "Expectation vs Reality", "Friday Deploy Memes"],
        observed_editing_style="Text message screenshots, terminal error screen captures, split comparisons.",
        public_subscriber_or_follower_count=1200000,
        recent_public_topics=["Junior vs Senior PR reviews", "Deploying on Friday", "CSS centering jokes"],
        strengths=["Broad relatable appeal across all skill levels", "High share-to-friend ratio"],
        saturation_risks=["Centering div jokes and semi-colon memes are completely saturated"],
    ),
]


class CompetitorIntelligence:
    """Manages competitor tracking and analyzes strategic format opportunities."""

    def __init__(self, database: Optional[Database] = None, data_path: Optional[Path] = None) -> None:
        self.db = database or db
        self.data_path = data_path or (Path(__file__).resolve().parent.parent.parent / "data" / "competitor_profiles.json")
        self._competitors: Dict[str, CompetitorProfile] = {}
        self._load()

    def _load(self) -> None:
        """Load competitor registry from file or seed with curated profiles."""
        for comp in CURATED_DEV_COMPETITORS:
            key = f"{comp.platform}:{comp.handle}"
            self._competitors[key] = comp

        if self.data_path.exists():
            try:
                raw = json.loads(self.data_path.read_text(encoding="utf-8"))
                for item in raw:
                    p = CompetitorProfile(**item)
                    self._competitors[f"{p.platform}:{p.handle}"] = p
            except Exception as e:
                logger.warning(f"Competitor data loading note: {e}")

    def save(self) -> None:
        """Persist registry to disk."""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [p.to_dict() for p in self._competitors.values()]
        self.data_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def list_all(self, platform: Optional[str] = None) -> List[CompetitorProfile]:
        """Return all tracked competitor profiles, optionally filtered by platform."""
        if platform:
            return [p for p in self._competitors.values() if p.platform == platform.lower()]
        return list(self._competitors.values())

    def add_competitor(self, profile: CompetitorProfile) -> None:
        """Add or update a competitor profile."""
        key = f"{profile.platform}:{profile.handle}"
        self._competitors[key] = profile
        self.save()
        logger.info(f"Updated competitor profile: {profile.handle} on {profile.platform}")

    def evaluate_format_saturation(self, topic: str) -> Dict[str, Any]:
        """Assess whether a proposed topic or joke is saturated or fresh."""
        t = topic.lower()
        saturated_keywords = ["center a div", "centering div", "missing semicolon", "html is a programming language"]
        is_saturated = any(k in t for k in saturated_keywords)

        return {
            "topic": topic,
            "is_saturated": is_saturated,
            "recommendation": (
                "Saturated format: reframe into a concrete modern incident (e.g., flexbox overflow bug in Safari) or pivot to an authentic confession."
                if is_saturated
                else "Fresh opportunity: strong relevance with low cliché risk."
            ),
        }


# Singleton instance
competitor_intelligence = CompetitorIntelligence()
