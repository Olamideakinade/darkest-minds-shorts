from __future__ import annotations

from pathlib import Path
import sys

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.db import db
from app.database.models import JobState
from app.youtube.publisher import YouTubePublisher


def upload_job(job_id: str = "7596150d-0c3a-4104-8804-721102d42506"):
    job = db.get_job(job_id)
    if not job:
        print(f"Error: Job {job_id} not found.")
        return False

    print(f"Uploading job {job_id}: '{job.title}'...")
    publisher = YouTubePublisher(database=db)
    success, msg, details = publisher.publish_video(job, privacy_status="public")
    print(f"PUBLISH_SUCCESS: {success}")
    print(f"PUBLISH_MESSAGE: {msg}")
    print(f"PUBLISH_DETAILS: {details}")

    if success:
        yt_id = details.get("youtube_id")
        yt_url = details.get("url") or f"https://youtube.com/shorts/{yt_id}"
        print("=" * 70)
        print("✓ FLAWLESS VIRAL SHORT PUBLISHED SUCCESSFULLY")
        print(f"  • Video URL: {yt_url}")
        print(f"  • Title:     {job.title}")
        print("=" * 70)

        # Lock scheduler state in database
        st = db.get_scheduler_state()
        st.is_paused = True
        st.pause_reason = "Automated uploads locked per user instruction."
        db.update_scheduler_state(st)
        print("Autonomous scheduler paused in database.")
        return True
    else:
        print(f"Upload failed: {msg}")
        return False


if __name__ == "__main__":
    jid = sys.argv[1] if len(sys.argv) > 1 else "7596150d-0c3a-4104-8804-721102d42506"
    upload_job(jid)
