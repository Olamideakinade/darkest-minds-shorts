"""Creative Director engine for MhideDev creator brand.

Formulates, scores, and selects high-retention video concepts across the 7 developer
content pillars using multi-attribute evaluation criteria (originality, relevance,
clarity, feasibility, shareability, brand fit).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid

from app.config import config
from app.utils.logger import logger


# The 7 Core Content Pillars for MhideDev
CONTENT_PILLARS = {
    "shared_developer_confessions": "Relatable developer mistakes, secret shortcuts, imposter syndrome, and production close-calls.",
    "programming_humour": "Observational comedy regarding code reviews, meetings, frameworks, and engineering habits.",
    "ai_coding_experiments": "Empirical tests of AI coding agents, Copilot failures, and real developer workflows.",
    "website_development": "Practical frontend/backend builds, weird CSS/JS quirks, and architectural decisions.",
    "developer_mistakes": "Real technical autopsies of historic or personal engineering bugs and lessons learned.",
    "technology_commentary": "Modern software engineering news, framework trends, and industry observations.",
    "creative_engineering": "Behind-the-scenes tooling, automation builds, and custom developer utilities.",
}


@dataclass
class CandidateConcept:
    """A generated candidate video concept prior to production selection."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    pillar: str = "shared_developer_confessions"
    premise: str = ""
    opening_hook: str = ""
    secondary_hook: str = ""
    viewer_emotion: str = "relatable_relief"
    punchline_payoff: str = ""
    code_language: str = "python"  # python, javascript, typescript, sql, rust
    visual_setup: str = "vs_code_editor_and_terminal"

    # Multi-attribute scoring (0.0 to 100.0)
    score_originality: float = 85.0
    score_relevance: float = 90.0
    score_clarity: float = 95.0
    score_feasibility: float = 95.0
    score_shareability: float = 90.0
    score_brand_fit: float = 95.0

    @property
    def composite_score(self) -> float:
        """Weighted score favoring clarity, relevance, and shareability."""
        return round(
            (self.score_originality * 0.15)
            + (self.score_relevance * 0.25)
            + (self.score_clarity * 0.20)
            + (self.score_feasibility * 0.15)
            + (self.score_shareability * 0.15)
            + (self.score_brand_fit * 0.10),
            1,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["composite_score"] = self.composite_score
        return d


@dataclass
class CreativeBrief:
    """Full creative direction brief passed to Scripting and Media Production."""

    concept: CandidateConcept
    target_audience: str = "Software engineers, full-stack developers, tech students, dev leads"
    intended_duration_sec: int = 42
    pacing_strategy: str = "rapid_cuts (1.8s - 2.8s per beat)"
    editing_techniques: List[str] = field(default_factory=lambda: [
        "cold_open_crisis",
        "fast_screen_cut",
        "punch_in_zoom",
        "sound_effect_sync",
        "silence_before_punchline",
    ])
    audio_strategy: str = "Crisp Christopher voiceover, lo-fi code background (-18dB), mechanical switch SFX"
    caption_plan: str = "Word-level kinetic captions in lower third with active gold highlight"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept.to_dict(),
            "target_audience": self.target_audience,
            "intended_duration_sec": self.intended_duration_sec,
            "pacing_strategy": self.pacing_strategy,
            "editing_techniques": self.editing_techniques,
            "audio_strategy": self.audio_strategy,
            "caption_plan": self.caption_plan,
            "created_at": self.created_at,
        }


class CreativeDirector:
    """Formulates and selects the optimal MhideDev video concept for production."""

    def formulate_candidates(self, topic_seed: str, preferred_pillar: Optional[str] = None) -> List[CandidateConcept]:
        """Generate diverse candidate concepts based on the topic seed."""
        pillar = preferred_pillar or "shared_developer_confessions"
        candidates: List[CandidateConcept] = []

        # Candidate 1: Direct Confession / Crisis
        candidates.append(
            CandidateConcept(
                title=f"{topic_seed}: The Friday Deploy",
                pillar="shared_developer_confessions",
                premise="Deploying an untested bugfix at 5:00 PM on a Friday and watching the entire API crumble.",
                opening_hook="I broke production at 5:02 PM on a Friday, and my Slack notifications sounded like machine gunfire.",
                secondary_hook="One tiny environment variable took down the authentication gateway for four thousand users.",
                viewer_emotion="panic_turning_into_shared_humour",
                punchline_payoff="The senior engineer fixed it in twelve seconds, smiled, and said: 'First time?'",
                code_language="python",
                visual_setup="vs_code_editor_and_terminal",
                score_originality=88.0,
                score_relevance=98.0,
                score_clarity=95.0,
                score_feasibility=95.0,
                score_shareability=96.0,
                score_brand_fit=98.0,
            )
        )

        # Candidate 2: Relatable Debugging Irony
        candidates.append(
            CandidateConcept(
                title=f"{topic_seed}: The 4-Hour Bug",
                pillar="programming_humour",
                premise="Spending half a workday diagnosing an invisible bug only to find a typo or git mishap.",
                opening_hook="I spent four hours tracing a memory leak through twelve microservices.",
                secondary_hook="I blamed Docker, I blamed the cloud provider, and I blamed the junior dev.",
                viewer_emotion="cynical_amusement",
                punchline_payoff="Then I ran `git blame` on the broken line. It was me. Two years ago.",
                code_language="javascript",
                visual_setup="split_screen_git_blame",
                score_originality=85.0,
                score_relevance=95.0,
                score_clarity=92.0,
                score_feasibility=95.0,
                score_shareability=94.0,
                score_brand_fit=92.0,
            )
        )

        # Candidate 3: AI Coding Agent Reality
        candidates.append(
            CandidateConcept(
                title=f"{topic_seed}: When AI Codes",
                pillar="ai_coding_experiments",
                premise="Asking an AI coding assistant to optimize a simple function, and it rewrites the entire project architecture.",
                opening_hook="I asked the AI to fix a regex pattern, and it deleted my database migrations.",
                secondary_hook="It generated eighty lines of perfect code with zero compile errors—for a library that doesn't exist.",
                viewer_emotion="wry_recognition",
                punchline_payoff="AI won't take our jobs yet; it's still busy hallucinating dependencies.",
                code_language="typescript",
                visual_setup="terminal_and_browser_preview",
                score_originality=92.0,
                score_relevance=94.0,
                score_clarity=90.0,
                score_feasibility=90.0,
                score_shareability=92.0,
                score_brand_fit=95.0,
            )
        )

        return candidates

    def select_best_concept(self, candidates: List[CandidateConcept]) -> CreativeBrief:
        """Select the highest-scoring candidate and generate the formal production brief."""
        if not candidates:
            raise ValueError("No candidate concepts provided for creative selection.")

        # Sort by composite score descending
        ranked = sorted(candidates, key=lambda c: c.composite_score, reverse=True)
        winner = ranked[0]

        logger.info(
            f"CreativeDirector selected '{winner.title}' (Pillar: {winner.pillar}, Score: {winner.composite_score})"
        )

        return CreativeBrief(concept=winner)


# Singleton instance
creative_director = CreativeDirector()
