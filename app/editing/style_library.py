"""Persistent, searchable editing style library for MhideDev content.

Stores short-form video editing techniques, timing rules, motion parameters,
and creative objectives for repeatable, high-retention video production.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EditingTechnique:
    """A documented, reusable short-form video editing technique."""

    id: str
    name: str
    category: str  # hook, pacing, visual_motion, audio_design, payoff, narrative
    objective: str
    when_to_use: str
    implementation_guide: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    reference_examples: List[str] = field(default_factory=list)
    limitations: str = ""
    confidence_score: float = 0.95

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Curated catalog of high-performing editing techniques for developer/tech content
CURATED_TECHNIQUES: List[EditingTechnique] = [
    EditingTechnique(
        id="cold_open_crisis",
        name="Cold-Open Crisis Hook",
        category="hook",
        objective="Grab attention within 1.2 seconds by opening in media res with an active disaster.",
        when_to_use="High-stakes developer confessions, bug stories, deployment failures.",
        implementation_guide="First frame shows an alarming terminal error or broken UI with urgent spoken audio. Zero intro logos.",
        parameters={"max_opening_latency_sec": 1.2, "initial_zoom": 1.15, "sound_cue": "error_buzz"},
        reference_examples=["'I just deleted the production database.'", "'Never push to main at 4:59 PM.'"],
        limitations="Must deliver on the premise; do not use for gentle educational explainers.",
    ),
    EditingTechnique(
        id="abrupt_comedic_reveal",
        name="Abrupt Comedic Reveal",
        category="payoff",
        objective="Create punchline contrast between calm developer confidence and catastrophic failure.",
        when_to_use="Punchline delivery, expectation vs reality, deployment disaster jokes.",
        implementation_guide="Hold a 250ms silence, then hard-cut to a massive red terminal stack trace or 500 error screen.",
        parameters={"pre_cut_silence_ms": 250, "visual_shake": True, "sound_cue": "record_scratch"},
        reference_examples=["'It compiled locally, so I pushed.' -> [FATAL ERROR]"],
        limitations="Requires precise audio timing; silence must feel intentional, not like missing audio.",
    ),
    EditingTechnique(
        id="punch_in_zoom",
        name="Kinetic Punch-In Zoom",
        category="visual_motion",
        objective="Force visual focus onto a specific line of faulty code or alarming message.",
        when_to_use="Highlighting a missing semicolon, wrong environment variable, or ridiculous commit message.",
        parameters={"zoom_factor": 1.35, "focal_transition_ms": 150, "reticle_overlay": True},
        implementation_guide="Crop dynamically from 100% full screen to 135% centered on the target line with a subtle highlight box.",
        reference_examples=["Zooming in on `if (user == null);` with a floating question mark."],
        limitations="Avoid over-zooming on low-resolution assets to prevent pixelation.",
    ),
    EditingTechnique(
        id="fast_screen_cut",
        name="Rapid Screen Pacing Cut",
        category="pacing",
        objective="Maintain high cognitive tempo by restricting shot durations to 1.5s–3.0s.",
        when_to_use="Throughout the escalation act to prevent viewer scroll-away.",
        implementation_guide="Switch between IDE, terminal, browser, and split-screen every 2.0 to 2.8 seconds on natural speech pauses.",
        parameters={"min_shot_duration_sec": 1.5, "max_shot_duration_sec": 3.2, "target_avg_duration_sec": 2.4},
        reference_examples=["Editor -> Terminal output -> Browser reload -> Stack Overflow."],
        limitations="Do not cut faster than 1.2s or the audience cannot read the code.",
    ),
    EditingTechnique(
        id="progressive_caption_punch",
        name="Progressive Kinetic Caption Punch",
        category="pacing",
        objective="Synchronize 1 to 3 words at a time with bold contrast so the viewer reads ahead effortlessly.",
        when_to_use="All spoken developer shorts for sound-off mobile accessibility.",
        implementation_guide="Render word-level subtitles in the center lower-third (y=1400) with a gold active word highlight.",
        parameters={"max_words_per_cue": 3, "font_size": 52, "safe_margin_bottom_px": 280},
        reference_examples=["[I PUSHED] -> [STRAIGHT TO] -> [PRODUCTION]"],
        limitations="Keep within the vertical mobile safe zone (above platform like/share overlays).",
    ),
    EditingTechnique(
        id="split_screen_comparison",
        name="Dual Split-Screen Contrast",
        category="visual_motion",
        objective="Show immediate direct comparison between two states.",
        when_to_use="'Localhost vs Production', 'Junior vs Senior', 'CSS in Tutorial vs Real Life'.",
        implementation_guide="Split 1080x1920 vertically into two 1080x920 cards with distinct top/bottom labels and borders.",
        parameters={"top_label": "LOCALHOST:3000 (GREEN)", "bottom_label": "PRODUCTION:443 (RED)"},
        reference_examples=["Top screen running smoothly; bottom screen throwing 504 Gateway Timeout."],
        limitations="Text on each half must remain large enough to read on small mobile screens.",
    ),
    EditingTechnique(
        id="sound_effect_sync",
        name="Tactile Foley SFX Synchronization",
        category="audio_design",
        objective="Reinforce physical presence of digital actions with authentic developer sound design.",
        when_to_use="Code typing, terminal execution, error alerts, mouse clicks.",
        implementation_guide="Align mechanical switch clicks to typing visuals, terminal chime to successful build, buzz to error.",
        parameters={"audio_duck_lead_ms": 30, "sfx_volume_db": -6.0},
        reference_examples=["Cherry MX blue keyboard clatter -> heavy enter key thud -> terminal bell."],
        limitations="Do not overpower narration; keep SFX 6dB to 12dB below vocal track.",
    ),
    EditingTechnique(
        id="seamless_loop_ending",
        name="Infinite Seamless Loop",
        category="payoff",
        objective="Encourage immediate rewatches by linking the final sentence seamlessly into the opening word.",
        when_to_use="Developer jokes and continuous cycle narratives (e.g. debugging loops).",
        implementation_guide="End the script mid-thought or with a premise lead-in that answers the opening question.",
        parameters={"fade_out_duration_sec": 0.0, "sentence_bridge": True},
        reference_examples=["Ending: 'And that is why the real bug was...' Opening: '...in line 42.'"],
        limitations="Requires strict vocal inflection alignment; the ending voice cannot drop into a full resolution pitch.",
    ),
    EditingTechnique(
        id="pattern_interrupt",
        name="Pattern Interrupt Flash",
        category="visual_motion",
        objective="Reset viewer attention at the 50% duration mark when retention naturally dips.",
        when_to_use="Between Act 2 (escalation) and Act 3 (payoff) at approximately 15s–25s.",
        implementation_guide="Insert a 300ms inverted color flash, terminal ASCII skull, or rapid sound whoosh.",
        parameters={"duration_ms": 300, "type": "color_invert_or_glitch"},
        reference_examples=["A sudden brief terminal glitch effect right before the senior dev speaks."],
        limitations="Use at most once per video to avoid visual fatigue.",
    ),
    EditingTechnique(
        id="silence_before_punchline",
        name="Dramatic Micro-Silence",
        category="audio_design",
        objective="Heighten anticipation immediately before a major joke reveal or fatal error.",
        when_to_use="Right before the final catastrophic terminal output or confession reveal.",
        implementation_guide="Ducking and background music drop to absolute 0dB for 300ms, followed by a loud error chime.",
        parameters={"silence_duration_ms": 300, "mute_bgm": True},
        reference_examples=["'I ran git push --force...' -> [silence] -> [ALERT]"],
        limitations="Must be tight; longer than 500ms feels like an audio dropout bug.",
    ),
]


class EditingStyleLibrary:
    """Persistent, searchable knowledge base of short-form video editing techniques."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.data_path = data_path or (Path(__file__).resolve().parent.parent.parent / "data" / "editing_style_library.json")
        self._techniques: Dict[str, EditingTechnique] = {}
        self._load()

    def _load(self) -> None:
        """Load techniques from persistent storage or initialize with curated catalog."""
        # Always populate base catalog
        for tech in CURATED_TECHNIQUES:
            self._techniques[tech.id] = tech

        if self.data_path.exists():
            try:
                data = json.loads(self.data_path.read_text(encoding="utf-8"))
                for item in data:
                    t = EditingTechnique(**item)
                    self._techniques[t.id] = t
            except Exception:
                pass

    def save(self) -> None:
        """Persist library to disk."""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [t.to_dict() for t in self._techniques.values()]
        self.data_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def get(self, technique_id: str) -> Optional[EditingTechnique]:
        """Fetch technique by unique ID."""
        return self._techniques.get(technique_id)

    def list_all(self) -> List[EditingTechnique]:
        """Return all available techniques."""
        return list(self._techniques.values())

    def search(self, query: str) -> List[EditingTechnique]:
        """Search techniques by keyword in name, objective, or implementation guide."""
        q = query.lower()
        results = []
        for t in self._techniques.values():
            if (
                q in t.name.lower()
                or q in t.objective.lower()
                or q in t.when_to_use.lower()
                or q in t.category.lower()
                or any(q in ex.lower() for ex in t.reference_examples)
            ):
                results.append(t)
        return results

    def get_by_category(self, category: str) -> List[EditingTechnique]:
        """Filter techniques by functional category."""
        return [t for t in self._techniques.values() if t.category == category]

    def add_technique(self, technique: EditingTechnique) -> None:
        """Add or update a technique in the persistent library."""
        self._techniques[technique.id] = technique
        self.save()


# Singleton instance
editing_style_library = EditingStyleLibrary()
