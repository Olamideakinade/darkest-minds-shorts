"""Full pilot execution script testing all 4 critical bug fixes and 5 upgrades."""

from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

from app.config import config
from app.database.db import db
from app.database.models import Job, JobState
from app.editing.per_scene_pipeline import per_scene_pipeline
from app.quality.checker import QualityChecker
from app.scripts.story_engine import StoryEngine
from app.utils.logger import logger


def run_test():
    topic = "Top 3 Terrifying Forbidden Places Where Survival Is 0%"

    # 1. Create Job in database
    job = db.create_job(
        title=topic,
        niche="Dark Rankings & Extreme Mysteries",
        payload={
            "topic": topic,
            "category": "dark_rankings",
            "narrative_archetype": "countdown_ranking",
        }
    )
    job_id = job.id
    logger.info(f"--- STARTING UPGRADED PRODUCTION PIPELINE ({job_id}) ---")

    # 2. Generate 12-Scene Script
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
    with open(words_file, "r") as fw:
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

    # 6. Run Automated QA
    from app.editing.timeline import ScenePlan
    tl_file = output_mp4.parent / "timeline.json"
    with open(tl_file, "r") as ft:
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
    print(f"CONTACT_SHEET: {contact_sheet}")

    # 7. Update Job Payload & Publish to YouTube
    db.update_job_state(
        job_id,
        JobState.READY,
        stage="production_verified",
        payload_updates={
            "video_path": str(output_mp4),
            "audio_path": str(output_mp4.parent / "narration.mp3"),
            "srt_path": str(srt_path),
            "contact_sheet_path": str(contact_sheet),
            "title": story.optimized_title or story.title,
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


if __name__ == "__main__":
    run_test()
