"""Per-scene audio-visual assembly pipeline with millisecond synchronization.

Guarantees 100% audio-video sync by synthesizing audio per scene, trimming
dead silence, measuring exact duration with ffprobe, rendering each scene's
visual to match that duration, and concatenating all scenes together.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import random
import re
import struct
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import wave

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from app.config import config
from app.database.db import Database, db
from app.database.models import MediaAsset, utc_now_iso
from app.editing.motion_graphics import MotionGraphicsEngine, VideoClipStream
from app.narration.tts_service import TTSService, WordTimestamp
from app.scripts.story_models import StoryScene
from app.utils.logger import logger
from app.visuals.pixabay_video_client import pixabay_video_client


class PerScenePipeline:
    """Renders fast-paced YouTube Shorts with millisecond audio-video sync."""

    WIDTH = 1080
    HEIGHT = 1920
    FPS = 30

    def __init__(self, database: Optional[Database] = None) -> None:
        self.db = database or db
        self.tts = TTSService(database=self.db)
        self.mg = MotionGraphicsEngine()

    def assemble_production_video(
        self,
        job_id: str,
        scenes: List[StoryScene],
        output_mp4: Path,
    ) -> Dict[str, Any]:
        """Execute end-to-end per-scene production and assemble the final Short."""
        job_dir = output_mp4.parent
        job_dir.mkdir(parents=True, exist_ok=True)
        scenes_dir = job_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = job_dir / "render_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting PerScenePipeline for job {job_id} ({len(scenes)} scenes)...")
        pixabay_video_client.reset_session()

        rendered_scene_paths: List[Path] = []
        scene_durations: List[float] = []
        all_word_timestamps: List[Dict[str, Any]] = []
        global_time_cursor = 0.0

        timeline_plans: List[Any] = []
        global_cursor_t = 0.0

        for idx, scene in enumerate(scenes):
            s_num = scene.scene_number
            logger.info(f"[Scene {s_num:02d}/{len(scenes):02d}] Processing: '{scene.narration_chunk[:45]}...'")

            # 1. Synthesize & trim audio for this individual scene
            audio_path, duration_sec, word_ts = self._produce_scene_audio(
                job_id=job_id,
                scene=scene,
                scene_index=idx,
                output_dir=scenes_dir,
            )
            scene_durations.append(duration_sec)

            # Offset word timestamps to global timeline
            for w in word_ts:
                all_word_timestamps.append({
                    "word": w.word,
                    "start_sec": round(global_time_cursor + w.start_sec, 3),
                    "end_sec": round(global_time_cursor + w.end_sec, 3),
                })
            start_scene_t = global_time_cursor
            global_time_cursor += duration_sec

            # 2. Acquire visual asset (Pollinations Flux AI or generic video b-roll)
            visual_path, is_video = self._acquire_scene_visual(
                scene=scene,
                scene_index=idx,
                job_dir=job_dir,
                duration_sec=duration_sec,
            )

            # Build ScenePlan for timeline tracking and QA
            from app.editing.timeline import ScenePlan
            plan = ScenePlan(
                scene_number=s_num,
                start_sec=round(start_scene_t, 3),
                end_sec=round(global_time_cursor, 3),
                duration_sec=round(duration_sec, 3),
                narration_segment=scene.narration_chunk,
                visual_purpose="tension",
                asset_type="archival_footage" if is_video else "archival_photo",
                search_query=scene.pexels_query or "flux",
                motion_type="push_in",
                transition_type="cut",
                kinetic_text=scene.badge_text,
                rendered_clip_path=visual_path if is_video else None,
                rendered_image_path=visual_path if not is_video else None,
            )
            timeline_plans.append(plan)

            # 3. Render scene video with exact frame count matching duration_sec
            scene_merged_mp4 = scenes_dir / f"scene_{s_num:02d}_merged.mp4"
            self._render_single_scene(
                scene=scene,
                scene_index=idx,
                visual_path=visual_path,
                is_video=is_video,
                audio_path=audio_path,
                duration_sec=duration_sec,
                word_timestamps=word_ts,
                output_mp4=scene_merged_mp4,
            )
            rendered_scene_paths.append(scene_merged_mp4)

        # 4. Save word timestamps & timeline.json
        words_path = job_dir / "word_timestamps.json"
        with open(words_path, "w", encoding="utf-8") as f_w:
            json.dump(all_word_timestamps, f_w, indent=2)

        timeline_path = job_dir / "timeline.json"
        with open(timeline_path, "w", encoding="utf-8") as f_tl:
            json.dump([p.to_dict() for p in timeline_plans], f_tl, indent=2)

        # 5. Concatenate all scenes seamlessly
        concat_raw_mp4 = tmp_dir / "concatenated_raw.mp4"
        self._concatenate_scenes(rendered_scene_paths, concat_raw_mp4)

        # 6. Final soundtrack mastering (Background horror drone @ -18dB + transition whooshes)
        self._master_final_soundtrack(
            video_input=concat_raw_mp4,
            scene_durations=scene_durations,
            output_mp4=output_mp4,
            job_dir=job_dir,
        )

        total_duration = sum(scene_durations)
        full_audio_path = job_dir / "narration.mp3"
        try:
            cmd_audio = [
                config.ffmpeg_path, "-y",
                "-i", str(output_mp4),
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                str(full_audio_path),
            ]
            subprocess.run(cmd_audio, capture_output=True)
        except Exception:
            pass

        logger.info(f"PerScenePipeline completed successfully: {output_mp4.name} ({total_duration:.1f}s, {len(scenes)} scenes)")

        return {
            "video_path": str(output_mp4),
            "audio_path": str(full_audio_path) if full_audio_path.exists() else None,
            "total_duration": total_duration,
            "scenes_count": len(scenes),
            "scene_durations": scene_durations,
            "word_timestamps_count": len(all_word_timestamps),
        }

    # -------------------------------------------------------------------------
    # Step 1: Per-Scene Audio Synthesis & Silence Trimming
    # -------------------------------------------------------------------------

    def _produce_scene_audio(
        self,
        job_id: str,
        scene: StoryScene,
        scene_index: int,
        output_dir: Path,
    ) -> Tuple[Path, float, List[WordTimestamp]]:
        """Synthesize TTS audio for a single sentence and trim dead silence."""
        raw_audio_path = output_dir / f"scene_{scene.scene_number:02d}_raw.mp3"
        trimmed_audio_path = output_dir / f"scene_{scene.scene_number:02d}_audio.mp3"

        # Edge-TTS with user-requested cinematic tuning: ChristopherNeural at +8% rate, -6Hz pitch
        # (or ElevenLabs Adam if configured)
        res = self.tts.synthesize(
            job_id=f"{job_id}_s{scene.scene_number}",
            text=scene.narration_chunk,
            output_path=raw_audio_path,
        )

        # Measure raw duration
        raw_dur = self._get_duration(raw_audio_path)
        if raw_dur <= 0.0:
            raw_dur = res.duration_sec

        # Trim leading/trailing dead silence (>0.15s) using acoustic word boundaries
        if res.word_timestamps:
            first_w = res.word_timestamps[0]
            last_w = res.word_timestamps[-1]

            # Leading silence: keep 40ms buffer before first word if leading dead silence > 0.12s
            trim_start = max(0.0, first_w.start_sec - 0.04) if first_w.start_sec > 0.12 else 0.0

            # Trailing silence: keep 80ms buffer after last word
            trim_end = min(raw_dur, last_w.end_sec + 0.08)
            trimmed_target_dur = max(0.3, trim_end - trim_start)

            trim_cmd = [
                config.ffmpeg_path, "-y",
                "-ss", f"{trim_start:.3f}",
                "-to", f"{trim_end:.3f}",
                "-i", str(raw_audio_path),
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(trimmed_audio_path),
            ]
            trim_res = subprocess.run(trim_cmd, capture_output=True, text=True)

            dur = self._get_duration(trimmed_audio_path)
            if dur <= 0.2:
                dur = trimmed_target_dur
                trimmed_audio_path = raw_audio_path
                trim_start = 0.0

            adjusted_words: List[WordTimestamp] = []
            for w in res.word_timestamps:
                adjusted_words.append(
                    WordTimestamp(
                        word=w.word,
                        start_sec=max(0.0, round(w.start_sec - trim_start, 3)),
                        end_sec=max(0.0, round(w.end_sec - trim_start, 3)),
                        is_estimated=w.is_estimated,
                    )
                )
        else:
            trimmed_audio_path = raw_audio_path
            dur = raw_dur
            adjusted_words = res.word_timestamps

        return trimmed_audio_path, dur, adjusted_words

    # -------------------------------------------------------------------------
    # Step 2: Visual Asset Acquisition (Strict Hybrid Visual Router)
    # -------------------------------------------------------------------------

    def _acquire_scene_visual(
        self,
        scene: StoryScene,
        scene_index: int,
        job_dir: Path,
        duration_sec: float,
    ) -> Tuple[Path, bool]:
        """Fetch custom 9:16 dark photorealistic image via Pollinations Flux, or stock video b-roll."""
        visual_source = getattr(scene, "visual_source", "ai_flux")
        visuals_dir = job_dir / "visuals"
        visuals_dir.mkdir(parents=True, exist_ok=True)

        # 1. Generic Stock Video: ONLY used for 100% generic nature/animal b-roll
        if visual_source == "pexels_video":
            query = scene.pexels_query or "storm sea"
            # Strict negative keyword filtering
            forbidden_terms = {"city", "resort", "cars", "tourists", "hotel", "happy"}
            if not any(term in query.lower() for term in forbidden_terms):
                video_clip = pixabay_video_client.search_and_download_video(query=query, target_duration=duration_sec)
                if video_clip and video_clip.exists():
                    return video_clip, True

        # 2. Pollinations Flux AI Image Generation (70-75% of scenes)
        flux_path = visuals_dir / f"scene_{scene.scene_number:02d}_flux.jpg"
        if flux_path.exists() and flux_path.stat().st_size > 10000:
            return flux_path, False

        prompt = scene.ai_image_prompt or scene.visual_prompt or "dark cinematic mystery background, horror documentary, 8k, photorealistic"
        # Enforce dark documentary parameters
        full_prompt = f"{prompt}, dark documentary style, cinematic lighting, 8k resolution, highly detailed, photorealistic, vertical 9:16 composition, eerie atmosphere, no modern cars, no tourists, no modern buildings"

        seed = random.randint(1000, 999999)
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(full_prompt)}?width=1080&height=1920&model=flux&nologo=true&enhance=true&seed={seed}"

        try:
            logger.info(f"Generating Flux AI visual for scene {scene.scene_number}: '{full_prompt[:50]}...'")
            req = urllib.request.Request(url, headers={"User-Agent": "MhideDev-Bot/2.0"})
            with urllib.request.urlopen(req, timeout=20) as response, open(flux_path, "wb") as out_f:
                out_f.write(response.read())

            if flux_path.exists() and flux_path.stat().st_size > 5000:
                return flux_path, False
        except Exception as e:
            logger.warning(f"Pollinations Flux generation failed for scene {scene.scene_number} ({e}). Routing to Pixabay Photo API...")

        # 3. High-Resolution Photorealistic Photo Fallback via Pixabay Photo API (with negative keyword filtering)
        photo_query = scene.pexels_query or scene.visual_prompt or "dark mystery"
        photo_clip = pixabay_video_client.search_and_download_photo(query=photo_query, orientation="vertical")
        if photo_clip and photo_clip.exists() and photo_clip.stat().st_size > 5000:
            return photo_clip, False

        # 4. Fallback to local curated dark asset
        fallback_dir = Path("data/curated_assets")
        local_candidates = list(fallback_dir.glob("**/*.jpg")) + list(fallback_dir.glob("**/*.png"))
        if local_candidates:
            fallback = local_candidates[scene_index % len(local_candidates)]
            return fallback, False

        # Ultimate fallback: create high-res gradient card
        fb_img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (12, 16, 26))
        draw = ImageDraw.Draw(fb_img)
        draw.rectangle([0, 0, self.WIDTH, self.HEIGHT], fill=(15, 18, 25))
        fb_path = visuals_dir / f"scene_{scene.scene_number:02d}_fb.png"
        fb_img.save(fb_path)
        return fb_path, False

    # -------------------------------------------------------------------------
    # Step 3: Single Scene Video Rendering (4-Direction Motion + Overlays)
    # -------------------------------------------------------------------------

    def _render_single_scene(
        self,
        scene: StoryScene,
        scene_index: int,
        visual_path: Path,
        is_video: bool,
        audio_path: Path,
        duration_sec: float,
        word_timestamps: List[WordTimestamp],
        output_mp4: Path,
    ) -> None:
        """Render a single scene video of exact duration_sec and mux with scene audio."""
        frames_count = max(1, int(round(duration_sec * self.FPS)))
        logger.info(f"Rendering scene {scene.scene_number:02d}: {duration_sec:.2f}s ({frames_count} frames, is_video={is_video})...")

        # Step 1: Pre-render background visual clip with required motion, looping, and color grading
        bg_clip_mp4 = output_mp4.parent / f"bg_scene_{scene.scene_number:02d}.mp4"
        video_stream: Optional[VideoClipStream] = None
        base_img: Optional[Image.Image] = None

        try:
            if is_video and visual_path.exists():
                # Bug 2 fix: Put -stream_loop -1 BEFORE -i and -t AFTER -i so short clips loop seamlessly
                cmd_bg = [
                    config.ffmpeg_path, "-y",
                    "-stream_loop", "-1",
                    "-i", str(visual_path),
                    "-t", f"{duration_sec:.3f}",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.15:brightness=-0.06:saturation=0.75,vignette=PI/4",
                    "-r", str(self.FPS),
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-pix_fmt", "yuv420p",
                    str(bg_clip_mp4),
                ]
            else:
                # Bug 1 fix: FFmpeg zoompan from min 1.08 to 1.28 (crops out bottom-right watermark)
                vf_zoompan = (
                    f"scale=2160:3840,"
                    f"zoompan=z='min(max(zoom,1.08)+0.002,1.28)':d={frames_count}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                    f"eq=contrast=1.15:brightness=-0.06:saturation=0.75,vignette=PI/4"
                )
                cmd_bg = [
                    config.ffmpeg_path, "-y",
                    "-loop", "1",
                    "-i", str(visual_path),
                    "-vf", vf_zoompan,
                    "-t", f"{duration_sec:.3f}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-pix_fmt", "yuv420p",
                    str(bg_clip_mp4),
                ]

            subprocess.run(cmd_bg, capture_output=True, check=True)
            video_stream = VideoClipStream(bg_clip_mp4, width=self.WIDTH, height=self.HEIGHT, fps=self.FPS)
        except Exception as e:
            logger.warning(f"Background clip pre-render failed for scene {scene.scene_number} ({e}). Falling back to direct stream.")
            if is_video and visual_path.exists():
                video_stream = VideoClipStream(visual_path, width=self.WIDTH, height=self.HEIGHT, fps=self.FPS)
            else:
                try:
                    base_img = Image.open(visual_path).convert("RGB")
                except Exception:
                    base_img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (15, 18, 25))

        # FFmpeg command: receives raw 1080x1920 RGB frames from pipe, muxes audio
        cmd = [
            config.ffmpeg_path, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.WIDTH}x{self.HEIGHT}",
            "-pix_fmt", "rgb24",
            "-r", str(self.FPS),
            "-i", "-",
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_mp4),
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        motion_mode = scene_index % 4
        last_frame: Optional[Image.Image] = None

        for frame_idx in range(frames_count):
            t_norm = frame_idx / max(1, frames_count - 1)
            t_rel = frame_idx / float(self.FPS)

            # 1. Generate base visual frame
            if video_stream:
                stream_frame = video_stream.read_frame()
                if stream_frame:
                    frame = stream_frame.copy()
                    last_frame = frame
                elif last_frame:
                    frame = last_frame.copy()
                else:
                    frame = base_img.copy() if base_img else Image.new("RGB", (self.WIDTH, self.HEIGHT), (15, 18, 25))
            else:
                frame = self._apply_4dir_motion(base_img, t_norm, motion_mode)

            draw = ImageDraw.Draw(frame)

            # 2. Render Top Countdown Badge (Upgrade 4 & Bug 3 fix)
            badge_text = getattr(scene, "badge_text", "").strip()
            if badge_text:
                self._draw_countdown_badge(draw, text=badge_text, y_pos=220)

            # 3. Render Bottom 2-to-3 Word Pop Caption (Upgrade 5)
            caption_text = self._get_pop_caption(word_timestamps, t_rel, scene.narration_chunk)
            if caption_text:
                self._draw_subtitle_pill(draw, caption_text, y_pos=1380)

            proc.stdin.write(frame.tobytes())

        if video_stream:
            video_stream.close()

        proc.stdin.close()
        proc.wait()

        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg render error for scene {scene.scene_number}: {err[-400:]}")
            raise RuntimeError(f"FFmpeg failed to render scene {scene.scene_number}: {err[-200:]}")

    # -------------------------------------------------------------------------
    # 4-Direction Cinematic Camera Motion (Upgrade 1)
    # -------------------------------------------------------------------------

    def _apply_4dir_motion(self, img: Image.Image, t_norm: float, mode: int) -> Image.Image:
        """Apply 1 of 4 distinct cinematic camera moves at 1080x1920."""
        # Mode 0: Slow Push-In (zoom from 1.0x to 1.15x)
        if mode == 0:
            ease = 1.0 - math.pow(1.0 - t_norm, 2.2)
            scale = 1.00 + 0.15 * ease
            focal_x, focal_y = 0.50, 0.46
        # Mode 1: Slow Pull-Out (zoom from 1.18x down to 1.0x)
        elif mode == 1:
            ease = 1.0 - math.pow(1.0 - t_norm, 2.2)
            scale = 1.18 - 0.18 * ease
            focal_x, focal_y = 0.50, 0.46
        # Mode 2: Pan Left-to-Right (scale 1.15x, slide x from 0.38 to 0.62)
        elif mode == 2:
            ease = 1.0 - math.pow(1.0 - t_norm, 2.0)
            scale = 1.15
            focal_x = 0.38 + 0.24 * ease
            focal_y = 0.48
        # Mode 3: Slow Tilt Bottom-to-Top (scale 1.15x, slide y from 0.58 up to 0.38)
        else:
            ease = 1.0 - math.pow(1.0 - t_norm, 2.0)
            scale = 1.15
            focal_x = 0.50
            focal_y = 0.58 - 0.20 * ease

        return self.mg._crop_and_scale_focal(img, scale, focal_x, focal_y)

    # -------------------------------------------------------------------------
    # Graphics & Text Overlays
    # -------------------------------------------------------------------------

    def _draw_countdown_badge(self, draw: ImageDraw.ImageDraw, text: str, y_pos: int = 220) -> None:
        """Draw gold-bordered dark frosted countdown badge box at the top of the frame."""
        clean_text = text.upper().strip()
        font = self.mg.font_sub if hasattr(self.mg, "font_sub") else ImageFont.load_default()

        bbox = draw.textbbox((0, 0), clean_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 36
        pad_y = 18
        badge_w = text_w + pad_x * 2
        badge_h = text_h + pad_y * 2
        badge_x = (self.WIDTH - badge_w) // 2
        badge_y = y_pos

        # Dark frosted background
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=14,
            fill=(10, 14, 24),
            outline=(217, 164, 65),  # Pure gold border
            width=3,
        )

        # Crisp centered text
        tx = badge_x + (badge_w - text_w) // 2
        ty = badge_y + (badge_h - text_h) // 2 - 2
        draw.text((tx, ty), clean_text, font=font, fill=(255, 255, 255))

    def _get_pop_caption(self, word_ts: List[WordTimestamp], t_rel: float, fallback: str) -> str:
        """Find 2-to-3 word pop caption chunk active at the current scene timestamp."""
        if not word_ts:
            return fallback[:40].upper()

        # Find word active around t_rel
        active_idx = 0
        for i, w in enumerate(word_ts):
            if w.start_sec <= t_rel <= (w.end_sec + 0.15):
                active_idx = i
                break
            elif w.start_sec > t_rel:
                active_idx = max(0, i - 1)
                break
        else:
            active_idx = len(word_ts) - 1

        # Group into 2-to-3 words chunk
        chunk_start = (active_idx // 3) * 3
        chunk_words = [w.word for w in word_ts[chunk_start : chunk_start + 3]]
        return " ".join(chunk_words).upper()

    def _draw_subtitle_pill(self, draw: ImageDraw.ImageDraw, text: str, y_pos: int = 1380) -> None:
        """Draw high-contrast, yellow-highlighted caption pill in the safe mobile lower third."""
        clean_text = text.upper().strip()
        font = self.mg.font_sub if hasattr(self.mg, "font_sub") else ImageFont.load_default()

        bbox = draw.textbbox((0, 0), clean_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 32
        pad_y = 16
        pill_w = min(self.WIDTH - 120, text_w + pad_x * 2)
        pill_h = text_h + pad_y * 2
        pill_x = (self.WIDTH - pill_w) // 2
        pill_y = y_pos

        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=12,
            fill=(0, 0, 0),
            outline=(250, 204, 21),  # Intense yellow accent border
            width=2,
        )

        tx = pill_x + (pill_w - text_w) // 2
        ty = pill_y + (pill_h - text_h) // 2 - 2
        draw.text((tx, ty), clean_text, font=font, fill=(255, 255, 255))

    # -------------------------------------------------------------------------
    # Step 4: Video Concatenation
    # -------------------------------------------------------------------------

    def _concatenate_scenes(self, scene_paths: List[Path], output_mp4: Path) -> None:
        """Concatenate all scene MP4 files seamlessly using FFmpeg concat demuxer."""
        txt_path = output_mp4.parent / "scenes_list.txt"
        with open(txt_path, "w", encoding="utf-8") as f_txt:
            for p in scene_paths:
                f_txt.write(f"file '{p.resolve()}'\n")

        cmd = [
            config.ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(txt_path),
            "-c", "copy",
            str(output_mp4),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {res.stderr[-300:]}")

    # -------------------------------------------------------------------------
    # Step 5: Final Soundtrack Mastering (Horror Music @ -18dB + Transition SFX)
    # -------------------------------------------------------------------------

    def _generate_sfx_track(
        self,
        scene_durations: List[float],
        total_duration: float,
        output_wav: Path,
    ) -> Optional[Path]:
        """Synthesize a sample-accurate transition SFX track with whooshes and rank impacts."""
        try:
            sr = 44100
            total_samples = int(total_duration * sr) + sr
            buffer = [0.0] * total_samples

            whoosh_path = config.data_dir / "audio" / "sfx" / "transition_whoosh.wav"
            impact_path = config.data_dir / "audio" / "sfx" / "cinematic_sub_impact.wav"

            def _read_wav_samples(path: Path) -> List[float]:
                if not path.exists():
                    return []
                with wave.open(str(path), "rb") as wf:
                    n_frames = wf.getnframes()
                    frames = wf.readframes(n_frames)
                    if wf.getsampwidth() == 2 and wf.getnchannels() == 1:
                        return [s / 32768.0 for s in struct.unpack(f"<{n_frames}h", frames)]
                return []

            whoosh_samples = _read_wav_samples(whoosh_path)
            impact_samples = _read_wav_samples(impact_path)

            cur_t = 0.0
            for idx, dur in enumerate(scene_durations[:-1]):
                cur_t += dur
                start_sample = int(cur_t * sr)

                # Add whoosh at every scene boundary
                for j, s in enumerate(whoosh_samples):
                    if start_sample + j < len(buffer):
                        buffer[start_sample + j] += s * 0.45

                # Major rank reveals (e.g., transition to Scene 3 (#3), Scene 6 (#2), Scene 9 (#1))
                if (idx + 1) in (2, 5, 8) and impact_samples:
                    for j, s in enumerate(impact_samples):
                        if start_sample + j < len(buffer):
                            buffer[start_sample + j] += s * 0.40

            out_frames = bytearray()
            for s in buffer[: int(total_duration * sr)]:
                clamped = max(-1.0, min(1.0, s))
                val = int(clamped * 32767.0)
                out_frames.extend(struct.pack("<h", val))

            with wave.open(str(output_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(out_frames)

            return output_wav if output_wav.exists() and output_wav.stat().st_size > 100 else None
        except Exception as e:
            logger.warning(f"SFX track generation failed ({e}). Proceeding without custom SFX.")
            return None

    def _master_final_soundtrack(
        self,
        video_input: Path,
        scene_durations: List[float],
        output_mp4: Path,
        job_dir: Path,
    ) -> None:
        """Mix background horror drone at -18dB (volume 0.12) and add transition whoosh SFX."""
        music_path = config.data_dir / "audio" / "dark_suspense_drone.mp3"
        if not music_path.exists():
            music_path = config.data_dir / "audio" / "background.mp3"

        total_duration = sum(scene_durations)

        # If music doesn't exist, simply copy
        if not music_path.exists():
            cmd = [config.ffmpeg_path, "-y", "-i", str(video_input), "-c", "copy", str(output_mp4)]
            subprocess.run(cmd, capture_output=True)
            return

        sfx_wav = job_dir / "sfx_track.wav"
        sfx_path = self._generate_sfx_track(scene_durations, total_duration, sfx_wav)

        if sfx_path and sfx_path.exists():
            cmd = [
                config.ffmpeg_path, "-y",
                "-i", str(video_input),
                "-stream_loop", "-1", "-i", str(music_path),
                "-i", str(sfx_path),
                "-filter_complex",
                f"[1:a]volume=0.12,atrim=0:{total_duration:.2f}[bg];"
                f"[2:a]volume=1.0,atrim=0:{total_duration:.2f}[sfx];"
                f"[0:a][bg][sfx]amix=inputs=3:duration=first:dropout_transition=0[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_mp4),
            ]
        else:
            cmd = [
                config.ffmpeg_path, "-y",
                "-i", str(video_input),
                "-stream_loop", "-1", "-i", str(music_path),
                "-filter_complex",
                f"[1:a]volume=0.12,atrim=0:{total_duration:.2f}[bg];"
                f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_mp4),
            ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not output_mp4.exists() or output_mp4.stat().st_size == 0:
            logger.warning(f"Audio mastering fallback: copying raw video. FFmpeg err: {res.stderr[-200:]}")
            cmd_copy = [config.ffmpeg_path, "-y", "-i", str(video_input), "-c", "copy", str(output_mp4)]
            subprocess.run(cmd_copy, capture_output=True)

    def _get_duration(self, file_path: Path) -> float:
        """Measure exact media duration via ffprobe."""
        cmd = [
            config.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return 0.0


# Singleton instance
per_scene_pipeline = PerScenePipeline()
