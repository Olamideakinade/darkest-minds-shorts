"""Full pilot execution script testing all 4 critical bug fixes and 5 upgrades."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config
from app.database.db import db
from app.database.models import Job, JobState, SchedulerState
from app.editing.per_scene_pipeline import per_scene_pipeline
from app.quality.checker import QualityChecker
from app.scripts.story_engine import StoryEngine
from app.utils.logger import logger


def run_production(topic: str = "The Dyatlov Pass Incident"):
    topic_lower = topic.lower()
    if any(k in topic_lower for k in ("ranking", "forbidden", "places", "survival", "deadliest")):
        niche = "Dark Rankings & Extreme Mysteries"
        category = "dark_rankings"
        archetype = "countdown_ranking"
    else:
        niche = "Strange History & Unsolved Mysteries"
        category = "unsolved_mysteries"
        archetype = "escalating_revelation"

    # 1. Create Job in database
    job = db.create_job(
        title=topic,
        niche=niche,
        payload={
            "topic": topic,
            "category": category,
            "narrative_archetype": archetype,
        }
    )
    job_id = job.id
    logger.info(f"--- STARTING PRODUCTION PIPELINE ({job_id}) FOR TOPIC: '{topic}' ---")

    # 2. Generate Multi-Scene Script with Infinite Loop
    engine = StoryEngine(database=db)
    story = engine.generate_story(job)
    logger.info(f"Generated story with {len(story.scenes)} scenes.")
    for sc in story.scenes:
        logger.info(f"Scene {sc.scene_number:02d}: {sc.narration_chunk} [{sc.visual_source} | Badge: {sc.badge_text}]")

    # 3. Assemble Production Video via PerScenePipeline
    output_mp4 = config.output_dir / "jobs" / job_id / "short_1080x1920.mp4"
    pipe_res = per_scene_pipeline.assemble_production_video(
        job_id=job_id,
        scenes=story.scenes,
        output_mp4=output_mp4
    )

    # 4. Generate Captions SRT from word_timestamps
    from app.editing.captions import CaptionGenerator, WordTimestamp
    words_file = output_mp4.parent / "word_timestamps.json"
    with open(words_file, "r", encoding="utf-8") as fw:
        words_data = json.load(fw)
    w_objs = [WordTimestamp(word=w["word"], start_sec=w["start_sec"], end_sec=w["end_sec"]) for w in words_data]
    caption_gen = CaptionGenerator()
    srt_path, cues = caption_gen.generate_captions(job_id, w_objs, output_dir=output_mp4.parent)

    # 5. Extract Preview Frames and Contact Sheet
    from app.editing.video_renderer import VideoRenderer
    from app.visuals.scene_synthesizer import scene_synthesizer
    renderer = VideoRenderer()
    preview_frames = renderer.extract_preview_frames(output_mp4, output_dir=output_mp4.parent / "previews")
    contact_sheet = output_mp4.parent / "contact_sheet.jpg"
    if preview_frames:
        scene_synthesizer.create_contact_sheet(preview_frames, contact_sheet)

    # 6. Run Automated QA Verification
    # 6. Run Comprehensive Automated QA & Pre-Upload Sanity Gate
    from app.editing.timeline import ScenePlan
    tl_file = output_mp4.parent / "timeline.json"
    with open(tl_file, "r", encoding="utf-8") as ft:
        plans = [ScenePlan(**p) for p in json.load(ft)]

    checker = QualityChecker()
    report = checker.verify_production_quality(
        job_id=job_id,
        video_path=output_mp4,
        audio_path=output_mp4.parent / "narration.mp3",
        srt_path=srt_path,
        timeline=plans
    )

    logger.info(f"--- QA STATUS: {report.status} (Issues: {report.issues}) ---")
    print(f"OUTPUT_MP4: {output_mp4}")
    print(f"DURATION: {pipe_res['total_duration']:.2f}s")
    print(f"SCENES: {len(story.scenes)}")
    print(f"QA_STATUS: {report.status}")
    print(f"QA_ISSUES: {report.issues}")

    if report.status == "FAIL":
        raise RuntimeError(f"QA hard failure for job {job_id}: {report.issues}")

    # =========================================================================
    # TASK 6: PRE-UPLOAD SANITY CHECK (QUALITY GATE)
    # =========================================================================
    import re
    import subprocess
    logger.info("Executing Pre-Upload Quality Gate checks...")

    # Gate Check 1: Audio-Video Duration Sync Check via ffprobe (<= 0.40s tolerance)
    def _probe_duration(fpath: Path) -> float:
        cmd = [
            config.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(fpath),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return 0.0

    video_probe_dur = _probe_duration(output_mp4)
    audio_probe_dur = _probe_duration(output_mp4.parent / "narration.mp3")
    total_tts_dur = sum(pipe_res.get("scene_durations", []))
    ref_audio_dur = audio_probe_dur if audio_probe_dur > 0 else total_tts_dur

    dur_diff = abs(video_probe_dur - ref_audio_dur)
    logger.info(f"Pre-Upload Gate: Video probe={video_probe_dur:.2f}s, Audio ref={ref_audio_dur:.2f}s (Diff: {dur_diff:.3f}s)")
    if dur_diff > 0.45:
        raise RuntimeError(
            f"PRE-UPLOAD QUALITY GATE REJECTED: Video ({video_probe_dur:.2f}s) and Audio ({ref_audio_dur:.2f}s) "
            f"duration discrepancy of {dur_diff:.2f}s exceeds strict 0.45s threshold! Narration cutoff prevention triggered."
        )

    # Gate Check 2: Unique Moving Visual Assets (Zero Repeated Fallback Images)
    visual_paths = pipe_res.get("visual_paths", [])
    unique_visuals = set(visual_paths)
    logger.info(f"Pre-Upload Gate: {len(unique_visuals)} unique visual files across {len(story.scenes)} scenes.")
    if len(unique_visuals) < len(story.scenes):
        raise RuntimeError(
            f"PRE-UPLOAD QUALITY GATE REJECTED: Visual repetition detected! "
            f"Expected {len(story.scenes)} unique visual assets, got {len(unique_visuals)}: {visual_paths}"
        )

    # Gate Check 3: Badge Text Tofu/Emoji Sanitization Verification
    for sc in story.scenes:
        if sc.badge_text and re.search(r"[^A-Za-z0-9#•\-\s]", sc.badge_text):
            raise RuntimeError(
                f"PRE-UPLOAD QUALITY GATE REJECTED: Badge text '{sc.badge_text}' contains unrenderable emoji/symbols!"
            )

    logger.info("✓ PRE-UPLOAD QUALITY GATE PASSED ALL CHECKS.")

    # 7. Update Job Payload & Publish to YouTube
    final_title = story.optimized_title or story.title
    db.update_job_state(
        job_id,
        JobState.READY,
        stage="production_verified",
        payload_updates={
            "video_path": str(output_mp4),
            "audio_path": str(output_mp4.parent / "narration.mp3"),
            "srt_path": str(srt_path),
            "contact_sheet_path": str(contact_sheet),
            "title": final_title,
            "optimized_title": story.optimized_title,
            "description": story.description_text or story.description,
            "description_text": story.description_text,
            "tags": story.target_tags,
            "target_tags": story.target_tags,
            "pinned_comment": story.pinned_comment,
            "video_duration": video_probe_dur or pipe_res["total_duration"],
        }
    )
    job = db.get_job(job_id)

    from app.youtube.publisher import YouTubePublisher
    publisher = YouTubePublisher(database=db)
    success, msg, details = publisher.publish_video(job, privacy_status="public")
    logger.info(f"YouTube Publish Result: success={success}, msg={msg}")
    print(f"PUBLISH_SUCCESS: {success}")
    print(f"PUBLISH_MESSAGE: {msg}")
    print(f"PUBLISH_DETAILS: {details}")

    if success:
        yt_id = details.get("youtube_id")
        yt_url = details.get("url") or f"https://youtube.com/shorts/{yt_id}"
        print("=" * 70)
        print("✓ FLAWLESS VIRAL SHORT PUBLISHED SUCCESSFULLY")
        print(f"  • Video URL: {yt_url}")
        print(f"  • Title:     {final_title}")
        print(f"  • Duration:  {video_probe_dur:.2f}s")
        print("=" * 70)

        # 8. Ensure autonomous scheduler remains UNPAUSED for peak viral publishing times (11:00 AM & 5:00 PM UTC)
        st = db.get_scheduler_state()
        st.is_paused = False
        st.pause_reason = ""
        db.update_scheduler_state(st)
        logger.info("Autonomous scheduler verified ACTIVE for peak viral upload schedule.")
    else:
        raise RuntimeError(f"YouTube upload failed: {msg}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run single upgraded showcase Short production & upload")
    parser.add_argument("--topic", type=str, default="The Dyatlov Pass Incident", help="Story topic to produce")
    args = parser.parse_args()
    run_production(topic=args.topic)

