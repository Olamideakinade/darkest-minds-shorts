"""Reference video analyzer for studying high-performing short-form video techniques.

Performs frame sampling, scene boundary detection, shot duration analysis,
audio energy profiling, and hook categorization using local FFmpeg and PIL.
Distinguishes measured empirical facts from inferred creative choices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageStat

from app.config import config
from app.utils.logger import logger


@dataclass
class MeasuredVideoFacts:
    """Empirically measured technical facts extracted directly from video bitstream."""

    file_path: str
    duration_sec: float
    width: int
    height: int
    aspect_ratio: str
    fps: float
    total_shots: int
    avg_shot_duration_sec: float
    cut_frequency_cpm: float  # cuts per minute
    shot_timestamps_sec: List[float] = field(default_factory=list)
    has_audio: bool = True
    audio_mean_volume_db: Optional[float] = None
    audio_max_volume_db: Optional[float] = None
    silence_intervals_sec: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class InferredCreativeChoices:
    """Analytic and creative interpretations derived from observed patterns."""

    hook_category: str  # curiosity_gap, relatable_pain, unexpected_failure, contrarian_claim, visual_gag
    pacing_tier: str  # rapid (<2.5s/cut), moderate (2.5s-4.0s/cut), slow (>4.0s/cut)
    detected_techniques: List[str] = field(default_factory=list)
    narrative_structure: str = "3-Act (Hook -> Escalation -> Payoff)"
    confidence_score: float = 0.85
    limitations: List[str] = field(default_factory=list)


@dataclass
class ReferenceAnalysisResult:
    """Complete analysis combining empirical facts and creative deductions."""

    video_id: str
    creator_handle: Optional[str] = None
    platform: str = "youtube_shorts"  # youtube_shorts, instagram_reels, tiktok
    source_url: Optional[str] = None
    facts: MeasuredVideoFacts = field(default_factory=lambda: MeasuredVideoFacts("", 0.0, 0, 0, "9:16", 30.0, 0, 0.0, 0.0))
    creative: InferredCreativeChoices = field(default_factory=lambda: InferredCreativeChoices("curiosity_gap", "moderate"))
    analysis_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReferenceVideoAnalyzer:
    """Analyzes reference videos using deterministic local tools."""

    def __init__(self, ffmpeg_bin: Optional[str] = None, ffprobe_bin: Optional[str] = None) -> None:
        self.ffmpeg = ffmpeg_bin or config.ffmpeg_path
        self.ffprobe = ffprobe_bin or config.ffprobe_path

    def inspect_stream_metadata(self, video_path: Path) -> Dict[str, Any]:
        """Run ffprobe to retrieve exact stream dimensions, duration, and codecs."""
        cmd = [
            self.ffprobe,
            "-v", "error",
            "-show_entries", "format=duration:stream=width,height,r_frame_rate,codec_type",
            "-of", "json",
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)

    def analyze_audio_volume(self, video_path: Path) -> Tuple[Optional[float], Optional[float], List[Tuple[float, float]]]:
        """Compute mean/max volume and detect silence pauses using FFmpeg volumedetect and silencedetect."""
        mean_vol = None
        max_vol = None
        silences: List[Tuple[float, float]] = []

        try:
            cmd = [
                self.ffmpeg,
                "-i", str(video_path),
                "-af", "volumedetect,silencedetect=noise=-30dB:d=0.3",
                "-vn", "-sn",
                "-f", "null",
                "-",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            stderr = res.stderr

            for line in stderr.splitlines():
                if "mean_volume:" in line:
                    try:
                        mean_vol = float(line.split("mean_volume:")[1].split("dB")[0].strip())
                    except Exception:
                        pass
                elif "max_volume:" in line:
                    try:
                        max_vol = float(line.split("max_volume:")[1].split("dB")[0].strip())
                    except Exception:
                        pass
                elif "silence_start:" in line:
                    try:
                        start = float(line.split("silence_start:")[1].strip())
                        silences.append((start, start + 0.3))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Audio analysis note: {e}")

        return mean_vol, max_vol, silences

    def detect_scene_boundaries(
        self, video_path: Path, sample_fps: float = 2.0, threshold_diff: float = 25.0
    ) -> List[float]:
        """Sample frames at sample_fps and detect scene cuts based on pixel delta threshold."""
        timestamps: List[float] = [0.0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_pattern = os.path.join(tmp_dir, "frame_%04d.jpg")
            cmd = [
                self.ffmpeg,
                "-y",
                "-i", str(video_path),
                "-vf", f"fps={sample_fps},scale=360:640",
                "-q:v", "5",
                "-loglevel", "error",
                out_pattern,
            ]
            subprocess.run(cmd, check=True)

            frame_files = sorted(Path(tmp_dir).glob("frame_*.jpg"))
            prev_stat = None
            step_sec = 1.0 / sample_fps

            for idx, f_path in enumerate(frame_files):
                img = Image.open(f_path).convert("L")
                stat = ImageStat.Stat(img)
                mean_brightness = stat.mean[0]

                if prev_stat is not None:
                    diff = abs(mean_brightness - prev_stat)
                    if diff >= threshold_diff:
                        shot_time = round(idx * step_sec, 2)
                        if not timestamps or (shot_time - timestamps[-1]) >= 1.0:
                            timestamps.append(shot_time)

                prev_stat = mean_brightness

        return timestamps

    def classify_hook(self, opening_text: str) -> str:
        """Infer hook category from opening text or audio transcription."""
        text = opening_text.lower()
        if any(w in text for w in ("how", "why", "secret", "never", "nobody", "what if")):
            return "curiosity_gap"
        elif any(w in text for w in ("junior", "senior", "hate", "pain", "hours", "exhausted", "debugging")):
            return "relatable_pain"
        elif any(w in text for w in ("bug", "crash", "error", "failed", "deleted", "broke", "500")):
            return "unexpected_failure"
        elif any(w in text for w in ("stop", "wrong", "lie", "myth", "don't")):
            return "contrarian_claim"
        return "visual_gag"

    def analyze(
        self,
        video_path: Path,
        opening_text: str = "",
        creator_handle: Optional[str] = None,
        source_url: Optional[str] = None,
        platform: str = "youtube_shorts",
    ) -> ReferenceAnalysisResult:
        """Execute complete analysis on target video file."""
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Reference video not found: {video_path}")

        meta = self.inspect_stream_metadata(video_path)
        duration = float(meta.get("format", {}).get("duration", 0.0))

        v_stream = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
        width = int(v_stream.get("width", 1080))
        height = int(v_stream.get("height", 1920))
        aspect_ratio = "9:16" if height > width else ("16:9" if width > height else "1:1")

        # Parse FPS
        r_fps = v_stream.get("r_frame_rate", "30/1")
        if "/" in r_fps:
            num, den = r_fps.split("/")
            fps = float(num) / max(float(den), 1.0)
        else:
            fps = float(r_fps)

        # Detect cuts
        cuts = self.detect_scene_boundaries(video_path)
        total_shots = max(len(cuts), 1)
        avg_shot_dur = round(duration / total_shots, 2) if total_shots > 0 else duration
        cpm = round((total_shots / max(duration, 1.0)) * 60.0, 1)

        # Audio analysis
        has_audio = any(s.get("codec_type") == "audio" for s in meta.get("streams", []))
        mean_vol, max_vol, silences = self.analyze_audio_volume(video_path) if has_audio else (None, None, [])

        facts = MeasuredVideoFacts(
            file_path=str(video_path),
            duration_sec=round(duration, 2),
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            fps=round(fps, 2),
            total_shots=total_shots,
            avg_shot_duration_sec=avg_shot_dur,
            cut_frequency_cpm=cpm,
            shot_timestamps_sec=cuts,
            has_audio=has_audio,
            audio_mean_volume_db=mean_vol,
            audio_max_volume_db=max_vol,
            silence_intervals_sec=silences,
        )

        # Creative classification
        hook_cat = self.classify_hook(opening_text)
        pacing_tier = "rapid" if avg_shot_dur < 2.5 else ("moderate" if avg_shot_dur <= 4.0 else "slow")

        detected_techniques = []
        if avg_shot_dur <= 2.8:
            detected_techniques.append("fast_screen_cut")
        if silences:
            detected_techniques.append("silence_before_punchline")
        if hook_cat == "unexpected_failure":
            detected_techniques.append("cold_open_crisis")

        creative = InferredCreativeChoices(
            hook_category=hook_cat,
            pacing_tier=pacing_tier,
            detected_techniques=detected_techniques,
            confidence_score=0.88,
            limitations=["Organic audience retention and reach metrics not publicly accessible."],
        )

        from datetime import datetime, timezone
        return ReferenceAnalysisResult(
            video_id=video_path.stem,
            creator_handle=creator_handle,
            platform=platform,
            source_url=source_url,
            facts=facts,
            creative=creative,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )
