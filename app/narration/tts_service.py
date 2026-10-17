"""Free-first neural text-to-speech voiceover service with macOS local fallback."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
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
    is_estimated: bool = False
    offset_ticks: Optional[int] = None
    duration_ticks: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "word": self.word,
            "start_sec": round(self.start_sec, 3),
            "end_sec": round(self.end_sec, 3),
            "is_estimated": self.is_estimated,
        }
        if self.offset_ticks is not None:
            d["offset_ticks"] = self.offset_ticks
        if self.duration_ticks is not None:
            d["duration_ticks"] = self.duration_ticks
        return d


@dataclass
class NarrationResult:
    """Result of voiceover synthesis."""
    audio_path: Path
    duration_sec: float
    provider: str  # edge-tts or macos-say
    voice_used: str
    word_timestamps: List[WordTimestamp] = field(default_factory=list)
    timing_mode: str = "acoustic"  # acoustic | estimated
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_path": str(self.audio_path),
            "duration_sec": round(self.duration_sec, 2),
            "provider": self.provider,
            "voice_used": self.voice_used,
            "word_count": len(self.word_timestamps),
            "timing_mode": self.timing_mode,
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

        Edge-TTS captures true WordBoundary events from the synthesis stream.
        If offline or fallback occurs, timings are marked as estimated.
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

        success = False
        provider = "gemini-tts" if config.tts_provider == "gemini" else "edge-tts"
        voice_used = self.voice
        word_timestamps: List[WordTimestamp] = []
        timing_mode = "estimated"

        # 1. Attempt ElevenLabs if API key configured (world-class human documentary voice)
        if getattr(config, "elevenlabs_api_key", ""):
            try:
                voice_id = getattr(config, "elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")
                logger.info(f"Attempting ElevenLabs Cinema-Grade Voiceover (Voice ID: {voice_id})...")
                el_success, el_timestamps = self._synthesize_elevenlabs(text, output_path, voice_id=voice_id)
                if el_success and output_path.exists() and output_path.stat().st_size > 1024:
                    success = True
                    provider = "elevenlabs"
                    voice_used = f"elevenlabs-{voice_id[:6]}"
                    if el_timestamps:
                        word_timestamps = el_timestamps
                        timing_mode = "acoustic"
                    else:
                        timing_mode = "estimated"
            except Exception as e:
                logger.warning(f"ElevenLabs synthesis failed ({e}). Falling back to next engine...")

        # 2. Attempt Google Gemini TTS if explicitly selected as tts_provider
        if not success and config.tts_provider == "gemini":
            try:
                gemini_voice = self.voice if self.voice in ("Fenrir", "Charon", "Aoede", "Puck") else "Fenrir"
                logger.info(f"Attempting Google Gemini Neural Voiceover ({gemini_voice})...")
                if self._synthesize_gemini_tts(text, output_path, voice=gemini_voice):
                    success = True
                    provider = "gemini-tts"
                    voice_used = gemini_voice
                    timing_mode = "estimated"
            except Exception as e:
                logger.warning(f"Gemini TTS synthesis attempt failed ({e}). Falling back to Edge-TTS...")

        # 3. Attempt Edge-TTS with dramatic documentary tuning (GuyNeural / RyanNeural at -12Hz pitch)
        if not success:
            candidate_voices = [self.voice if "Neural" in self.voice else "en-US-ChristopherNeural"]
            for alt_v in ("en-US-ChristopherNeural", "en-US-GuyNeural", "en-GB-RyanNeural", "en-US-BrianNeural"):
                if alt_v not in candidate_voices:
                    candidate_voices.append(alt_v)

            for v_candidate in candidate_voices:
                for attempt in range(1, 4):
                    try:
                        boundaries = self._synthesize_edge_tts(text, output_path, voice=v_candidate)
                        if output_path.exists() and output_path.stat().st_size > 1024:
                            success = True
                            provider = "edge-tts"
                            voice_used = v_candidate
                            if boundaries:
                                word_timestamps = boundaries
                                timing_mode = "acoustic"
                            else:
                                timing_mode = "estimated"
                            break
                    except Exception as e:
                        logger.warning(f"Edge-TTS attempt {attempt} with voice {v_candidate} failed: {e}")
                        time.sleep(0.4 * attempt)
                if success:
                    break

        # 4. Fall back to native macOS speech synthesis if Edge-TTS failed or offline (test only)
        if not success:
            if getattr(config, "app_env", "") != "test":
                raise RuntimeError(f"All neural voiceover engines (ElevenLabs, Gemini TTS, Edge-TTS) failed for job {job_id}. Robotic voice fallback blocked to preserve quality.")
            logger.info("Falling back to native macOS speech synthesis with broadcast mastering...")
            try:
                selected_voice = self._synthesize_macos_say(text, output_path)
                provider = "macos-say"
                voice_used = selected_voice
                timing_mode = "estimated"
                success = True
            except Exception as e:
                logger.error(f"macOS say fallback failed: {e}")
                raise RuntimeError(f"All narration engines failed for job {job_id}: {e}")

        # 3. Measure exact duration using ffprobe
        duration_sec = self._measure_audio_duration(output_path)
        if duration_sec <= 0.0:
            raise RuntimeError(f"Synthesized audio {output_path} has invalid duration: {duration_sec}s")

        # 4. Generate synchronized word timings if not acquired acoustically
        words = text.split()
        if not word_timestamps or timing_mode == "estimated":
            word_timestamps = self._calculate_proportional_word_timings(words, duration_sec)
            timing_mode = "estimated"

        # 5. Persist MediaAsset in database if job exists
        if job_id and self.db.get_job(job_id):
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

        # 6. Save word timestamps in stable machine-readable JSON alongside audio
        timestamps_path = output_path.parent / "word_timestamps.json"
        with open(timestamps_path, "w", encoding="utf-8") as f:
            json.dump({
                "job_id": job_id,
                "timing_mode": timing_mode,
                "word_count": len(word_timestamps),
                "words": [wt.to_dict() for wt in word_timestamps],
            }, f, indent=2)

        # 7. Save narration metadata JSON
        meta_path = output_path.with_suffix(".json")
        result = NarrationResult(
            audio_path=output_path,
            duration_sec=duration_sec,
            provider=provider,
            voice_used=voice_used,
            word_timestamps=word_timestamps,
            timing_mode=timing_mode,
            metadata={
                "word_count": len(words),
                "words_per_minute": round((len(words) / max(duration_sec, 1)) * 60.0, 1),
                "output_size_bytes": output_path.stat().st_size,
                "timing_mode": timing_mode,
                "created_at": utc_now_iso(),
            },
        )
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(
            f"Narration generated successfully: {output_path.name} ({duration_sec:.1f}s, "
            f"{result.metadata['words_per_minute']} WPM, provider: {provider}, timing: {timing_mode})"
        )
        return result

    def _synthesize_edge_tts(self, text: str, output_path: Path, voice: Optional[str] = None) -> List[WordTimestamp]:
        """Stream Edge-TTS with WordBoundary events, pitch-shifted baritone timbre, and real acoustic timestamps."""
        import edge_tts

        active_voice = voice or self.voice
        rate = getattr(config, "tts_rate", "+8%")
        pitch = getattr(config, "tts_pitch", "-6Hz")

        async def _run() -> List[WordTimestamp]:
            communicate = edge_tts.Communicate(text, active_voice, rate=rate, pitch=pitch, boundary="WordBoundary")
            boundaries: List[WordTimestamp] = []
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        # Convert 100ns units (ticks) to seconds: 1 tick = 1e-7 seconds
                        offset_ticks = chunk.get("offset", 0)
                        duration_ticks = chunk.get("duration", 0)
                        start_sec = offset_ticks / 10_000_000.0
                        duration_sec = duration_ticks / 10_000_000.0
                        end_sec = start_sec + duration_sec
                        boundaries.append(
                            WordTimestamp(
                                word=chunk.get("text", ""),
                                start_sec=round(start_sec, 3),
                                end_sec=round(end_sec, 3),
                                is_estimated=False,
                                offset_ticks=offset_ticks,
                                duration_ticks=duration_ticks,
                            )
                        )
            return boundaries

        return asyncio.run(_run())

    def _synthesize_elevenlabs(
        self,
        text: str,
        output_path: Path,
        voice_id: Optional[str] = None
    ) -> Tuple[bool, List[WordTimestamp]]:
        """Synthesize cinema-grade human voiceover using ElevenLabs API with acoustic timestamps."""
        api_key = getattr(config, "elevenlabs_api_key", "")
        if not api_key:
            return False, []

        import base64
        import urllib.request
        import urllib.error

        voice = voice_id or getattr(config, "elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")
        model = getattr(config, "elevenlabs_model_id", "eleven_turbo_v2_5") or "eleven_turbo_v2_5"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"

        payload = {
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.85,
                "style": 0.35,
                "use_speaker_boost": True
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "xi-api-key": api_key,
                "Accept": "application/json"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                if resp.status != 200:
                    return False, []
                data = json.loads(resp.read().decode("utf-8"))
                audio_b64 = data.get("audio_base64", "")
                if not audio_b64:
                    return False, []

                audio_bytes = base64.b64decode(audio_b64)
                with open(output_path, "wb") as f_out:
                    f_out.write(audio_bytes)

                alignment = data.get("alignment", {})
                chars = alignment.get("characters", [])
                starts = alignment.get("character_start_times_seconds", [])
                ends = alignment.get("character_end_times_seconds", [])

                words: List[WordTimestamp] = []
                current_chars = []
                word_start = None
                last_end = 0.0

                for char, start_t, end_t in zip(chars, starts, ends):
                    if char.isspace():
                        if current_chars and word_start is not None:
                            word_str = "".join(current_chars).strip()
                            if word_str:
                                words.append(WordTimestamp(
                                    word=word_str,
                                    start_sec=round(word_start, 3),
                                    end_sec=round(last_end, 3),
                                    is_estimated=False
                                ))
                            current_chars = []
                            word_start = None
                    else:
                        if word_start is None:
                            word_start = start_t
                        current_chars.append(char)
                        last_end = end_t

                if current_chars and word_start is not None:
                    word_str = "".join(current_chars).strip()
                    if word_str:
                        words.append(WordTimestamp(
                            word=word_str,
                            start_sec=round(word_start, 3),
                            end_sec=round(last_end, 3),
                            is_estimated=False
                        ))

                return True, words
        except Exception as e:
            logger.warning(f"ElevenLabs synthesis failed: {e}")
            return False, []

    def _synthesize_gemini_tts(self, text: str, output_path: Path, voice: str = "Fenrir") -> bool:
        """Synthesize expressive, broadcast-grade human voiceover using Google Gemini Neural TTS."""
        api_key = getattr(config, "gemini_api_key", "")
        if not api_key:
            return False

        import base64
        import urllib.request

        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice
                        }
                    }
                }
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST"
        )

        import urllib.error
        raw_pcm = b""
        for attempt in range(1, 5):
            try:
                with urllib.request.urlopen(req, timeout=40) as resp:
                    if resp.status != 200:
                        return False
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return False
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        return False
                    b64_audio = parts[0].get("inlineData", {}).get("data", "")
                    if not b64_audio:
                        return False
                    raw_pcm = base64.b64decode(b64_audio)
                    break
            except urllib.error.HTTPError as he:
                if he.code == 429 and attempt < 4:
                    backoff = 3.0 * attempt
                    logger.info(f"Gemini TTS rate limited (429). Retrying in {backoff:.1f}s (attempt {attempt}/4)...")
                    time.sleep(backoff)
                    continue
                raise
        if not raw_pcm:
            return False

        # Master audio via FFmpeg: convert 24kHz raw PCM to broadcast 192k MP3 with loudness normalization
        cmd = [
            config.ffmpeg_path,
            "-y",
            "-f", "s16le",
            "-ar", "24000",
            "-ac", "1",
            "-i", "-",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_path),
        ]
        res = subprocess.run(cmd, input=raw_pcm, capture_output=True, check=True)
        return output_path.exists() and output_path.stat().st_size > 1024

    def _synthesize_macos_say(self, text: str, output_path: Path) -> str:
        """Use native macOS speech synthesis with selected voice and broadcast audio mastering."""
        temp_aiff = output_path.with_suffix(".temp.aiff")
        selected_voice = "Daniel"
        try:
            # Check for preferred storytelling voices
            check_res = subprocess.run(["/usr/bin/say", "-v", "?"], capture_output=True, text=True)
            avail = check_res.stdout
            if "Daniel" in avail:
                selected_voice = "Daniel"
            elif "Oliver" in avail:
                selected_voice = "Oliver"
            elif "Evan" in avail:
                selected_voice = "Evan"
            elif "Alex" in avail:
                selected_voice = "Alex"
            else:
                selected_voice = "Samantha"

            # Generate high-sample AIFF at natural documentary speech rate (~165 WPM)
            cmd_say = ["/usr/bin/say", "-v", selected_voice, "-r", "165", "-o", str(temp_aiff), text]
            subprocess.run(cmd_say, check=True, capture_output=True)

            # Master audio with EQ, presence compression, and loudness normalization
            af_filter = (
                "highpass=f=75,"
                "equalizer=f=2800:width_type=o:width=1.5:g=3.0,"
                "equalizer=f=250:width_type=o:width=1.0:g=1.5,"
                "acompressor=threshold=-18dB:ratio=3:attack=5:release=50:makeup=2,"
                "loudnorm=I=-16:TP=-1.5:LRA=11"
            )
            cmd_convert = [
                "ffmpeg", "-y", "-i", str(temp_aiff),
                "-af", af_filter,
                "-codec:a", "libmp3lame", "-b:a", "192k",
                str(output_path),
            ]
            subprocess.run(cmd_convert, check=True, capture_output=True)
            return selected_voice
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
        """Distribute word timestamps proportionally based on character weight when acoustic timings are unavailable."""
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
            timestamps.append(WordTimestamp(word=w, start_sec=start, end_sec=end, is_estimated=True))
            current_time = end

        return timestamps


# Global narration service singleton
tts_service = TTSService()
