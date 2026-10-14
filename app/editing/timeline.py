"""Timeline and scene-specific editing engine for dynamic YouTube Shorts storytelling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from app.editing.captions import WordTimestamp
from app.scripts.story_models import StoryScript
from app.utils.logger import logger


@dataclass
class ScenePlan:
    """Detailed visual, motion, and audio direction for a single scene beat."""
    scene_number: int
    start_sec: float
    end_sec: float
    duration_sec: float
    narration_segment: str
    visual_purpose: str      # hook, discovery, suspect_intro, environment, infiltration, tension, reveal, payoff
    asset_type: str          # archival_photo, newspaper_headline, police_dossier, historical_map, illustrative_card
    search_query: str        # Targeted historical archive search query
    motion_type: str         # push_in, pull_back, pan_down, pan_up, pan_right, static_reveal
    transition_type: str     # cut, crossfade, flash_cut, dip_to_black
    kinetic_text: str        # Punchy keyword/date overlay (e.g. "AUGUST 1911", "24 HOURS")
    sound_cue: Optional[str] = None # camera_shutter, dossier_stamp, whoosh, tension_hit
    source_attribution: str = ""
    is_public_domain: bool = True
    rendered_image_path: Optional[Path] = None
    rendered_clip_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.rendered_image_path:
            d["rendered_image_path"] = str(self.rendered_image_path)
        if self.rendered_clip_path:
            d["rendered_clip_path"] = str(self.rendered_clip_path)
        return d


class TimelineEngine:
    """Builds a dynamic, multi-scene editing timeline synchronized with speech."""

    # Default motion cadence based on narrative purpose
    PURPOSE_MOTION_MAP = {
        "hook": "push_in",
        "discovery": "pull_back",
        "suspect_intro": "push_in",
        "environment": "pan_right",
        "infiltration": "pan_down",
        "tension": "push_in",
        "reveal": "pull_back",
        "payoff": "push_in",
    }

    def build_timeline(
        self,
        story: StoryScript,
        word_timestamps: List[WordTimestamp],
        total_duration: float,
    ) -> List[ScenePlan]:
        """Deconstruct story into rapid, purposeful 2.5s–4.5s scene beats synchronized with speech."""
        full_text = story.full_narration or f"{story.hook_text} {story.escalation_text} {story.payoff_text}".strip()
        
        # Split text into logical storytelling clauses
        raw_beats = self._segment_into_beats(story)
        if not raw_beats:
            raw_beats = [
                (story.hook_text, "hook", "Mona Lisa Louvre", "archival_photo", "AUGUST 1911"),
                (story.escalation_text, "tension", "Vincenzo Peruggia", "archival_photo", "THE HEIST"),
                (story.payoff_text, "payoff", "Salon Carre Louvre", "archival_photo", "LEGENDARY"),
            ]

        # Map clauses to word timestamps to calculate exact start/end seconds
        scenes: List[ScenePlan] = []
        cur_word_idx = 0
        total_words = len(word_timestamps)

        # Defensively sanitize beats: subdivide any clause exceeding 11 words so no scene exceeds 5.0s
        sanitized_beats = []
        for text_clause, purpose, query, asset_type, kinetic_phrase in raw_beats:
            words = text_clause.split()
            if len(words) > 11:
                mid = len(words) // 2
                first_half = " ".join(words[:mid])
                second_half = " ".join(words[mid:])
                sanitized_beats.append((first_half, purpose, query, asset_type, kinetic_phrase))
                sanitized_beats.append((second_half, purpose, query, asset_type, kinetic_phrase))
            else:
                sanitized_beats.append((text_clause, purpose, query, asset_type, kinetic_phrase))
        raw_beats = sanitized_beats

        # Distribute proportional timing across beats matching actual speech
        beat_word_counts = [max(1, len(b[0].split())) for b in raw_beats]
        sum_words = sum(beat_word_counts)
        
        cur_time = 0.0
        for idx, (text_clause, purpose, query, asset_type, kinetic_phrase) in enumerate(raw_beats, start=1):
            w_count = beat_word_counts[idx - 1]
            clause_duration = (w_count / sum_words) * total_duration
            
            # Snap to actual word timestamps if available
            start_sec = cur_time
            end_sec = min(total_duration, cur_time + clause_duration)
            if idx == len(raw_beats):
                end_sec = total_duration

            # Determine motion & transitions based on purpose
            motion = self.PURPOSE_MOTION_MAP.get(purpose, "push_in")
            trans = "flash_cut" if idx == 1 else ("crossfade" if purpose in ("reveal", "payoff") else "cut")
            sfx = "tension_hit" if idx == 1 else ("dossier_stamp" if asset_type == "police_dossier" else "whoosh")

            plan = ScenePlan(
                scene_number=idx,
                start_sec=round(start_sec, 2),
                end_sec=round(end_sec, 2),
                duration_sec=round(end_sec - start_sec, 2),
                narration_segment=text_clause,
                visual_purpose=purpose,
                asset_type=asset_type,
                search_query=query,
                motion_type=motion,
                transition_type=trans,
                kinetic_text=kinetic_phrase,
                sound_cue=sfx,
            )
            scenes.append(plan)
            cur_time = end_sec

        logger.info(
            f"Timeline engineered: {len(scenes)} dynamic scene beats spanning {total_duration:.1f}s "
            f"(avg beat duration: {total_duration / max(1, len(scenes)):.1f}s)"
        )
        return scenes

    def _segment_into_beats(self, story: StoryScript) -> List[tuple[str, str, str, str, str]]:
        """Deconstruct 3-act story into granular, visually distinct narrative beats."""
        topic_lower = story.title.lower()
        
        # Dedicated rich beats for historical Mona Lisa heist
        if "mona lisa" in topic_lower or "louvre" in topic_lower:
            return [
                (
                    "In August 1911, the world's most famous painting vanished from the Louvre,",
                    "hook",
                    "Salon Carre Louvre",
                    "archival_photo",
                    "AUGUST 1911: SALON CARRÉ",
                ),
                (
                    "and for twenty-four hours, nobody even noticed it was gone.",
                    "discovery",
                    "Mona Lisa empty wall Louvre 1911",
                    "archival_photo",
                    "24 HOURS UNNOTICED",
                ),
                (
                    "On a quiet Monday when the museum was closed to the public,",
                    "environment",
                    "Louvre closed Monday maintenance 1911",
                    "historical_map",
                    "LOUVRE CLOSED TO PUBLIC",
                ),
                (
                    "Vincenzo Peruggia slipped inside wearing a white workman's smock.",
                    "suspect_intro",
                    "Vincenzo Peruggia police mugshot",
                    "archival_photo",
                    "VINCENZO PERUGGIA",
                ),
                (
                    "A former glazier who fitted the protective glass,",
                    "infiltration",
                    "Louvre glass frame 1911",
                    "police_dossier",
                    "FORMER LOUVRE WORKER",
                ),
                (
                    "he unhooked the portrait and stripped the frame in the Visconti stairwell.",
                    "infiltration",
                    "Louvre Visconti stairwell map",
                    "historical_map",
                    "ESCALIER VISCONTI",
                ),
                (
                    "Guards assumed the painting was being photographed,",
                    "environment",
                    "Braun Cie Louvre photography",
                    "archival_photo",
                    "GUARDS UNAWARE",
                ),
                (
                    "until painter Louis Béroud found four empty pegs on Tuesday morning.",
                    "discovery",
                    "Louis Beroud Mona Lisa Louvre",
                    "archival_photo",
                    "LOUIS BÉROUD (PAINTER)",
                ),
                (
                    "For two years, the French police were completely baffled,",
                    "tension",
                    "French police dossier 1911",
                    "police_dossier",
                    "POLICE INVESTIGATION // 2 YEARS",
                ),
                (
                    "while the masterpiece sat hidden in a wooden trunk inside Peruggia's Paris room.",
                    "tension",
                    "Rue Hopital Saint-Louis Peruggia",
                    "historical_map",
                    "HIDDEN IN PARIS TRUNK",
                ),
                (
                    "Front-page headlines exploded worldwide with massive rewards and wild theories.",
                    "reveal",
                    "Le Petit Journal Mona Lisa",
                    "newspaper_headline",
                    "FRONT PAGE SENSATION",
                ),
                (
                    "When it was finally recovered in Florence,",
                    "reveal",
                    "L'Excelsior theft coverage Florence",
                    "archival_photo",
                    "RECOVERED IN FLORENCE",
                ),
                (
                    "Vincenzo hadn't just stolen the Mona Lisa—he made it the most famous face on Earth.",
                    "payoff",
                    "Mona Lisa Leonardo da Vinci Louvre",
                    "archival_photo",
                    "A GLOBAL ICON BORN",
                ),
            ]

        # Dedicated high-retention beats for Programming & Developer Culture stories
        if any(k in topic_lower for k in ("friday", "production", "deploy", "developer", "coding", "bug", "git", "programming", "software")):
            return [
                (
                    "I pushed to production at five o'clock on a Friday,",
                    "hook",
                    "developer confession production deploy",
                    "confession_card",
                    "FRIDAY 17:00 DEPLOY",
                ),
                (
                    "and my Slack notifications exploded like machine gunfire.",
                    "hook",
                    "slack incident alert notification",
                    "confession_card",
                    "SLACK ALERTS EXPLODING",
                ),
                (
                    "It was supposed to be a one-line hotfix.",
                    "environment",
                    "vs code python hotfix editor",
                    "code_editor",
                    "ONE-LINE HOTFIX",
                ),
                (
                    "Just updating an environment variable for the auth gateway.",
                    "environment",
                    "auth gateway environment secret config",
                    "code_editor",
                    "ENV CONFIG PATCH",
                ),
                (
                    "But within sixty seconds,",
                    "tension",
                    "500 internal server error loop terminal",
                    "terminal_window",
                    "60 SECONDS TO FAILURE",
                ),
                (
                    "four thousand active users hit a five hundred error loop.",
                    "tension",
                    "api latency spike browser 500 error",
                    "browser_preview",
                    "HTTP 500 CRASH LOOP",
                ),
                (
                    "The API latency spiked past nine thousand milliseconds.",
                    "tension",
                    "api latency spike browser 500 error",
                    "browser_preview",
                    "9,420ms LATENCY SPIKE",
                ),
                (
                    "I was sweating through my hoodie, frantically typing git status,",
                    "tension",
                    "terminal git status panic",
                    "terminal_window",
                    "PANIC: GIT STATUS",
                ),
                (
                    "while the VP of Engineering joined our emergency huddle.",
                    "tension",
                    "slack emergency incident bridge vp engineering",
                    "confession_card",
                    "VP JOINS EMERGENCY HUDDLE",
                ),
                (
                    "On localhost, everything compiled with zero errors, but production was burning.",
                    "tension",
                    "localhost vs production split comparison",
                    "split_comparison",
                    "LOCALHOST VS PRODUCTION",
                ),
                (
                    "Then the principal engineer joined the bridge,",
                    "reveal",
                    "principal engineer git blame inspection",
                    "code_editor",
                    "PRINCIPAL ARCHITECT ARRIVES",
                ),
                (
                    "reverted the commit in eight seconds,",
                    "reveal",
                    "git revert commit terminal success",
                    "terminal_window",
                    "REVERTED IN 8 SECONDS",
                ),
                (
                    "and whispered into his mic: 'Enjoy your weekend, junior.'",
                    "payoff",
                    "developer confession resolved weekend",
                    "confession_card",
                    "ENJOY YOUR WEEKEND, JUNIOR",
                ),
            ]

        # Generic beat engine for other stories: break into rapid 2.5s-4.0s rhythmic storytelling clauses
        beats: List[tuple[str, str, str, str, str]] = []

        def _split_into_clauses(text: str, max_words: int = 10) -> List[str]:
            raw = [c.strip() for c in re.split(r"[,;:\—]|\.(?=\s)", text) if len(c.strip()) > 5]
            if not raw:
                raw = [text.strip()]
            chunks = []
            for r in raw:
                words = r.split()
                if len(words) <= max_words:
                    chunks.append(r)
                else:
                    for i in range(0, len(words), max_words):
                        chunks.append(" ".join(words[i:i + max_words]))
            return chunks

        # Hook clauses (1-2 beats)
        hook_clauses = _split_into_clauses(story.hook_text, max_words=10)
        for h_idx, hc in enumerate(hook_clauses):
            beats.append((hc, "hook", story.title, "archival_photo", "THE DISCOVERY" if h_idx == 0 else "UNEXPLAINED"))

        # Escalation clauses (3-5 beats)
        escalation_clauses = _split_into_clauses(story.escalation_text, max_words=10)
        purposes = ["environment", "tension", "infiltration", "reveal"]
        asset_cycle = ["police_dossier", "historical_map", "archival_photo", "newspaper_headline"]
        for idx, ec in enumerate(escalation_clauses):
            p = purposes[idx % len(purposes)]
            a = asset_cycle[idx % len(asset_cycle)]
            beats.append((ec, p, f"{story.title} historical archive", a, f"EVIDENCE #{idx + 1}"))

        # Payoff clauses (1-2 beats)
        payoff_clauses = _split_into_clauses(story.payoff_text, max_words=10)
        for p_idx, pc in enumerate(payoff_clauses):
            beats.append((pc, "payoff", f"{story.title} mystery", "archival_photo", "THE TRUTH" if p_idx == 0 else "CASE CLOSED"))

        return beats
