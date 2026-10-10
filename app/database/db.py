"""Durable SQLite database connection and repository operations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
import uuid

from app.config import config
from app.database.migrations import apply_migrations
from app.database.models import (
    Job,
    JobState,
    StoryIdea,
    ScriptRecord,
    MediaAsset,
    QualityReport,
    PublishedVideo,
    SystemEvent,
    utc_now_iso,
)
from app.utils.logger import logger


class Database:
    """Encapsulates SQLite access with WAL mode and atomic transactions."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or config.db_path
        self._init_db()

    def _get_raw_connection(self) -> sqlite3.Connection:
        """Create and configure a raw SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Initialize database directory and run pending migrations."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            apply_migrations(conn)

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an auto-committing connection."""
        conn = self._get_raw_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction error: {e}")
            raise
        finally:
            conn.close()

    # --------------------------------------------------------------------------
    # Job Operations & State Machine Persistence
    # --------------------------------------------------------------------------

    def create_job(self, title: str, niche: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> Job:
        """Create and persist a new job in QUEUED state."""
        job = Job(
            title=title,
            niche=niche or config.niche_default,
            state=JobState.QUEUED,
            current_stage="queued",
            payload=payload or {},
        )
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, title, niche, state, current_stage, payload_json, error_message,
                                  retry_count, max_retries, lock_token, locked_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.title,
                    job.niche,
                    job.state.value,
                    job.current_stage,
                    json.dumps(job.payload),
                    job.error_message,
                    job.retry_count,
                    job.max_retries,
                    job.lock_token,
                    job.locked_at,
                    job.created_at,
                    job.updated_at,
                ),
            )
        self.record_event("JOB_CREATED", f"Job created: {job.title} ({job.id})", {"job_id": job.id})
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Fetch a job by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def update_job_state(
        self,
        job_id: str,
        state: JobState,
        stage: Optional[str] = None,
        error_message: Optional[str] = None,
        payload_updates: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Atomically update a job's lifecycle state and stage."""
        now = utc_now_iso()
        with self.connection() as conn:
            row = conn.execute("SELECT payload_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return False

            existing_payload = json.loads(row["payload_json"] or "{}")
            if payload_updates:
                existing_payload.update(payload_updates)

            conn.execute(
                """
                UPDATE jobs
                SET state = ?,
                    current_stage = COALESCE(?, current_stage),
                    error_message = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    state.value,
                    stage,
                    error_message,
                    json.dumps(existing_payload),
                    now,
                    job_id,
                ),
            )

        self.record_event(
            "JOB_STATE_CHANGE",
            f"Job {job_id} transitioned to {state.value} (stage: {stage or 'same'})",
            {"job_id": job_id, "state": state.value, "stage": stage, "error": error_message},
        )
        return True

    def acquire_job_lock(self, job_id: str, lock_token: str) -> bool:
        """Attempt to acquire a unique lock on a job to prevent duplicate execution."""
        now = utc_now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET lock_token = ?, locked_at = ?, updated_at = ?
                WHERE id = ? AND (lock_token IS NULL OR lock_token = ?)
                """,
                (lock_token, now, now, job_id, lock_token),
            )
            return cursor.rowcount > 0

    def release_job_lock(self, job_id: str, lock_token: str) -> bool:
        """Release a job lock."""
        now = utc_now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET lock_token = NULL, locked_at = NULL, updated_at = ?
                WHERE id = ? AND lock_token = ?
                """,
                (now, job_id, lock_token),
            )
            return cursor.rowcount > 0

    def get_next_queued_job(self) -> Optional[Job]:
        """Retrieve the oldest pending job that is ready for processing."""
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE state = ? AND lock_token IS NULL
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (JobState.QUEUED.value,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def list_jobs(self, limit: int = 50, state: Optional[JobState] = None) -> List[Job]:
        """List jobs ordered by most recently updated."""
        with self.connection() as conn:
            if state:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                    (state.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_job(r) for r in rows]

    def count_jobs_by_state(self) -> Dict[str, int]:
        """Count jobs grouped by state."""
        counts = {s.value: 0 for s in JobState}
        with self.connection() as conn:
            rows = conn.execute("SELECT state, COUNT(*) as cnt FROM jobs GROUP BY state").fetchall()
            for r in rows:
                counts[r["state"]] = r["cnt"]
        return counts

    def recover_in_flight_jobs(self) -> int:
        """Reset jobs left in-flight after an unexpected restart.

        Transitions in-flight active states to RETRYING or NEEDS_REVIEW
        to avoid ghost executions and prevent duplicate publishing.
        """
        in_flight_states = [
            JobState.RESEARCHING.value,
            JobState.SCRIPTING.value,
            JobState.NARRATING.value,
            JobState.ASSEMBLING.value,
            JobState.QA.value,
        ]
        placeholders = ",".join("?" for _ in in_flight_states)
        now = utc_now_iso()
        count = 0
        with self.connection() as conn:
            # Jobs in UPLOADING state must transition to NEEDS_REVIEW to prevent duplicate uploads
            cursor_upload = conn.execute(
                """
                UPDATE jobs
                SET state = ?, lock_token = NULL, locked_at = NULL,
                    error_message = 'Interrupted during upload. Flagged for review to avoid duplicate publishing.',
                    updated_at = ?
                WHERE state = ?
                """,
                (JobState.NEEDS_REVIEW.value, now, JobState.UPLOADING.value),
            )
            count += cursor_upload.rowcount

            # Other in-flight processing jobs transition to RETRYING
            cursor_other = conn.execute(
                f"""
                UPDATE jobs
                SET state = ?, lock_token = NULL, locked_at = NULL,
                    retry_count = retry_count + 1,
                    error_message = 'Process interrupted by application restart. Auto-recovered to RETRYING.',
                    updated_at = ?
                WHERE state IN ({placeholders})
                """,
                [JobState.RETRYING.value, now] + in_flight_states,
            )
            count += cursor_other.rowcount

        if count > 0:
            logger.warning(f"Crash recovery: safely recovered {count} in-flight jobs.")
            self.record_event("CRASH_RECOVERY", f"Safely recovered {count} in-flight jobs on startup.")
        return count

    # --------------------------------------------------------------------------
    # Subsystem Records Persistence
    # --------------------------------------------------------------------------

    def save_story_idea(self, idea: StoryIdea) -> None:
        """Save a generated story concept."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO story_ideas (id, job_id, topic, angle, score, rationale, source_urls_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idea.id,
                    idea.job_id,
                    idea.topic,
                    idea.angle,
                    idea.score,
                    idea.rationale,
                    json.dumps(idea.source_urls),
                    idea.status,
                    idea.created_at,
                ),
            )

    def save_script(self, script: ScriptRecord) -> None:
        """Save a generated script with hook, body, payoff, and factual verification status."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scripts (id, job_id, idea_id, hook_text, body_text, payoff_text,
                                                full_text, word_count, estimated_duration_sec,
                                                factual_verification_status, factual_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    script.id,
                    script.job_id,
                    script.idea_id,
                    script.hook_text,
                    script.body_text,
                    script.payoff_text,
                    script.full_text,
                    script.word_count,
                    script.estimated_duration_sec,
                    script.factual_verification_status,
                    script.factual_notes,
                    script.created_at,
                ),
            )

    def save_quality_report(self, report: QualityReport) -> None:
        """Save QA verification findings."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO quality_reports (id, job_id, status, checks_json, issues_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.job_id,
                    report.status,
                    json.dumps(report.checks),
                    json.dumps(report.issues),
                    report.created_at,
                ),
            )

    def save_published_video(self, record: PublishedVideo) -> None:
        """Save published video identifier and URL."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO published_videos (video_id, job_id, youtube_id, title, description,
                                                         privacy_status, youtube_url, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.video_id,
                    record.job_id,
                    record.youtube_id,
                    record.title,
                    record.description,
                    record.privacy_status,
                    record.youtube_url,
                    record.published_at,
                ),
            )

    def record_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None, level: str = "INFO") -> None:
        """Log structured system event into SQLite database."""
        event = SystemEvent(
            event_type=event_type,
            level=level,
            message=message,
            details=details or {},
        )
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO system_events (id, event_type, level, message, details_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.event_type,
                        event.level,
                        event.message,
                        json.dumps(event.details),
                        event.created_at,
                    ),
                )
        except Exception as e:
            logger.debug(f"Failed to record system event to DB: {e}")

    # --------------------------------------------------------------------------
    # Helper Serialization
    # --------------------------------------------------------------------------

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        payload = {}
        if row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}

        return Job(
            id=row["id"],
            title=row["title"],
            niche=row["niche"],
            state=JobState(row["state"]),
            current_stage=row["current_stage"],
            payload=payload,
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            lock_token=row["lock_token"],
            locked_at=row["locked_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# Global Database instance
db = Database()
