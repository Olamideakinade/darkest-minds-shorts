"""Free-first neural text-to-speech voiceover service with macOS local fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from app.config import config
from app.database.db import Database, db
from app.database.models import MediaAsset, utc_now_iso
from app.utils.logger import logger


@dataclass
class WordTimestamp:
    """Individual word timing for subtitle and scene synchronization."""
    word: str
    start_sec: float
    end_sec: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "start_sec": round(self.start_sec, 3),
            "end_sec": round(self.end_sec, 3),
        }


@dataclass
class NarrationResult:
    """Result of voiceover synthesis."""
    audio_path: Path
    duration_sec: float
    provider: str  # edge-tts or macos-say
    voice_used: str
    word_timestamps: List[WordTimestamp] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_path": str(self.audio_path),
            "duration_sec": round(self.duration_sec, 2),
            "provider": self.provider,
            "voice_used": self.voice_used,
            "word_count": len(self.word_timestamps),
            "metadata": self.metadata,
        }


class TTSService:
    """Natural English narration generator using free Edge-TTS with native macOS offline fallback."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self.db = database or db
        self.voice = config.tts_voice
        self.rate = config.tts_rate

    def synthesize(self, job_id: str, text: str, output_path: Optional[Path] = None) -> NarrationResult:
        """Synthesize script text into audio, measure exact duration, and compute word timings.

        Edge-TTS requires an active internet connection. If transient network issues occur,
        it automatically falls back to native macOS speech synthesis (`say`) to guarantee
        offline zero-failure execution.
        """
        if not text or not text.strip():
            raise ValueError("Cannot synthesize empty narration text.")

        if output_path is None:
            job_dir = config.output_dir / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            output_path = job_dir / "narration.mp3"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Synthesizing narration for job {job_id} ({len(text.split())} words)...")

        # 1. Attempt Edge-TTS with bounded retries
        success = False
        provider = "edge-tts"
        voice_used = self.voice

        for attempt in range(1, 3):
            try:
                self._synthesize_edge_tts(text, output_path)
                if output_path.exists() and output_path.stat().st_size > 1024:
                    success = True
                    break
            except Exception as e:
                logger.warning(f"Edge-TTS attempt {attempt} failed: {e}")
                time.sleep(0.5)

        # 2. Fall back to native macOS speech synthesis if Edge-TTS failed or offline
        if not success:
            logger.info("Falling back to native macOS speech synthesis ('say' command)...")
            try:
                self._synthesize_macos_say(text, output_path)
                provider = "macos-say"
                voice_used = "Samantha"
                success = True
            except Exception as e:
                logger.error(f"macOS say fallback failed: {e}")
                raise RuntimeError(f"All narration engines failed for job {job_id}: {e}")

        # 3. Measure exact duration using ffprobe
        duration_sec = self._measure_audio_duration(output_path)
        if duration_sec <= 0.0:
            raise RuntimeError(f"Synthesized audio {output_path} has invalid duration: {duration_sec}s")

        # 4. Generate synchronized word timings
        words = text.split()
        word_timestamps = self._calculate_proportional_word_timings(words, duration_sec)

        # 5. Persist MediaAsset in database
        if job_id and not self.db.get_job(job_id):
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO jobs (id, title, niche, state, current_stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (job_id, f"Job {job_id}", config.niche_default, "NARRATING", "narrating", utc_now_iso(), utc_now_iso()),
                )

        asset = MediaAsset(
            job_id=job_id,
            asset_type="audio",
            file_path=str(output_path),
            duration_sec=duration_sec,
            license_info=f"Original Audio Generated via {provider} ({voice_used})",
        )
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO media_assets (id, job_id, asset_type, file_path, duration_sec, license_info, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (asset.id, asset.job_id, asset.asset_type, asset.file_path, asset.duration_sec, asset.license_info, asset.created_at),
            )

        # 6. Save metadata JSON alongside audio file
        meta_path = output_path.with_suffix(".json")
        result = NarrationResult(
            audio_path=output_path,
            duration_sec=duration_sec,
            provider=provider,
            voice_used=voice_used,
            word_timestamps=word_timestamps,
            metadata={
                "word_count": len(words),
                "words_per_minute": round((len(words) / max(duration_sec, 1)) * 60.0, 1),
                "output_size_bytes": output_path.stat().st_size,
                "created_at": utc_now_iso(),
            },
        )
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(
            f"Narration generated successfully: {output_path.name} ({duration_sec:.1f}s, "
            f"{result.metadata['words_per_minute']} WPM, provider: {provider})"
        )
        return result

    def _synthesize_edge_tts(self, text: str, output_path: Path) -> None:
        """Call edge-tts CLI or API asynchronously to produce MP3."""
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            await communicate.save(str(output_path))

        asyncio.run(_run())

    def _synthesize_macos_say(self, text: str, output_path: Path) -> None:
        """Use native macOS /usr/bin/say to generate AIFF, then convert to MP3 via ffmpeg."""
        temp_aiff = output_path.with_suffix(".aiff")
        try:
            # Generate AIFF using Samantha voice
            cmd_say = ["/usr/bin/say", "-v", "Samantha", "-o", str(temp_aiff), text]
            subprocess.run(cmd_say, check=True, capture_output=True)

            # Convert AIFF to MP3 with ffmpeg
            cmd_convert = [
                "ffmpeg", "-y", "-i", str(temp_aiff),
                "-codec:a", "libmp3lame", "-b:a", "192k",
                str(output_path),
            ]
            subprocess.run(cmd_convert, check=True, capture_output=True)
        finally:
            if temp_aiff.exists():
                temp_aiff.unlink()

    def _measure_audio_duration(self, audio_path: Path) -> float:
        """Measure exact audio duration in seconds using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception as e:
            logger.warning(f"ffprobe duration measurement failed: {e}")
            return 0.0

    @staticmethod
    def _calculate_proportional_word_timings(words: List[str], total_duration: float) -> List[WordTimestamp]:
        """Distribute word timestamps proportionally based on character weight and speech cadence."""
        if not words:
            return []

        # Character weight allocation with pauses for punctuation
        weights = []
        for w in words:
            weight = float(len(w))
            if w.endswith((".", "!", "?")):
                weight += 4.0  # Punctuation pause weight
            elif w.endswith((",", ";", ":", "—")):
                weight += 2.0
            weights.append(max(weight, 1.0))

        total_weight = sum(weights)
        current_time = 0.1  # 100ms opening padding
        usable_duration = max(total_duration - 0.2, 0.5)

        timestamps: List[WordTimestamp] = []
        for w, weight in zip(words, weights):
            word_duration = (weight / total_weight) * usable_duration
            start = current_time
            end = current_time + word_duration
            timestamps.append(WordTimestamp(word=w, start_sec=start, end_sec=end))
            current_time = end

        return timestamps


# Global narration service singleton
tts_service = TTSService()
