"""Render a fresh pilot mystery video for Darkest Minds 101."""

from __future__ import annotations
import json
from pathlib import Path

from app.config import config
from app.database.db import Database
from app.database.models import JobState
from app.orchestrator import Orchestrator
from app.visuals.scene_synthesizer import SceneSynthesizer

def main() -> None:
    db = Database()
    
    # Clean out any old/stale queued or test jobs
    with db.connection() as conn:
        conn.execute("DELETE FROM jobs WHERE id LIKE 'probe%' OR title LIKE 'Researching%'")

    title = "The Flannan Isles Mystery: Three Keepers Vanished"
    print(f"Creating job: {title}...")
    job = db.create_job(
        title=title,
        payload={
            "topic": title,
            "category": "Unsolved Mysteries & Strange Disappearances",
            "angle": "Investigative breakdown of the missing keepers on Eilean Mor",
            "hook_style": "in_media_res_anomaly",
            "narrative_archetype": "unexplained_disappearance",
            "niche": "Unsolved Mysteries & Strange Disappearances",
        }
    )
    print(f"Enqueued Job ID: {job.id}")

    orchestrator = Orchestrator(database=db)
    processed_job = orchestrator.process_next_job()

    if not processed_job:
        print("ERROR: No job was processed.")
        return

    print(f"Job state: {processed_job.state}")
    job_dir = config.output_dir / "jobs" / processed_job.id
    video_path = job_dir / "short_1080x1920.mp4"
    print(f"Video file exists: {video_path.exists()} (size: {video_path.stat().st_size if video_path.exists() else 0} bytes)")

    # Read timeline and print scenes
    timeline_json = job_dir / "timeline.json"
    if timeline_json.exists():
        with open(timeline_json) as f:
            timeline_data = json.load(f)
        print(f"Total scenes rendered: {len(timeline_data)}")
        scene_files = []
        for s in timeline_data:
            rendered_p = s.get("rendered_image_path")
            print(f"Scene {s.get('scene_number')}: {s.get('visual_purpose')} | asset_type={s.get('asset_type')} | query={s.get('search_query')} | image={Path(rendered_p).name if rendered_p else 'NONE'}")
            if rendered_p and Path(rendered_p).exists():
                scene_files.append(Path(rendered_p))

        # Generate contact sheet
        contact_sheet_p = job_dir / "contact_sheet.jpg"
        synth = SceneSynthesizer()
        synth.create_contact_sheet(scene_files, contact_sheet_p)
        print(f"Contact sheet saved to: {contact_sheet_p} (exists: {contact_sheet_p.exists()})")

if __name__ == "__main__":
    main()
