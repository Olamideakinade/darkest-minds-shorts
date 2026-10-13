"""Professional vertical video renderer featuring camera pan/zoom motion, overlays, and hardware acceleration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from app.config import config
from app.editing.captions import CaptionCue
from app.editing.timeline import ScenePlan
from app.utils.logger import logger
from app.visuals.scene_synthesizer import scene_synthesizer
from app.visuals.service import ProducedSceneAsset


@dataclass
class VideoMetadata:
    """Technical metadata verified via FFprobe."""
    duration_sec: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    file_size_bytes: int
    has_video_stream: bool
    has_audio_stream: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration_sec": round(self.duration_sec, 2),
            "resolution": f"{self.width}x{self.height}",
            "fps": round(self.fps, 1),
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "file_size_bytes": self.file_size_bytes,
            "has_video_stream": self.has_video_stream,
            "has_audio_stream": self.has_audio_stream,
        }


class VideoRenderer:
    """Renders 1080x1920 YouTube Shorts using hardware acceleration, motion graphics, and audio mixing."""

    WIDTH = 1080
    HEIGHT = 1920
    FPS = 30

    def __init__(self) -> None:
        self.encoder = self._detect_hardware_encoder()

    def _detect_hardware_encoder(self) -> str:
        """Detect Apple VideoToolbox hardware acceleration or fallback to libx264."""
        try:
            res = subprocess.run([config.ffmpeg_path, "-encoders"], capture_output=True, text=True)
            if "h264_videotoolbox" in res.stdout:
                logger.debug("Apple VideoToolbox hardware encoding detected (h264_videotoolbox active).")
                return "h264_videotoolbox"
        except Exception:
            pass
        return "libx264"

    # -------------------------------------------------------------------------
    # Timeline-Driven Dynamic Motion Rendering
    # -------------------------------------------------------------------------

    def render_timeline(
        self,
        job_id: str,
        audio_path: Path,
        timeline: List[ScenePlan],
        caption_cues: List[CaptionCue],
        output_mp4: Path,
    ) -> VideoMetadata:
        """Render complete timeline with broadcast documentary motion graphics and audio design."""
        from app.editing.motion_graphics import motion_graphics_engine

        try:
            return motion_graphics_engine.render_timeline_documentary(
                job_id=job_id,
                audio_path=audio_path,
                timeline=timeline,
                output_mp4=output_mp4,
                caption_cues=caption_cues,
            )
        except Exception as e:
            logger.warning(f"MotionGraphicsEngine rendering failed ({e}). Falling back to FFmpeg timeline renderer.")
            return self._render_timeline_ffmpeg_fallback(
                job_id=job_id,
                audio_path=audio_path,
                timeline=timeline,
                caption_cues=caption_cues,
                output_mp4=output_mp4,
            )

    def _render_timeline_ffmpeg_fallback(
        self,
        job_id: str,
        audio_path: Path,
        timeline: List[ScenePlan],
        caption_cues: List[CaptionCue],
        output_mp4: Path,
    ) -> VideoMetadata:
        """Fallback: Render complete timeline with scene-specific camera motion (pan/zoom), captions, and audio mixing."""
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_mp4.parent / "render_tmp"
        work_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Rendering timeline Short via FFmpeg fallback ({len(timeline)} dynamic motion scenes) -> {output_mp4.name}...")
        start_time = time.time()

        total_audio_duration = self._get_media_duration(audio_path)
        if total_audio_duration <= 0.0:
            raise RuntimeError(f"Audio file {audio_path} has invalid duration: {total_audio_duration}")

        # 1. Render individual dynamic motion clips for each scene beat
        clip_paths: List[Path] = []
        for idx, plan in enumerate(timeline, start=1):
            clip_path = work_dir / f"clip_{idx:02d}.mp4"
            img_path = plan.rendered_image_path
            if not img_path or not img_path.exists():
                raise FileNotFoundError(f"Missing rendered image for scene #{idx}: {img_path}")

            self._render_scene_motion_clip(
                image_path=img_path,
                duration_sec=plan.duration_sec,
                motion_type=plan.motion_type,
                output_clip=clip_path,
            )
            clip_paths.append(clip_path)
            plan.rendered_clip_path = clip_path

        # 2. Build concat list for motion clips
        concat_file = work_dir / "motion_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                escaped = str(cp.resolve()).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # 3. Build FFmpeg command with concatenated motion clips and caption overlays
        concat_video_raw = work_dir / "scenes_combined.mp4"
        concat_cmd = [
            config.ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy",
            str(concat_video_raw),
        ]
        subprocess.run(concat_cmd, capture_output=True, text=True, check=True)

        # 4. Final compositing: Overlay captions onto motion video + attach audio
        cmd = [
            config.ffmpeg_path, "-y",
            "-i", str(concat_video_raw),
            "-i", str(audio_path),
        ]

        filter_parts: List[str] = []
        last_v = "0:v"

        # Multi-card caption overlays
        for c_idx, cue in enumerate(caption_cues):
            cmd.extend(["-i", str(cue.overlay_path.resolve())])
            input_idx = 2 + c_idx
            out_v = f"v_cap_{c_idx}"
            between_expr = f"between(t,{cue.start_sec:.3f},{cue.end_sec:.3f})"
            filter_parts.append(
                f"[{last_v}][{input_idx}:v]overlay=x=0:y=0:enable='{between_expr}'[{out_v}]"
            )
            last_v = out_v

        if filter_parts:
            cmd.extend([
                "-filter_complex", ";".join(filter_parts),
                "-map", f"[{last_v}]",
            ])
        else:
            cmd.extend([
                "-map", "0:v",
            ])

        cmd.extend([
            "-map", "1:a",
            "-t", f"{total_audio_duration:.3f}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", str(self.FPS),
            str(output_mp4),
        ])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg compositing failed: {e.stderr}")
            raise RuntimeError(f"FFmpeg render error: {e.stderr[-500:] if e.stderr else 'unknown'}")

        render_sec = time.time() - start_time
        logger.info(f"Timeline video render completed in {render_sec:.1f}s. Validating...")

        # 5. FFprobe technical validation
        metadata = self.inspect_video(output_mp4)
        if not metadata.has_video_stream or not metadata.has_audio_stream:
            raise RuntimeError(f"Rendered video {output_mp4} is missing video or audio stream.")
        if metadata.width != self.WIDTH or metadata.height != self.HEIGHT:
            raise RuntimeError(f"Resolution mismatch: expected {self.WIDTH}x{self.HEIGHT}, got {metadata.width}x{metadata.height}")

        # 6. Extract representative preview frames from actual rendered video across all scenes
        preview_dir = output_mp4.parent / "previews"
        scene_timestamps = [round((p.start_sec + p.end_sec) / 2.0, 2) for p in timeline]
        preview_frames = self.extract_preview_frames(output_mp4, output_dir=preview_dir, timestamps=scene_timestamps)
        try:
            contact_sheet_path = output_mp4.parent / "contact_sheet.jpg"
            frames_for_sheet = preview_frames if preview_frames else [p.rendered_image_path for p in timeline if p.rendered_image_path]
            scene_synthesizer.create_contact_sheet(frames_for_sheet[:9], contact_sheet_path)
        except Exception as e:
            logger.warning(f"Could not generate contact sheet: {e}")

        logger.info(
            f"Video successfully validated: {output_mp4.name} ({metadata.duration_sec:.1f}s, "
            f"{metadata.width}x{metadata.height}, {metadata.fps}fps, {metadata.file_size_bytes / 1024 / 1024:.2f} MB)"
        )
        return metadata

    def _render_scene_motion_clip(
        self,
        image_path: Path,
        duration_sec: float,
        motion_type: str,
        output_clip: Path,
    ) -> Path:
        """Render a single scene image into an animated 1080x1920 video clip with camera motion."""
        frames = max(30, int(round(duration_sec * self.FPS)))
        
        # Determine zoompan filter expression
        if motion_type == "pull_back":
            # Dramatic pull back: starts zoomed in (1.18), pulls back to full frame (1.0)
            zoom_expr = f"zoompan=z='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={self.WIDTH}x{self.HEIGHT}:fps={self.FPS}"
        elif motion_type == "pan_down":
            # Slow inspection glide down the document/photograph
            zoom_expr = f"zoompan=z='1.12':x='iw/2-(iw/zoom/2)':y='min(ih-ih/zoom,(ih-ih/zoom)*on/{frames})':d={frames}:s={self.WIDTH}x{self.HEIGHT}:fps={self.FPS}"
        elif motion_type == "pan_right":
            # Slow horizontal scan across historical environment
            zoom_expr = f"zoompan=z='1.12':x='min(iw-iw/zoom,(iw-iw/zoom)*on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s={self.WIDTH}x{self.HEIGHT}:fps={self.FPS}"
        elif motion_type == "pan_up":
            # Upward tilt
            zoom_expr = f"zoompan=z='1.12':x='iw/2-(iw/zoom/2)':y='max(0,(ih-ih/zoom)*(1-on/{frames}))':d={frames}:s={self.WIDTH}x{self.HEIGHT}:fps={self.FPS}"
        elif motion_type == "static_reveal":
            # Subtle micro-motion
            zoom_expr = f"zoompan=z='1.02':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={self.WIDTH}x{self.HEIGHT}:fps={self.FPS}"
        else:
            # Default push_in: slow cinematic push in towards subject (1.0 -> 1.18)
            zoom_expr = f"zoompan=z='min(zoom+0.0015,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={self.WIDTH}x{self.HEIGHT}:fps={self.FPS}"

        # Choose encoder flags
        if self.encoder == "h264_videotoolbox":
            codec_flags = ["-c:v", "h264_videotoolbox", "-b:v", "4M", "-pix_fmt", "yuv420p"]
        else:
            codec_flags = ["-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p"]

        cmd = [
            config.ffmpeg_path, "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", zoom_expr,
            "-t", f"{duration_sec:.3f}",
            *codec_flags,
            "-r", str(self.FPS),
            str(output_clip),
        ]

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return output_clip
        except subprocess.CalledProcessError as e:
            # Fallback to software encoding if VideoToolbox has an issue with specific dimension
            if self.encoder == "h264_videotoolbox":
                logger.warning("VideoToolbox encode had warning, falling back to libx264 for clip...")
                fallback_cmd = [
                    config.ffmpeg_path, "-y",
                    "-loop", "1",
                    "-i", str(image_path),
                    "-vf", zoom_expr,
                    "-t", f"{duration_sec:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-r", str(self.FPS),
                    str(output_clip),
                ]
                subprocess.run(fallback_cmd, capture_output=True, text=True, check=True)
                return output_clip
            raise RuntimeError(f"Failed to render scene motion clip: {e.stderr}")

    # -------------------------------------------------------------------------
    # Legacy Renderer Support (Preserves Backwards Compatibility)
    # -------------------------------------------------------------------------

    def render(
        self,
        job_id: str,
        audio_path: Path,
        scene_assets: List[ProducedSceneAsset],
        caption_cues: List[CaptionCue],
        output_mp4: Path,
        background_music_path: Optional[Path] = None,
    ) -> VideoMetadata:
        """Render complete 1080x1920 vertical MP4 video with synchronized scenes, captions, and audio."""
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_mp4.parent / "render_tmp"
        work_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Rendering vertical Short for job {job_id} -> {output_mp4.name}...")
        start_time = time.time()

        total_duration = self._get_media_duration(audio_path)
        if total_duration <= 0.0:
            raise RuntimeError(f"Audio file {audio_path} has invalid duration: {total_duration}")

        proportional_scenes = self._compute_proportional_scene_durations(scene_assets, total_duration)

        concat_file = work_dir / "scenes_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for scene_path, dur in proportional_scenes:
                escaped_path = str(scene_path.resolve()).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
                f.write(f"duration {dur:.3f}\n")
            last_path = str(proportional_scenes[-1][0].resolve()).replace("'", "'\\''")
            f.write(f"file '{last_path}'\n")

        cmd = [
            config.ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(audio_path),
        ]

        filter_parts: List[str] = [f"[0:v]fps={self.FPS}[v_base]"]
        last_v = "v_base"
        for c_idx, cue in enumerate(caption_cues):
            cmd.extend(["-i", str(cue.overlay_path.resolve())])
            input_idx = 2 + c_idx
            out_v = f"v_cap_{c_idx}"
            between_expr = f"between(t,{cue.start_sec:.3f},{cue.end_sec:.3f})"
            filter_parts.append(f"[{last_v}][{input_idx}:v]overlay=x=0:y=0:enable='{between_expr}'[{out_v}]")
            last_v = out_v

        cmd.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[{last_v}]",
            "-map", "1:a",
            "-t", f"{total_duration:.3f}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", str(self.FPS),
            str(output_mp4),
        ])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg render error: {e.stderr[-500:] if e.stderr else 'unknown'}")

        metadata = self.inspect_video(output_mp4)
        self.extract_preview_frames(output_mp4, output_dir=output_mp4.parent / "previews")
        return metadata

    # -------------------------------------------------------------------------
    # Inspection and Preview Utilities
    # -------------------------------------------------------------------------

    def inspect_video(self, video_path: Path) -> VideoMetadata:
        """Inspect video file metadata using FFprobe."""
        if not video_path.exists():
            raise FileNotFoundError(f"Video file does not exist: {video_path}")

        cmd = [
            config.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration,size,bit_rate",
            "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of", "json",
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)

        fmt = data.get("format", {})
        streams = data.get("streams", [])

        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        fps = 30.0
        if v_stream and v_stream.get("r_frame_rate"):
            num, den = v_stream["r_frame_rate"].split("/")
            fps = float(num) / float(den) if float(den) > 0 else 30.0

        return VideoMetadata(
            duration_sec=float(fmt.get("duration", 0.0)),
            width=int(v_stream.get("width", 0)) if v_stream else 0,
            height=int(v_stream.get("height", 0)) if v_stream else 0,
            fps=fps,
            video_codec=v_stream.get("codec_name", "") if v_stream else "",
            audio_codec=a_stream.get("codec_name", "") if a_stream else "",
            file_size_bytes=int(fmt.get("size", 0)),
            has_video_stream=v_stream is not None,
            has_audio_stream=a_stream is not None,
        )

    def extract_preview_frames(
        self,
        video_path: Path,
        output_dir: Path,
        timestamps: Optional[List[float]] = None,
    ) -> List[Path]:
        """Extract representative preview frames from finished video for inspection."""
        output_dir.mkdir(parents=True, exist_ok=True)
        duration = self._get_media_duration(video_path)

        if not timestamps:
            timestamps = [
                round(duration * 0.15, 2),
                round(duration * 0.50, 2),
                round(duration * 0.85, 2),
            ]

        extracted: List[Path] = []
        for idx, ts in enumerate(timestamps, start=1):
            out_img = output_dir / f"frame_preview_{idx:02d}.jpg"
            cmd = [
                config.ffmpeg_path, "-y",
                "-ss", str(ts),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(out_img),
            ]
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                if out_img.exists() and out_img.stat().st_size > 0:
                    extracted.append(out_img)
            except Exception as e:
                logger.warning(f"Failed to extract frame at {ts}s: {e}")

        logger.info(f"Extracted {len(extracted)} representative frames into {output_dir.name}")
        return extracted

    def _get_media_duration(self, file_path: Path) -> float:
        """Measure precise media duration via ffprobe."""
        cmd = [
            config.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())

    def _compute_proportional_scene_durations(
        self, scenes: List[ProducedSceneAsset], total_duration: float
    ) -> List[Tuple[Path, float]]:
        """Scale nominal scene durations proportionally to exactly match narration length."""
        nominal_sum = sum(s.duration_sec for s in scenes)
        if nominal_sum <= 0:
            nominal_sum = len(scenes) * 8.0

        results = []
        allocated = 0.0
        for idx, s in enumerate(scenes):
            if idx == len(scenes) - 1:
                dur = max(1.0, round(total_duration - allocated, 3))
            else:
                dur = max(1.0, round((s.duration_sec / nominal_sum) * total_duration, 3))
                allocated += dur
            results.append((s.image_path, dur))
        return results
