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
    VideoObservation,
    ApiCacheEntry,
    ApiQuotaRecord,
    OpportunityAnalysis,
    OwnerChannelStatus,
    ResearchedVideo,
    CompetitorChannel,
    DecisionLog,
    ContentStrategy,
    StrategyWeight,
    SchedulerState,
    FactualClaim,
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
        increment_retry: bool = False,
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

            retry_sql = ", retry_count = retry_count + 1" if increment_retry else ""
            conn.execute(
                f"""
                UPDATE jobs
                SET state = ?,
                    current_stage = COALESCE(?, current_stage),
                    error_message = ?,
                    payload_json = ?,
                    updated_at = ?
                    {retry_sql}
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
            JobState.GENERATING_ASSETS.value,
            JobState.EDITING.value,
            JobState.RENDERING.value,
            JobState.QUALITY_CHECK.value,
            JobState.NARRATING.value,
            JobState.ASSEMBLING.value,
            JobState.QA.value,
        ]
        placeholders = ",".join("?" for _ in in_flight_states)
        now = utc_now_iso()
        count = 0
        with self.connection() as conn:
            # Jobs in UPLOADING or PUBLISHING state must transition to REVIEW_REQUIRED to prevent duplicate uploads
            cursor_upload = conn.execute(
                """
                UPDATE jobs
                SET state = ?, lock_token = NULL, locked_at = NULL,
                    error_message = 'Interrupted during publish/upload. Flagged for review to reconcile with remote platforms and avoid duplicate publishing.',
                    updated_at = ?
                WHERE state IN (?, ?)
                """,
                (JobState.REVIEW_REQUIRED.value, now, JobState.UPLOADING.value, JobState.PUBLISHING.value),
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
    # Phase 2: YouTube Research, Observations, Caching, and Quota Management
    # --------------------------------------------------------------------------

    def save_researched_video(self, video: ResearchedVideo) -> None:
        """Upsert a researched video metadata record."""
        now = utc_now_iso()
        with self.connection() as conn:
            # Ensure channel exists in competitor_channels to satisfy foreign key in any migration state
            conn.execute(
                """
                INSERT OR IGNORE INTO competitor_channels (channel_id, title, tracked_since)
                VALUES (?, ?, ?)
                """,
                (video.channel_id, video.channel_title or "Discovered Channel", now),
            )
            conn.execute(
                """
                INSERT INTO researched_videos (video_id, channel_id, channel_title, title, published_at,
                                               duration_sec, view_count, like_count, comment_count,
                                               estimated_vph, topic_tags_json, hook_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    view_count = excluded.view_count,
                    like_count = excluded.like_count,
                    comment_count = excluded.comment_count,
                    estimated_vph = excluded.estimated_vph
                """,
                (
                    video.video_id,
                    video.channel_id,
                    video.channel_title,
                    video.title,
                    video.published_at,
                    video.duration_sec,
                    video.view_count,
                    video.like_count,
                    video.comment_count,
                    video.estimated_vph,
                    json.dumps(video.topic_tags),
                    video.hook_summary,
                    video.created_at,
                ),
            )

    def get_researched_video(self, video_id: str) -> Optional[ResearchedVideo]:
        """Fetch a researched video by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM researched_videos WHERE video_id = ?", (video_id,)).fetchone()
            if not row:
                return None
            return self._row_to_researched_video(row)

    def get_researched_videos(self, limit: int = 50) -> List[ResearchedVideo]:
        """List recently researched videos."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM researched_videos ORDER BY published_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_researched_video(r) for r in rows]

    def get_channel_videos(self, channel_id: str) -> List[ResearchedVideo]:
        """Fetch all researched videos from a specific channel."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM researched_videos WHERE channel_id = ? ORDER BY published_at DESC",
                (channel_id,),
            ).fetchall()
            return [self._row_to_researched_video(r) for r in rows]

    def record_observation(self, obs: VideoObservation) -> None:
        """Store a point-in-time snapshot of video metrics."""
        now = utc_now_iso()
        with self.connection() as conn:
            # Ensure parent records exist to satisfy foreign keys in any migration state
            conn.execute(
                """
                INSERT OR IGNORE INTO competitor_channels (channel_id, title, tracked_since)
                VALUES (?, ?, ?)
                """,
                (obs.channel_id, "Discovered Channel", now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO researched_videos (video_id, channel_id, channel_title, title, published_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (obs.video_id, obs.channel_id, "Discovered Channel", obs.video_id, obs.observed_at, now),
            )
            conn.execute(
                """
                INSERT INTO video_observations (id, video_id, channel_id, view_count, like_count,
                                                comment_count, observed_at, search_query, discovery_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.id,
                    obs.video_id,
                    obs.channel_id,
                    obs.view_count,
                    obs.like_count,
                    obs.comment_count,
                    obs.observed_at,
                    obs.search_query,
                    obs.discovery_source,
                ),
            )


    def get_video_observations(self, video_id: str) -> List[VideoObservation]:
        """Retrieve chronological observations for a video to calculate real velocity."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_observations WHERE video_id = ? ORDER BY observed_at ASC",
                (video_id,),
            ).fetchall()
            return [
                VideoObservation(
                    id=r["id"],
                    video_id=r["video_id"],
                    channel_id=r["channel_id"],
                    view_count=r["view_count"],
                    like_count=r["like_count"],
                    comment_count=r["comment_count"],
                    observed_at=r["observed_at"],
                    search_query=r["search_query"],
                    discovery_source=r["discovery_source"],
                )
                for r in rows
            ]

    # --- API Response Caching (Zero-Cost & Quota Protection) ---

    def get_cached_api_response(self, cache_key: str) -> Optional[str]:
        """Fetch cached API response if not expired."""
        now = utc_now_iso()
        with self.connection() as conn:
            row = conn.execute(
                "SELECT response_json FROM api_cache WHERE cache_key = ? AND expires_at > ?",
                (cache_key, now),
            ).fetchone()
            if row:
                return row["response_json"]
        return None

    def set_cached_api_response(self, cache_key: str, endpoint: str, response_json: str, ttl_hours: int = 6) -> None:
        """Cache an API response with TTL in hours."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        now_iso = now.isoformat()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO api_cache (cache_key, endpoint, response_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cache_key, endpoint, response_json, now_iso, expires_at),
            )

    # --- Daily Quota Usage Tracking ---

    def record_quota_usage(self, units: int = 1) -> None:
        """Track YouTube API quota units consumed today."""
        from datetime import datetime, timezone
        date_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO api_quota_usage (date_utc, units_used, request_count, last_updated)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(date_utc) DO UPDATE SET
                    units_used = units_used + excluded.units_used,
                    request_count = request_count + 1,
                    last_updated = excluded.last_updated
                """,
                (date_today, units, now_iso),
            )

    def get_today_quota_usage(self) -> Dict[str, Any]:
        """Retrieve estimated quota units and request counts used today."""
        from datetime import datetime, timezone
        date_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM api_quota_usage WHERE date_utc = ?",
                (date_today,),
            ).fetchone()
            if row:
                return {
                    "date_utc": row["date_utc"],
                    "units_used": row["units_used"],
                    "request_count": row["request_count"],
                    "last_updated": row["last_updated"],
                }
        return {"date_utc": date_today, "units_used": 0, "request_count": 0, "last_updated": utc_now_iso()}

    # --- Opportunity Analyses Persistence ---

    def save_opportunity_analysis(self, analysis: OpportunityAnalysis) -> None:
        """Store a scored storytelling opportunity with transparent evidence."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opportunity_analyses (
                    id, topic, primary_video_id, related_video_ids_json, composite_score,
                    confidence, signals_json, supporting_observations_json, missing_evidence_json,
                    failure_risks_json, suggested_angle, factual_verification_notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.id,
                    analysis.topic,
                    analysis.primary_video_id,
                    json.dumps(analysis.related_video_ids),
                    analysis.composite_score,
                    analysis.confidence,
                    json.dumps(analysis.signals),
                    json.dumps(analysis.supporting_observations),
                    json.dumps(analysis.missing_evidence),
                    json.dumps(analysis.failure_risks),
                    analysis.suggested_angle,
                    analysis.factual_verification_notes,
                    analysis.created_at,
                ),
            )

    def list_opportunity_analyses(self, limit: int = 20) -> List[OpportunityAnalysis]:
        """Fetch ranked opportunity analyses."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunity_analyses ORDER BY composite_score DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_opportunity_analysis(r) for r in rows]

    # --- Competitor Channels Management ---

    def add_competitor_channel(self, channel: CompetitorChannel) -> None:
        """Register a competitor channel to track."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO competitor_channels (channel_id, title, subscriber_count, total_videos, tracked_since, last_analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    channel.channel_id,
                    channel.title,
                    channel.subscriber_count,
                    channel.total_videos,
                    channel.tracked_since,
                    channel.last_analyzed_at,
                ),
            )

    def list_competitor_channels(self) -> List[CompetitorChannel]:
        """Retrieve list of tracked competitor channels."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM competitor_channels ORDER BY tracked_since DESC").fetchall()
            return [
                CompetitorChannel(
                    channel_id=r["channel_id"],
                    title=r["title"],
                    subscriber_count=r["subscriber_count"],
                    total_videos=r["total_videos"],
                    tracked_since=r["tracked_since"],
                    last_analyzed_at=r["last_analyzed_at"],
                )
                for r in rows
            ]

    # --- Authenticated Owner Channel State Management ---

    def get_owner_channel_status(self) -> OwnerChannelStatus:
        """Retrieve connected owner channel status from persistent state."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM owner_channel WHERE id = 1").fetchone()
            if not row:
                return OwnerChannelStatus(is_connected=False)
            scopes = []
            if row["scopes_authorized_json"]:
                try:
                    scopes = json.loads(row["scopes_authorized_json"])
                except Exception:
                    scopes = []
            return OwnerChannelStatus(
                channel_id=row["channel_id"],
                title=row["title"],
                custom_url=row["custom_url"],
                subscriber_count=row["subscriber_count"],
                video_count=row["video_count"],
                scopes_authorized=scopes,
                is_connected=bool(row["is_connected"]),
                connected_at=row["connected_at"],
                last_verified_at=row["last_verified_at"],
            )

    def set_owner_channel_status(self, status: OwnerChannelStatus) -> None:
        """Persist or update authenticated owner channel status."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO owner_channel (id, channel_id, title, custom_url, subscriber_count,
                                           video_count, scopes_authorized_json, is_connected,
                                           connected_at, last_verified_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    title = excluded.title,
                    custom_url = excluded.custom_url,
                    subscriber_count = excluded.subscriber_count,
                    video_count = excluded.video_count,
                    scopes_authorized_json = excluded.scopes_authorized_json,
                    is_connected = excluded.is_connected,
                    connected_at = excluded.connected_at,
                    last_verified_at = excluded.last_verified_at
                """,
                (
                    status.channel_id,
                    status.title,
                    status.custom_url,
                    status.subscriber_count,
                    status.video_count,
                    json.dumps(status.scopes_authorized),
                    1 if status.is_connected else 0,
                    status.connected_at,
                    status.last_verified_at,
                ),
            )

    def clear_owner_channel_status(self) -> None:
        """Disconnect owner channel in local state without deleting any remote YouTube data."""
        with self.connection() as conn:
            conn.execute("DELETE FROM owner_channel WHERE id = 1")

    # --------------------------------------------------------------------------
    # Autonomous Operations: Decisions, Strategies, Scheduler & Claims
    # --------------------------------------------------------------------------

    def log_decision(self, decision: DecisionLog) -> None:
        """Record an autonomous decision to the durable audit trail."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO decision_logs (id, decision_type, input_summary, chosen_action, rationale, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.decision_type,
                    decision.input_summary,
                    decision.chosen_action,
                    decision.rationale,
                    decision.outcome,
                    decision.created_at,
                ),
            )
        self.record_event("DECISION_LOGGED", f"Decision [{decision.decision_type}]: {decision.chosen_action}", {
            "decision_id": decision.id,
            "decision_type": decision.decision_type,
        })

    def get_decision_logs(self, limit: int = 50, decision_type: Optional[str] = None) -> List[DecisionLog]:
        """Retrieve recent autonomous decision logs."""
        with self.connection() as conn:
            if decision_type:
                rows = conn.execute(
                    "SELECT * FROM decision_logs WHERE decision_type = ? ORDER BY created_at DESC LIMIT ?",
                    (decision_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM decision_logs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            DecisionLog(
                id=r["id"],
                decision_type=r["decision_type"],
                input_summary=r["input_summary"],
                chosen_action=r["chosen_action"],
                rationale=r["rationale"],
                outcome=r["outcome"] or "",
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def record_content_strategy(self, strategy: ContentStrategy) -> None:
        """Store the strategy metadata for a produced Short."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO content_strategies (id, job_id, script_id, category, hook_style,
                                                          target_duration_sec, words_per_minute, narrative_archetype,
                                                          experiment_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy.id,
                    strategy.job_id,
                    strategy.script_id,
                    strategy.category,
                    strategy.hook_style,
                    strategy.target_duration_sec,
                    strategy.words_per_minute,
                    strategy.narrative_archetype,
                    strategy.experiment_id,
                    strategy.created_at,
                ),
            )

    def get_content_strategy_for_job(self, job_id: str) -> Optional[ContentStrategy]:
        """Retrieve the strategy metadata associated with a specific job."""
        with self.connection() as conn:
            r = conn.execute("SELECT * FROM content_strategies WHERE job_id = ?", (job_id,)).fetchone()
            if not r:
                return None
            return ContentStrategy(
                id=r["id"],
                job_id=r["job_id"],
                script_id=r["script_id"],
                category=r["category"],
                hook_style=r["hook_style"],
                target_duration_sec=r["target_duration_sec"],
                words_per_minute=r["words_per_minute"],
                narrative_archetype=r["narrative_archetype"],
                experiment_id=r["experiment_id"],
                created_at=r["created_at"],
            )

    def list_content_strategies(self, limit: int = 50) -> List[ContentStrategy]:
        """List recent content strategies across jobs."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM content_strategies ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            ContentStrategy(
                id=r["id"],
                job_id=r["job_id"],
                script_id=r["script_id"],
                category=r["category"],
                hook_style=r["hook_style"],
                target_duration_sec=r["target_duration_sec"],
                words_per_minute=r["words_per_minute"],
                narrative_archetype=r["narrative_archetype"],
                experiment_id=r["experiment_id"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_strategy_weights(self) -> Dict[str, StrategyWeight]:
        """Get all active dynamic strategy weights."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM active_strategy_weights").fetchall()
        return {
            r["strategy_key"]: StrategyWeight(
                strategy_key=r["strategy_key"],
                weight=r["weight"],
                performance_multiplier=r["performance_multiplier"],
                sample_count=r["sample_count"],
                last_updated=r["last_updated"],
            )
            for r in rows
        }

    def update_strategy_weight(self, key: str, weight: float, performance_multiplier: float, sample_count: int) -> None:
        """Upsert dynamic strategy weight based on measured video performance."""
        now_iso = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO active_strategy_weights (strategy_key, weight, performance_multiplier, sample_count, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategy_key) DO UPDATE SET
                    weight = excluded.weight,
                    performance_multiplier = excluded.performance_multiplier,
                    sample_count = excluded.sample_count,
                    last_updated = excluded.last_updated
                """,
                (key, weight, performance_multiplier, sample_count, now_iso),
            )

    def get_scheduler_state(self) -> SchedulerState:
        """Fetch persistent scheduler state."""
        with self.connection() as conn:
            r = conn.execute("SELECT * FROM scheduler_state WHERE id = 1").fetchone()
            if not r:
                return SchedulerState()
            return SchedulerState(
                id=r["id"],
                last_research_at=r["last_research_at"],
                last_production_at=r["last_production_at"],
                last_analytics_at=r["last_analytics_at"],
                consecutive_failures=r["consecutive_failures"],
                is_paused=bool(r["is_paused"]),
                pause_reason=r["pause_reason"],
                updated_at=r["updated_at"],
            )

    def update_scheduler_state(self, state: SchedulerState) -> None:
        """Upsert persistent scheduler state."""
        now_iso = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_state (id, last_research_at, last_production_at, last_analytics_at,
                                            consecutive_failures, is_paused, pause_reason, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_research_at = excluded.last_research_at,
                    last_production_at = excluded.last_production_at,
                    last_analytics_at = excluded.last_analytics_at,
                    consecutive_failures = excluded.consecutive_failures,
                    is_paused = excluded.is_paused,
                    pause_reason = excluded.pause_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    state.last_research_at,
                    state.last_production_at,
                    state.last_analytics_at,
                    state.consecutive_failures,
                    1 if state.is_paused else 0,
                    state.pause_reason,
                    now_iso,
                ),
            )

    def get_published_videos(self, limit: int = 50) -> List[PublishedVideo]:
        """Fetch list of recorded published videos."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM published_videos ORDER BY published_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            PublishedVideo(
                video_id=r["video_id"],
                job_id=r["job_id"],
                youtube_id=r["youtube_id"],
                title=r["title"],
                description=r["description"] or "",
                privacy_status=r["privacy_status"] or "private",
                youtube_url=r["youtube_url"] or "",
                published_at=r["published_at"],
            )
            for r in rows
        ]

    def get_published_video_by_job(self, job_id: str) -> Optional[PublishedVideo]:
        """Find published video record by job ID."""
        with self.connection() as conn:
            r = conn.execute("SELECT * FROM published_videos WHERE job_id = ?", (job_id,)).fetchone()
            if not r:
                return None
            return PublishedVideo(
                video_id=r["video_id"],
                job_id=r["job_id"],
                youtube_id=r["youtube_id"],
                title=r["title"],
                description=r["description"] or "",
                privacy_status=r["privacy_status"] or "private",
                youtube_url=r["youtube_url"] or "",
                published_at=r["published_at"],
            )

    def record_factual_claim(self, claim: FactualClaim) -> None:
        """Store individual factual claim extracted from script."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO factual_claims (id, script_id, claim_text, verification_status,
                                                       sources_checked_json, notes, is_flagged, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.id,
                    claim.script_id,
                    claim.claim_text,
                    claim.verification_status,
                    json.dumps(claim.sources_checked),
                    claim.notes,
                    1 if claim.is_flagged else 0,
                    claim.created_at,
                ),
            )

    def get_factual_claims_for_script(self, script_id: str) -> List[FactualClaim]:
        """Retrieve all claims extracted for a specific script."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM factual_claims WHERE script_id = ? ORDER BY created_at ASC", (script_id,)
            ).fetchall()
        claims = []
        for r in rows:
            sources = []
            if r["sources_checked_json"]:
                try:
                    sources = json.loads(r["sources_checked_json"])
                except Exception:
                    sources = []
            claims.append(
                FactualClaim(
                    id=r["id"],
                    script_id=r["script_id"],
                    claim_text=r["claim_text"],
                    verification_status=r["verification_status"],
                    sources_checked=sources,
                    notes=r["notes"] or "",
                    is_flagged=bool(r["is_flagged"]),
                    created_at=r["created_at"],
                )
            )
        return claims

    def save_media_asset(self, asset: MediaAsset) -> None:
        """Record or update a media asset in the database."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO media_assets (id, job_id, asset_type, file_path, duration_sec, license_info, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.id,
                    asset.job_id,
                    asset.asset_type,
                    asset.file_path,
                    asset.duration_sec,
                    asset.license_info,
                    asset.created_at,
                ),
            )

    def get_media_assets_for_job(self, job_id: str) -> List[MediaAsset]:
        """Retrieve all recorded media assets for a job."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM media_assets WHERE job_id = ? ORDER BY created_at ASC",
                (job_id,),
            ).fetchall()
            return [
                MediaAsset(
                    id=row["id"],
                    job_id=row["job_id"],
                    asset_type=row["asset_type"],
                    file_path=row["file_path"],
                    duration_sec=row["duration_sec"],
                    license_info=row["license_info"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

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

    @staticmethod
    def _row_to_researched_video(row: sqlite3.Row) -> ResearchedVideo:
        tags = []
        if row["topic_tags_json"]:
            try:
                tags = json.loads(row["topic_tags_json"])
            except Exception:
                tags = []
        return ResearchedVideo(
            video_id=row["video_id"],
            channel_id=row["channel_id"],
            channel_title=row["channel_title"],
            title=row["title"],
            published_at=row["published_at"],
            duration_sec=row["duration_sec"],
            view_count=row["view_count"],
            like_count=row["like_count"],
            comment_count=row["comment_count"],
            estimated_vph=row["estimated_vph"],
            topic_tags=tags,
            hook_summary=row["hook_summary"] or "",
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_opportunity_analysis(row: sqlite3.Row) -> OpportunityAnalysis:
        related_ids = []
        signals = {}
        observations = []
        missing = []
        risks = []
        try:
            if row["related_video_ids_json"]:
                related_ids = json.loads(row["related_video_ids_json"])
            if row["signals_json"]:
                signals = json.loads(row["signals_json"])
            if row["supporting_observations_json"]:
                observations = json.loads(row["supporting_observations_json"])
            if row["missing_evidence_json"]:
                missing = json.loads(row["missing_evidence_json"])
            if row["failure_risks_json"]:
                risks = json.loads(row["failure_risks_json"])
        except Exception:
            pass

        return OpportunityAnalysis(
            id=row["id"],
            topic=row["topic"],
            primary_video_id=row["primary_video_id"],
            related_video_ids=related_ids,
            composite_score=row["composite_score"],
            confidence=row["confidence"],
            signals=signals,
            supporting_observations=observations,
            missing_evidence=missing,
            failure_risks=risks,
            suggested_angle=row["suggested_angle"],
            factual_verification_notes=row["factual_verification_notes"] or "",
            created_at=row["created_at"],
        )



# Global Database instance
db = Database()
