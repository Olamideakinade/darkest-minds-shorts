"""Professional audio mixer with narration prioritization, ducking, and sound design."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import List, Optional

from app.config import config
from app.editing.timeline import ScenePlan
from app.utils.logger import logger


class AudioMixer:
    """Mixes narration, optional licensed atmospheric music, and subtle sound effects with ducking."""

    def __init__(self, audio_dir: Optional[Path] = None) -> None:
        self.audio_dir = audio_dir or (config.data_dir / "audio")
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        (self.audio_dir / "sfx").mkdir(parents=True, exist_ok=True)

    def mix_soundtrack(
        self,
        job_id: str,
        narration_path: Path,
        total_duration: float,
        timeline: Optional[List[ScenePlan]] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Mix narration with optional local music and sound effects, ducking music beneath voiceover."""
        if not output_path:
            output_path = config.output_dir / "jobs" / job_id / "audio_mixed.aac"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not narration_path.exists():
            raise FileNotFoundError(f"Narration file not found: {narration_path}")

        # Check for optional local background music
        music_candidates = [
            self.audio_dir / "background.mp3",
            self.audio_dir / "background.wav",
            self.audio_dir / "atmosphere.mp3",
        ]
        music_file = next((f for f in music_candidates if f.exists() and f.stat().st_size > 0), None)

        if not music_file:
            logger.info("No local background music file found in data/audio/. Using clean normalized narration track.")
            return narration_path

        # Ducking parameters: Background music faded out at conclusion
        fade_out_start = max(0.0, total_duration - 2.5)
        logger.info(f"Mixing local licensed soundtrack '{music_file.name}' with narration (ducking: -18dB)...")

        # Multi-stem Audio Mix: Narration (primary) + Ducked Background Music (-18dB) + Synced SFX Cues
        sfx_dir = self.audio_dir / "sfx"
        sfx_inputs: List[str] = []
        sfx_filters: List[str] = []
        next_input_idx = 2

        if timeline and sfx_dir.exists():
            for plan in timeline:
                cue = (plan.sound_cue or "").lower()
                sfx_file = None
                sfx_delay_ms = int(plan.start_sec * 1000)
                vol = 0.50

                if plan.visual_purpose == "hook" or "sub" in cue or "hit" in cue or "tension" in cue:
                    candidate = sfx_dir / "cinematic_sub_impact.wav"
                    if candidate.exists():
                        sfx_file = candidate
                        vol = 0.55
                elif "reticle" in cue or "focus" in cue or "click" in cue or plan.visual_purpose == "discovery":
                    candidate = sfx_dir / "focus_reticle_click.wav"
                    if candidate.exists():
                        sfx_file = candidate
                        sfx_delay_ms = int((plan.start_sec + 0.8) * 1000)
                        vol = 0.45
                elif "stamp" in cue or "dossier" in cue or plan.visual_purpose in ("suspect_intro", "infiltration"):
                    candidate = sfx_dir / "document_stamp.wav"
                    if candidate.exists():
                        sfx_file = candidate
                        sfx_delay_ms = int((plan.start_sec + 0.4) * 1000)
                        vol = 0.50

                if sfx_file and sfx_delay_ms < int(total_duration * 1000):
                    sfx_inputs.extend(["-i", str(sfx_file)])
                    sfx_filters.append(
                        f"[{next_input_idx}:a]adelay={sfx_delay_ms}|{sfx_delay_ms},volume={vol}[sfx_{next_input_idx}]"
                    )
                    next_input_idx += 1

        filter_chain = f"[1:a]volume=0.12,afade=t=out:st={fade_out_start:.2f}:d=2.5[bg];"
        if sfx_filters:
            filter_chain += ";".join(sfx_filters) + ";"
            sfx_refs = "".join(f"[sfx_{i}]" for i in range(2, next_input_idx))
            filter_chain += f"[0:a][bg]{sfx_refs}amix=inputs={next_input_idx}:duration=first:dropout_transition=2[outa]"
        else:
            filter_chain += "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[outa]"

        cmd = [
            config.ffmpeg_path,
            "-y",
            "-i", str(narration_path),
            "-stream_loop", "-1",
            "-i", str(music_file),
            *sfx_inputs,
            "-filter_complex", filter_chain,
            "-map", "[outa]",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            logger.info(f"Soundtrack mixed successfully with {len(sfx_filters)} SFX stem(s) -> {output_path.name}")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.warning(f"Audio mixing failed ({e.stderr}). Falling back to pristine narration track.")
            return narration_path
