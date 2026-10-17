"""Domain models for original 3-Act YouTube Shorts storytelling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from app.database.models import FactualClaim, utc_now_iso


@dataclass
class StoryScene:
    """Scene-by-scene visual direction and narration sync."""
    scene_number: int
    narration_chunk: str
    visual_prompt: str
    target_duration_sec: float = 4.0
    visual_mood: str = "cinematic_dramatic"  # moody, vintage, mysterious, archival
    badge_text: str = ""
    pexels_query: str = ""
    ai_image_prompt: str = ""
    visual_source: str = "ai_flux"  # "ai_flux" or "pexels_video"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoryScript:
    """Complete 3-Act original storytelling script."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    title: str = ""
    category: str = "strange_history"
    narrative_archetype: str = "escalating_revelation"
    hook_style: str = "curiosity_gap"

    # 3-Act Narrative Architecture
    hook_text: str = ""        # Act 1: 0–3 seconds (Instant curiosity, zero fluff)
    escalation_text: str = ""  # Act 2: 3–30 seconds (Rising stakes, concrete evidence)
    payoff_text: str = ""      # Act 3: 30–45 seconds (Twist, irony, or unresolved mystery)
    full_narration: str = ""

    word_count: int = 0
    estimated_duration_sec: float = 0.0

    # Multi-scene visual breakdown
    scenes: List[StoryScene] = field(default_factory=list)

    # Verification and Quality
    factual_claims: List[FactualClaim] = field(default_factory=list)
    factual_verification_status: str = "VERIFIED"  # VERIFIED, UNVERIFIED, SPECULATIVE
    factual_notes: str = ""
    originality_score: float = 100.0
    is_approved: bool = True

    # Viral Metadata & Algorithmic Comment Trap
    optimized_title: str = ""
    description_text: str = ""
    target_tags: List[str] = field(default_factory=list)
    pinned_comment: str = ""
    retention_score: int = 90
    critique_feedback: str = ""

    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scenes"] = [s.to_dict() if isinstance(s, StoryScene) else s for s in self.scenes]
        d["factual_claims"] = [c.to_dict() if isinstance(c, FactualClaim) else c for c in self.factual_claims]
        return d


@dataclass
class CanonicalProductionManifest:
    """Single source of truth production manifest linking script, speech, visuals, and timing."""
    job_id: str
    topic: str
    title: str
    target_duration_seconds: float
    verified_claims: List[Dict[str, Any]] = field(default_factory=list)
    exact_narration_segments: List[str] = field(default_factory=list)
    scene_ids: List[str] = field(default_factory=list)
    scene_narration_references: Dict[str, str] = field(default_factory=dict)
    word_boundary_timestamps: List[Dict[str, Any]] = field(default_factory=list)
    timing_mode: str = "acoustic"  # acoustic | provisional | estimated
    visual_purpose: List[str] = field(default_factory=list)
    image_prompts: List[str] = field(default_factory=list)
    negative_prompts: List[str] = field(default_factory=list)
    camera_movements: List[str] = field(default_factory=list)
    overlays: List[str] = field(default_factory=list)
    sound_cues: List[str] = field(default_factory=list)
    transition_types: List[str] = field(default_factory=list)
    source_references: List[str] = field(default_factory=list)
    verification_status: str = "VERIFIED"
    scenes: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

