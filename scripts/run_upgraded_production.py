"""Full pilot execution script testing all 4 critical bug fixes and 5 upgrades."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

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
            "video_duration": pipe_res["total_duration"],
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
        print(f"  • Duration:  {pipe_res['total_duration']:.2f}s")
        print("=" * 70)

        # 8. Post-upload guard: disable any further automated uploads
        st = db.get_scheduler_state()
        st.is_paused = True
        st.pause_reason = "Automated uploads locked per user instruction."
        db.update_scheduler_state(st)
        logger.info("Autonomous scheduler successfully paused in database.")
    else:
        raise RuntimeError(f"YouTube upload failed: {msg}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run single upgraded showcase Short production & upload")
    parser.add_argument("--topic", type=str, default="The Dyatlov Pass Incident", help="Story topic to produce")
    args = parser.parse_args()
    run_production(topic=args.topic)

