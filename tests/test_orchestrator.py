"""Unit tests for the job orchestrator lifecycle and concurrency controls."""

from pathlib import Path
from app.database.db import Database
from app.database.models import JobState
from app.orchestrator import Orchestrator


def test_orchestrator_job_lifecycle(tmp_path: Path):
    from app.config import config
    old_mode = config.youtube_publish_mode
    old_out = config.output_dir
    config.youtube_publish_mode = "disabled"
    config.output_dir = tmp_path
    try:
        db_file = tmp_path / "orch_test.db"
        test_db = Database(db_path=db_file)
        orch = Orchestrator(database=test_db)

        # 1. Enqueue Job
        job = orch.enqueue_job(title="Test Pipeline Short", niche="Science Curiosities")
        assert job.state == JobState.QUEUED

        # 2. Process Job
        completed_job = orch.process_next_job()
        assert completed_job is not None
        assert completed_job.id == job.id
        # Since YOUTUBE_PUBLISH_MODE is default 'disabled', final state is READY
        assert completed_job.state == JobState.READY
        assert completed_job.current_stage == "ready_for_review"
    finally:
        config.youtube_publish_mode = old_mode
        config.output_dir = old_out


def test_orchestrator_startup_recovery(tmp_path: Path):
    db_file = tmp_path / "orch_recovery.db"
    test_db = Database(db_path=db_file)

    # Inject an in-flight job simulating an interrupted run
    job = test_db.create_job(title="Interrupted Job")
    test_db.update_job_state(job.id, JobState.ASSEMBLING, stage="rendering_ffmpeg")

    orch = Orchestrator(database=test_db)
    summary = orch.startup()

    assert summary["recovered_jobs"] == 1
    recovered_job = test_db.get_job(job.id)
    assert recovered_job.state == JobState.RETRYING
