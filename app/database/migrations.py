"""Database schema migrations and initialization for SQLite."""

from __future__ import annotations

import sqlite3
from app.utils.logger import logger

SCHEMA_VERSION = 1

MIGRATION_V1_SQL = """
-- Schema Version Table
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Core Jobs Table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    niche TEXT NOT NULL,
    state TEXT NOT NULL,
    current_stage TEXT NOT NULL DEFAULT 'init',
    payload_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    lock_token TEXT,
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);

-- Competitor Channels Table
CREATE TABLE IF NOT EXISTS competitor_channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    subscriber_count INTEGER DEFAULT 0,
    total_videos INTEGER DEFAULT 0,
    tracked_since TEXT NOT NULL,
    last_analyzed_at TEXT
);

-- Researched Videos Table
CREATE TABLE IF NOT EXISTS researched_videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT NOT NULL,
    duration_sec INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    estimated_vph REAL DEFAULT 0.0,
    topic_tags_json TEXT DEFAULT '[]',
    hook_summary TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (channel_id) REFERENCES competitor_channels(channel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_researched_channel ON researched_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_researched_published ON researched_videos(published_at);

-- Story Ideas Table
CREATE TABLE IF NOT EXISTS story_ideas (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    topic TEXT NOT NULL,
    angle TEXT NOT NULL,
    score REAL DEFAULT 0.0,
    rationale TEXT NOT NULL,
    source_urls_json TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_story_ideas_status ON story_ideas(status);

-- Scripts Table
CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    idea_id TEXT,
    hook_text TEXT NOT NULL,
    body_text TEXT NOT NULL,
    payoff_text TEXT NOT NULL,
    full_text TEXT NOT NULL,
    word_count INTEGER DEFAULT 0,
    estimated_duration_sec REAL DEFAULT 0.0,
    factual_verification_status TEXT DEFAULT 'UNVERIFIED',
    factual_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (idea_id) REFERENCES story_ideas(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_scripts_job ON scripts(job_id);

-- Media Assets Table
CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    duration_sec REAL DEFAULT 0.0,
    license_info TEXT DEFAULT 'Original / CC0',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_assets_job ON media_assets(job_id);

-- Quality Reports Table
CREATE TABLE IF NOT EXISTS quality_reports (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    checks_json TEXT DEFAULT '{}',
    issues_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qa_job ON quality_reports(job_id);

-- Published Videos Table
CREATE TABLE IF NOT EXISTS published_videos (
    video_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    youtube_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    privacy_status TEXT NOT NULL DEFAULT 'private',
    youtube_url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_published_youtube_id ON published_videos(youtube_id);

-- Analytics Snapshots Table
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id TEXT PRIMARY KEY,
    youtube_id TEXT NOT NULL,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    watch_time_sec REAL DEFAULT 0.0,
    average_view_duration_sec REAL DEFAULT 0.0,
    retention_pct REAL DEFAULT 0.0,
    subscribers_gained INTEGER DEFAULT 0,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (youtube_id) REFERENCES published_videos(youtube_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_analytics_yt_time ON analytics_snapshots(youtube_id, recorded_at);

-- Strategy Experiments Table
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    variable_name TEXT NOT NULL,
    variant_value TEXT NOT NULL,
    outcome_metric TEXT DEFAULT '',
    outcome_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- System Events Log Table
CREATE TABLE IF NOT EXISTS system_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_created ON system_events(created_at);
"""


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply database migrations up to current SCHEMA_VERSION."""
    cursor = conn.cursor()

    # Create version table if needed
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    cursor.execute("SELECT MAX(version) FROM schema_version")
    row = cursor.fetchone()
    current_version = row[0] if row and row[0] is not None else 0

    if current_version < 1:
        logger.info(f"Applying database schema migration V1 (current: {current_version})...")
        cursor.executescript(MIGRATION_V1_SQL)
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, ?)", (now_iso,))
        conn.commit()
        logger.info("Database migration V1 applied successfully.")
    else:
        logger.debug(f"Database schema is already at version {current_version}.")
