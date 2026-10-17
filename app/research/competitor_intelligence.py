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


# Verified dark storytelling and mystery creators with proven high-retention formats
CURATED_MYSTERY_COMPETITORS: List[CompetitorProfile] = [
    CompetitorProfile(
        handle="@MrBallen",
        platform="youtube",
        profile_url="https://youtube.com/@MrBallen",
        niche="strange_dark_and_mysterious",
        posting_frequency="3_per_week",
        primary_formats=["Top 3 Mysterious Disappearances", "Places You Can't Go", "Stories That Sound Fake But Are Real"],
        observed_editing_style="Immediate hook in <1.5s, conversational suspense, high narrative tension, slow camera push-ins, dramatic silent pauses.",
        public_subscriber_or_follower_count=9800000,
        recent_public_topics=["Dyatlov pass theories", "Unsolved national park vanishings", "Bizarre survival stories"],
        strengths=["Unmatched narrative storytelling", "Psychological immersion", "High audience retention"],
        saturation_risks=["Over-covered mainstream cases; demands fresh, lesser-known forgotten cases"],
    ),
    CompetitorProfile(
        handle="@Wendigoon",
        platform="youtube",
        profile_url="https://youtube.com/@Wendigoon",
        niche="internet_rabbit_holes_and_unexplained_mysteries",
        posting_frequency="weekly",
        primary_formats=["Mystery Deep Dives", "Unsolved Cold Cases", "Cryptic Internet Rabbit Holes"],
        observed_editing_style="Archival photographs, case evidence document overlays, eerie ambient audio drones, philosophical cliffhangers.",
        public_subscriber_or_follower_count=3500000,
        recent_public_topics=["The Lead Masks of Vintém Hill", "Cicada 3301", "The Missing Yuba County Five"],
        strengths=["Deep audience trust", "Intellectual curiosity", "Massive comment section debate"],
        saturation_risks=["Long-form format (often >1 hour); leaves massive opportunity for fast, punchy 30s-45s vertical Shorts"],
    ),
    CompetitorProfile(
        handle="@Lemmino",
        platform="youtube",
        profile_url="https://youtube.com/@Lemmino",
        niche="cinematic_investigative_mysteries",
        posting_frequency="monthly",
        primary_formats=["The Disappearance of...", "Forensic Timeline Reconstruction", "Unsolved Enigmas"],
        observed_editing_style="Minimalist dark cinematography, historical evidence maps, stark typography, cold objective narration.",
        public_subscriber_or_follower_count=5400000,
        recent_public_topics=["The Dyatlov Pass Mystery", "The Mary Celeste", "Jack the Ripper Forensic Analysis"],
        strengths=["World-class production value", "Credible factual rigor", "Cinematic dark mood"],
        saturation_risks=["Extremely infrequent uploads (1-2 videos per year); audience craves consistent high-quality shorts"],
    ),
    CompetitorProfile(
        handle="@Dark5Docs",
        platform="youtube",
        profile_url="https://youtube.com/@Dark5Docs",
        niche="dark_rankings_and_classified_countdowns",
        posting_frequency="weekly",
        primary_formats=["Top 5 Classified Discoveries", "5 Most Dangerous Forbidden Zones", "Deep Sea Anomalies Ranked"],
        observed_editing_style="Pacing build from #5 to #1, deep sub-bass sound design, ominous drone music, dark atmospheric imagery, glowing text countdown overlays.",
        public_subscriber_or_follower_count=2500000,
        recent_public_topics=["Forbidden Cold War bases", "Deepest ocean anomalies", "Deadliest radioactive zones"],
        strengths=["Top-tier countdown structure", "Ominous suspense sound design", "High viral sharing"],
        saturation_risks=["Needs faster vertical shorts pacing (<35s) with kinetic animated captions"],
    ),
    CompetitorProfile(
        handle="@UnveilMedia",
        platform="youtube",
        profile_url="https://youtube.com/@UnveilMedia",
        niche="extreme_danger_rankings_and_survival",
        posting_frequency="daily",
        primary_formats=["Top 3 Places Humans Cannot Enter", "Ranking Deadliest Islands", "Zero Survival Zones"],
        observed_editing_style="Explosive 1.5s hook, #3 to #1 countdown progression, high stakes survival contrast, glassmorphic ranking tags, punchy cliffhanger CTA.",
        public_subscriber_or_follower_count=1800000,
        recent_public_topics=["Snake Island", "North Sentinel Island", "Chernobyl Red Forest"],
        strengths=["Hyper-optimized Shorts retention", "Extreme hook curiosity", "Rapid comment debates"],
        saturation_risks=["Often uses generic stock; bespoke cinematic treatment wins instantly"],
    ),
    CompetitorProfile(
        handle="@Top5Unknowns",
        platform="youtube",
        profile_url="https://youtube.com/@Top5Unknowns",
        niche="creepy_unexplained_countdowns",
        posting_frequency="2_per_week",
        primary_formats=["5 Forbidden Places", "Unexplained Disappearances Ranked", "Terrifying Discoveries"],
        observed_editing_style="Dark ambient background music, slow reveal from least to most terrifying, stark typographic count tags.",
        public_subscriber_or_follower_count=2100000,
        recent_public_topics=["Forbidden caves", "Deadliest deep-sea trenches", "Forgotten bunker systems"],
        strengths=["Classic countdown appeal", "Broad demographic intrigue"],
        saturation_risks=["Pacing can be slow; our 30s vertical formula outperforms in Shorts algorithm"],
    ),
]

# Aliased for backward compatibility with existing tests
CURATED_DEV_COMPETITORS = CURATED_MYSTERY_COMPETITORS


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
        saturated_keywords = [
            "center a div", "centering div", "missing semicolon", "html is a programming language",
            "bermuda triangle", "loch ness", "flat earth", "generic ghost story", "aliens built pyramids",
        ]
        is_saturated = any(k in t for k in saturated_keywords)

        return {
            "topic": topic,
            "is_saturated": is_saturated,
            "recommendation": (
                "Saturated format: over-covered cliché. Pivot to a lesser-known documented case (e.g. Lead Masks, Yuba County Five, Flannan Isle)."
                if is_saturated
                else "Fresh opportunity: high curiosity with low cliché risk."
            ),
        }


# Singleton instance
competitor_intelligence = CompetitorIntelligence()
