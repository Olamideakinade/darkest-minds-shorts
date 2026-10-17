"""Timeline and scene-specific editing engine for dynamic YouTube Shorts storytelling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from app.editing.captions import WordTimestamp
from app.scripts.story_models import CanonicalProductionManifest, StoryScript
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
    kinetic_text: str        # Punchy keyword/date overlay derived strictly from narration
    sound_cue: Optional[str] = None # tension_hit, dossier_stamp, whoosh, sub_bass_drop
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
    """Builds a dynamic, multi-scene editing timeline strictly derived from the approved script."""

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

    def __init__(self) -> None:
        self.last_manifest: Optional[CanonicalProductionManifest] = None

    def build_timeline(
        self,
        story: StoryScript,
        word_timestamps: List[WordTimestamp],
        total_duration: float,
        job_dir: Optional[Path] = None,
    ) -> List[ScenePlan]:
        """Build timeline scenes and canonical production manifest strictly from approved script."""
        # 1. Segment approved narration into rapid, purposeful 2.5s–4.5s scene beats
        raw_beats = self._segment_into_beats(story)
        if not raw_beats:
            raw_beats = [
                (story.hook_text, "hook", story.title, "archival_photo", self._extract_kinetic_text(story.hook_text, story.title)),
                (story.escalation_text, "tension", story.title, "archival_photo", self._extract_kinetic_text(story.escalation_text, story.title)),
                (story.payoff_text, "payoff", story.title, "archival_photo", self._extract_kinetic_text(story.payoff_text, story.title)),
            ]

        # Defensively sanitize beats: subdivide any clause exceeding 12 words
        sanitized_beats = []
        for text_clause, purpose, query, asset_type, kinetic_phrase in raw_beats:
            words = text_clause.split()
            if len(words) > 12:
                mid = len(words) // 2
                first_half = " ".join(words[:mid])
                second_half = " ".join(words[mid:])
                sanitized_beats.append((first_half, purpose, query, asset_type, self._extract_kinetic_text(first_half, story.title)))
                sanitized_beats.append((second_half, purpose, query, asset_type, self._extract_kinetic_text(second_half, story.title)))
            else:
                sanitized_beats.append((text_clause, purpose, query, asset_type, kinetic_phrase))
        raw_beats = sanitized_beats

        # Ensure documentary visual diversity (at least 3 distinct asset types across 6+ beats)
        if len(raw_beats) >= 6:
            existing_types = set(b[3] for b in raw_beats)
            if len(existing_types) < 3:
                diverse_beats = []
                for b_idx, (tc, purp, qry, at, kp) in enumerate(raw_beats):
                    if b_idx == 1 and at == "archival_photo":
                        diverse_beats.append((tc, purp, qry, "historical_map", kp))
                    elif b_idx == 3 and at == "archival_photo":
                        diverse_beats.append((tc, purp, qry, "police_dossier", kp))
                    elif b_idx == 4 and at == "archival_photo" and len(existing_types) < 2:
                        diverse_beats.append((tc, purp, qry, "newspaper_headline", kp))
                    else:
                        diverse_beats.append((tc, purp, qry, at, kp))
                raw_beats = diverse_beats

        # 2. Determine timing mode
        has_acoustic_timestamps = (
            bool(word_timestamps) and not any(getattr(wt, "is_estimated", False) for wt in word_timestamps)
        )
        timing_mode = "acoustic" if has_acoustic_timestamps else "provisional"

        # 3. Calculate timing per beat using word timestamps if available
        scenes: List[ScenePlan] = []
        total_words = len(word_timestamps)
        beat_word_counts = [max(1, len(b[0].split())) for b in raw_beats]
        sum_words = sum(beat_word_counts)

        cur_word_idx = 0
        cur_time = 0.0

        for idx, (text_clause, purpose, query, asset_type, kinetic_phrase) in enumerate(raw_beats, start=1):
            w_count = beat_word_counts[idx - 1]
            start_sec = cur_time

            if has_acoustic_timestamps and total_words > 0 and cur_word_idx < total_words:
                target_word_idx = min(total_words - 1, cur_word_idx + w_count - 1)
                if idx == len(raw_beats):
                    end_sec = total_duration
                elif target_word_idx < total_words - 1:
                    end_sec = max(start_sec + 0.1, word_timestamps[target_word_idx].end_sec)
                else:
                    clause_duration = (w_count / sum_words) * (total_duration - cur_time)
                    end_sec = min(total_duration, cur_time + max(0.5, clause_duration))
                cur_word_idx = target_word_idx + 1
            else:
                clause_duration = (w_count / sum_words) * total_duration
                end_sec = min(total_duration, cur_time + clause_duration)
                if idx == len(raw_beats):
                    end_sec = total_duration

            if end_sec <= start_sec:
                end_sec = min(total_duration, start_sec + 0.5)
            if idx == len(raw_beats):
                end_sec = total_duration

            cur_time = end_sec

            # Determine motion & transitions
            motion = self.PURPOSE_MOTION_MAP.get(purpose, "push_in")
            trans = "flash_cut" if idx == 1 else ("crossfade" if purpose in ("reveal", "payoff", "discovery") else "cut")
            
            # Sound cues: Atmospheric only, NEVER success_chime.wav
            if idx == 1:
                sfx = "tension_hit"
            elif asset_type == "police_dossier":
                sfx = "document_stamp"
            elif purpose in ("reveal", "payoff"):
                sfx = "sub_bass_drop"
            else:
                sfx = "transition_whoosh"

            plan = ScenePlan(
                scene_number=idx,
                start_sec=round(start_sec, 2),
                end_sec=round(end_sec, 2),
                duration_sec=round(max(0.1, end_sec - start_sec), 2),
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

        # 4. Construct CanonicalProductionManifest
        manifest = CanonicalProductionManifest(
            job_id=story.job_id or "job_unspecified",
            topic=story.title,
            title=story.title,
            target_duration_seconds=round(total_duration, 2),
            verified_claims=[c.to_dict() if hasattr(c, "to_dict") else c for c in story.factual_claims],
            exact_narration_segments=[p.narration_segment for p in scenes],
            scene_ids=[f"scene_{p.scene_number:02d}" for p in scenes],
            scene_narration_references={f"scene_{p.scene_number:02d}": p.narration_segment for p in scenes},
            word_boundary_timestamps=[wt.to_dict() for wt in word_timestamps],
            timing_mode=timing_mode,
            visual_purpose=[p.visual_purpose for p in scenes],
            image_prompts=[p.search_query for p in scenes],
            negative_prompts=["modern, radar, hud, futuristic, cyber, vector, glowing neon, watermark, distortion" for _ in scenes],
            camera_movements=[p.motion_type for p in scenes],
            overlays=[p.kinetic_text for p in scenes],
            sound_cues=[p.sound_cue or "none" for p in scenes],
            transition_types=[p.transition_type for p in scenes],
            source_references=list(set([getattr(c, "source_url", "") for c in story.factual_claims if getattr(c, "source_url", "")])),
            verification_status=story.factual_verification_status or "VERIFIED",
            scenes=[p.to_dict() for p in scenes],
        )
        self.last_manifest = manifest

        # 5. Persist manifest and timeline if job_dir provided
        if job_dir:
            manifest_file = job_dir / "canonical_manifest.json"
            timeline_file = job_dir / "timeline.json"
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(manifest.to_dict(), f, indent=2)
            with open(timeline_file, "w", encoding="utf-8") as f:
                json.dump([p.to_dict() for p in scenes], f, indent=2)

        logger.info(
            f"Timeline engineered: {len(scenes)} scenes spanning {total_duration:.1f}s "
            f"(mode: {timing_mode}, avg scene: {total_duration / max(1, len(scenes)):.1f}s)"
        )
        return scenes

    def _segment_into_beats(self, story: StoryScript) -> List[Tuple[str, str, str, str, str]]:
        """Deconstruct approved story into granular beats derived directly from the approved narration."""
        # Check if pre-structured story scenes exist
        if story.scenes and len(story.scenes) >= 3:
            beats: List[Tuple[str, str, str, str, str]] = []
            for idx, sc in enumerate(story.scenes):
                chunk = sc.narration_chunk.strip()
                if not chunk:
                    continue
                purpose = self._infer_purpose(idx, len(story.scenes))
                asset_type = self._infer_asset_type(purpose, chunk)
                query = getattr(sc, "pexels_query", "") or sc.visual_prompt or f"{story.title} {chunk[:32]}"
                kinetic = getattr(sc, "badge_text", "") or self._extract_kinetic_text(chunk, story.title)
                beats.append((chunk, purpose, query, asset_type, kinetic))
            if beats:
                return beats

        # Tokenize narration text by natural sentence / clause boundaries
        full_text = story.full_narration or f"{story.hook_text} {story.escalation_text} {story.payoff_text}".strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", full_text) if s.strip()]

        beats = []
        for idx, sentence in enumerate(sentences):
            words = sentence.split()
            # If sentence exceeds 11 words and has clause punctuation, split gracefully
            if len(words) > 11 and any(p in sentence for p in (",", ";", "—")):
                parts = [p.strip() for p in re.split(r"[,;—]\s*", sentence) if p.strip()]
                for p_idx, part in enumerate(parts):
                    purpose = self._infer_purpose(len(beats), max(4, len(sentences) * 2))
                    asset_type = self._infer_asset_type(purpose, part)
                    query = f"{story.title} {part[:32]}"
                    kinetic = self._extract_kinetic_text(part, story.title)
                    beats.append((part, purpose, query, asset_type, kinetic))
            else:
                purpose = self._infer_purpose(idx, len(sentences))
                asset_type = self._infer_asset_type(purpose, sentence)
                query = f"{story.title} {sentence[:32]}"
                kinetic = self._extract_kinetic_text(sentence, story.title)
                beats.append((sentence, purpose, query, asset_type, kinetic))

        return beats

    @staticmethod
    def _infer_purpose(index: int, total: int) -> str:
        """Infer dramatic purpose from position in the narrative arc."""
        if index == 0:
            return "hook"
        if index == 1:
            return "discovery"
        if index == total - 1:
            return "payoff"
        if index == total - 2:
            return "reveal"
        if index % 2 == 0:
            return "tension"
        return "environment"

    @staticmethod
    def _infer_asset_type(purpose: str, text: str) -> str:
        """Select appropriate documentary asset type from narrative content."""
        t_low = text.lower()
        if any(k in t_low for k in ("map", "island", "route", "latitude", "ocean", "sea", "perimeter", "location")):
            return "historical_map"
        if any(k in t_low for k in ("logbook", "record", "letter", "dossier", "telegram", "report", "file", "clock", "coat")):
            return "police_dossier"
        if any(k in t_low for k in ("headline", "newspaper", "front page", "times", "journal")):
            return "newspaper_headline"
        return "archival_photo"

    @staticmethod
    def _extract_kinetic_text(text: str, fallback_topic: str) -> str:
        """Extract a punchy keyword, countdown rank, date, or phrase directly from the narration beat."""
        # 0. Check for Countdown Rank: e.g. "Number 5", "#5", "At number 3", "And at number 1"
        rank_m = re.search(r"\b(?:At\s+|And\s+at\s+)?(?:number|rank|#)\s*([1-9])\b", text, re.IGNORECASE)
        if rank_m:
            rank_num = rank_m.group(1)
            after_rank = text[rank_m.end():].strip(" :,-—")
            subject_words = [w.strip(".,;:\"'!?") for w in after_rank.split() if len(w) > 2][:3]
            subject_str = " ".join(subject_words).upper()
            if subject_str:
                return f"#{rank_num} • {subject_str}"
            return f"RANK #{rank_num}"

        # 1. Look for date/year in beat: e.g. "December 1900", "In 1911", "August 1911"
        date_m = re.search(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)?\s*(?:1[89][0-9]{2}|20[0-2][0-9]))\b", text, re.IGNORECASE)
        if date_m and date_m.group(0).strip():
            matched_date = date_m.group(0).strip().upper()
            # If island or place is also in the beat, combine
            place_m = re.search(r"\b(Eilean Mòr|Flannan|Louvre|Paris|Scotland|Atlantic)\b", text, re.IGNORECASE)
            if place_m:
                return f"{matched_date}: {place_m.group(0).upper()}"
            return matched_date

        # 2. Look for prominent quoted text
        quote_m = re.search(r"['\"]([^'\"]{4,28})['\"]", text)
        if quote_m:
            return quote_m.group(1).upper()

        # 3. Look for strong historical mystery keywords present IN THIS BEAT
        for kw in (
            "untouched meal", "clocks stopped", "logbook recorded", "no bodies",
            "storm recorded", "empty pegs", "oilskin coat", "vanished", "investigation",
            "unsolved", "evidence", "the vanishing"
        ):
            if kw in text.lower():
                return kw.upper()

        # 4. Default: first 3-4 impactful words from the beat itself
        words = [w.strip(".,;:\"'!?") for w in text.split() if len(w) > 2][:3]
        if words:
            return " ".join(words).upper()
        return fallback_topic.upper()[:24]


# Global timeline engine singleton
timeline_engine = TimelineEngine()
