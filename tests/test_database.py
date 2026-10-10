"""Unit tests for SQLite database operations, transactions, and state machine."""

from pathlib import Path
from app.database.db import Database
from app.database.models import JobState, StoryIdea, ScriptRecord, QualityReport


def test_database_init_and_job_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test.db"
    test_db = Database(db_path=db_file)

    # 1. Create Job
    job = test_db.create_job(
        title="Test Story Job",
        niche="Strange History",
        payload={"test_param": 123},
    )
    assert job.id is not None
    assert job.state == JobState.QUEUED
    assert job.niche == "Strange History"

    # 2. Get Job
    retrieved = test_db.get_job(job.id)
    assert retrieved is not None
    assert retrieved.title == "Test Story Job"
    assert retrieved.payload.get("test_param") == 123

    # 3. State update
    success = test_db.update_job_state(job.id, JobState.RESEARCHING, stage="competitor_analysis")
    assert success is True
    updated = test_db.get_job(job.id)
    assert updated.state == JobState.RESEARCHING
    assert updated.current_stage == "competitor_analysis"

    # 4. Job locking
    lock_ok = test_db.acquire_job_lock(job.id, "worker-1")
    assert lock_ok is True
    # Second worker should fail to lock
    lock_fail = test_db.acquire_job_lock(job.id, "worker-2")
    assert lock_fail is False
    # Release lock
    release_ok = test_db.release_job_lock(job.id, "worker-1")
    assert release_ok is True


def test_database_crash_recovery(tmp_path: Path):
    db_file = tmp_path / "test_recovery.db"
    test_db = Database(db_path=db_file)

    # Create job and put into in-flight state
    job1 = test_db.create_job(title="Active Story Job")
    test_db.update_job_state(job1.id, JobState.SCRIPTING, stage="writing")

    # Create job in uploading state
    job2 = test_db.create_job(title="Uploading Job")
    test_db.update_job_state(job2.id, JobState.UPLOADING, stage="uploading")

    # Simulate crash and restart recovery
    recovered_count = test_db.recover_in_flight_jobs()
    assert recovered_count == 2

    # Verify states
    j1 = test_db.get_job(job1.id)
    assert j1.state == JobState.RETRYING

    j2 = test_db.get_job(job2.id)
    assert j2.state == JobState.NEEDS_REVIEW
