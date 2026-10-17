"""Cinematic audio mixer for multi-stem YouTube Shorts soundtracks with dynamic sidechain ducking."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

from app.config import config
from app.editing.timeline import ScenePlan
from app.utils.logger import logger


class AudioMixer:
    """Mixes narration, background music, and restrained cinematic SFX stems."""

    def __init__(self, audio_dir: Optional[Path] = None) -> None:
        self.audio_dir = audio_dir or (config.data_dir / "audio")
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        (self.audio_dir / "sfx").mkdir(parents=True, exist_ok=True)
        self.provenance_file = self.audio_dir / "provenance.json"

    def mix_soundtrack(
        self,
        job_id: Any = None,
        narration_path: Any = None,
        total_duration: Optional[float] = None,
        timeline: Optional[List[ScenePlan]] = None,
        output_path: Optional[Path] = None,
        bg_music_filename: Optional[str] = "background.mp3",
        include_music: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> Path:
        """Mix primary narration with ducked background music and restrained atmospheric SFX stems."""
        # Support positional calling where narration_path is first arg
        if isinstance(job_id, Path) or (
            isinstance(job_id, str)
            and (Path(job_id).exists() or "/" in job_id or job_id.endswith((".wav", ".mp3", ".aac", ".m4a")))
        ):
            actual_narr = Path(job_id)
            if isinstance(narration_path, (int, float)):
                dur = float(narration_path)
            elif total_duration is not None:
                dur = float(total_duration)
            else:
                dur = 25.0
            actual_job_id = kwargs.get("job_id") or "job"
        else:
            actual_job_id = str(job_id or kwargs.get("job_id") or "job")
            narr_candidate = narration_path or kwargs.get("narration_path")
            if narr_candidate is None:
                raise ValueError("narration_path is required")
            actual_narr = Path(narr_candidate)
            dur = float(total_duration if total_duration is not None else 25.0)

        total_duration = dur
        narration_path = actual_narr

        if not narration_path.exists():
            raise FileNotFoundError(f"Narration audio not found: {narration_path}")

        if output_path is None:
            output_path = narration_path.parent / "audio_mixed.aac"

        # Check background music
        music_file = None
        if include_music and bg_music_filename:
            candidate = self.audio_dir / bg_music_filename
            if candidate.exists() and candidate.stat().st_size > 1024:
                music_file = candidate

        # Collect Restrained Mystery Documentary SFX Cues
        sfx_dir = self.audio_dir / "sfx"
        sfx_inputs: List[str] = []
        sfx_filters: List[str] = []
        next_input_idx = 2 if music_file else 1

        if timeline and sfx_dir.exists():
            for plan in timeline:
                cue = (plan.sound_cue or "").lower()
                sfx_file = None
                sfx_delay_ms = int(plan.start_sec * 1000)
                vol = 0.35

                # NEVER insert success_chime.wav into mystery documentaries or payoffs
                if "chime" in cue or "success" in cue or "revert" in cue:
                    continue

                # Cinematic Mystery Cues (Deep sub drops, eerie impacts, and subtle whooshes only)
                if "whoosh" in cue or "transition" in cue:
                    candidate = sfx_dir / "transition_whoosh.wav"
                    if candidate.exists():
                        sfx_file = candidate
                        sfx_delay_ms = int(plan.start_sec * 1000)
                        vol = 0.20
                elif plan.visual_purpose in ("hook", "payoff", "reveal") or "sub" in cue or "impact" in cue or "tension" in cue:
                    candidate = sfx_dir / "cinematic_sub_impact.wav"
                    if not candidate.exists():
                        candidate = sfx_dir / "sub_bass_drop.wav"
                    if candidate.exists():
                        sfx_file = candidate
                        sfx_delay_ms = int(plan.start_sec * 1000)
                        vol = 0.35

                if sfx_file and sfx_delay_ms < int(total_duration * 1000):
                    sfx_inputs.extend(["-i", str(sfx_file)])
                    sfx_filters.append(
                        f"[{next_input_idx}:a]adelay={sfx_delay_ms}|{sfx_delay_ms},volume={vol}[sfx_{next_input_idx}]"
                    )
                    next_input_idx += 1

        # If neither music nor SFX exist, return pristine narration
        if not music_file and not sfx_filters:
            logger.info("No background music or SFX stems found. Using pristine narration track.")
            return narration_path

        inputs = ["-i", str(narration_path)]
        if music_file:
            inputs.extend(["-stream_loop", "-1", "-i", str(music_file)])
        inputs.extend(sfx_inputs)

        filter_parts: List[str] = []
        mix_inputs: List[str] = ["[0:a]"]

        # Music stem with sidechain compression / ducking under narration [0:a]
        if music_file:
            fade_out_start = max(0.0, total_duration - 2.5)
            # Use sidechain compression to dynamically duck music under narration
            filter_parts.append(
                f"[1:a]volume=0.14,afade=t=out:st={fade_out_start:.2f}:d=2.5[bg_raw];"
                f"[bg_raw][0:a]sidechaincompress=threshold=0.09:ratio=4:attack=50:release=350[bg]"
            )
            mix_inputs.append("[bg]")

        if sfx_filters:
            filter_parts.extend(sfx_filters)
            start_idx = 2 if music_file else 1
            for i in range(start_idx, next_input_idx):
                mix_inputs.append(f"[sfx_{i}]")

        # Mix all stems without dividing primary voice volume (normalize=0) and master to -14 LUFS
        filter_parts.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=2:normalize=0[mixed];"
            f"[mixed]alimiter=limit=0.95:attack=5:release=50,loudnorm=I=-14:TP=-1.0:LRA=9[outa]"
        )
        filter_chain = ";".join(filter_parts)

        cmd = [
            config.ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", filter_chain,
            "-map", "[outa]",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            # Validate output duration
            out_dur = self._get_audio_duration(output_path)
            if abs(out_dur - total_duration) > 1.5:
                logger.warning(f"Audio duration mismatch: rendered {out_dur:.1f}s vs target {total_duration:.1f}s")

            logger.info(
                f"Soundtrack mixed successfully with {len(sfx_filters)} SFX stem(s) "
                f"(music={'yes' if music_file else 'no'}, sidechain=active) -> {output_path.name}"
            )
            return output_path
        except subprocess.CalledProcessError as e:
            logger.warning(f"Audio mixing filter failed ({e.stderr[:200]}). Falling back to simple volume ducking mix.")
            return self._mix_fallback(narration_path, music_file, total_duration, output_path)

    def _mix_fallback(self, narration_path: Path, music_file: Optional[Path], total_duration: float, output_path: Path) -> Path:
        """Robust fallback mix without sidechain if complex filter fails."""
        if not music_file:
            return narration_path

        fade_out_start = max(0.0, total_duration - 2.5)
        filter_chain = (
            f"[1:a]volume=0.09,afade=t=out:st={fade_out_start:.2f}:d=2.5[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,alimiter=limit=0.95,loudnorm=I=-14:TP=-1.0:LRA=9[outa]"
        )
        cmd = [
            config.ffmpeg_path, "-y",
            "-i", str(narration_path),
            "-stream_loop", "-1", "-i", str(music_file),
            "-filter_complex", filter_chain,
            "-map", "[outa]",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_path
        except Exception:
            return narration_path

    @staticmethod
    def _get_audio_duration(audio_path: Path) -> float:
        """Measure audio duration via ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 0.0

    # Alias for backward compatibility
    mix_documentary_audio = mix_soundtrack


audio_mixer = AudioMixer()
