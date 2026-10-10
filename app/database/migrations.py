"""Database schema migrations and initialization for SQLite."""

from __future__ import annotations

import sqlite3
from app.utils.logger import logger

SCHEMA_VERSION = 4

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
    created_at TEXT NOT NULL
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

MIGRATION_V2_SQL = """
-- Historical Observations Table for Trend & Velocity Tracking
CREATE TABLE IF NOT EXISTS video_observations (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    view_count INTEGER NOT NULL,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    observed_at TEXT NOT NULL,
    search_query TEXT DEFAULT '',
    discovery_source TEXT DEFAULT 'keyword_search'
);
CREATE INDEX IF NOT EXISTS idx_observations_video_time ON video_observations(video_id, observed_at);

CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON video_observations(observed_at);
CREATE INDEX IF NOT EXISTS idx_observations_channel ON video_observations(channel_id);

-- API Response Cache Table (Saves Quota, Prevents Redundant Network Hits)
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache(expires_at);

-- Daily API Quota Tracking Table
CREATE TABLE IF NOT EXISTS api_quota_usage (
    date_utc TEXT PRIMARY KEY,
    units_used INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL
);

-- Opportunity Analyses Table
CREATE TABLE IF NOT EXISTS opportunity_analyses (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    primary_video_id TEXT,
    related_video_ids_json TEXT DEFAULT '[]',
    composite_score REAL NOT NULL,
    confidence TEXT NOT NULL,
    signals_json TEXT NOT NULL DEFAULT '{}',
    supporting_observations_json TEXT NOT NULL DEFAULT '[]',
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    failure_risks_json TEXT NOT NULL DEFAULT '[]',
    suggested_angle TEXT NOT NULL,
    factual_verification_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunity_analyses(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_created ON opportunity_analyses(created_at);

-- Authenticated Owner Channel State (Completely decoupled from public competitor research)
CREATE TABLE IF NOT EXISTS owner_channel (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    channel_id TEXT NOT NULL,
    title TEXT NOT NULL,
    custom_url TEXT DEFAULT '',
    subscriber_count INTEGER DEFAULT 0,
    video_count INTEGER DEFAULT 0,
    scopes_authorized_json TEXT DEFAULT '[]',
    is_connected INTEGER DEFAULT 0,
    connected_at TEXT,
    last_verified_at TEXT
);
"""



MIGRATION_V3_SQL = """
-- Autonomous Decision Logs Table (Complete audit trail of AI agent decisions)
CREATE TABLE IF NOT EXISTS decision_logs (
    id TEXT PRIMARY KEY,
    decision_type TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    chosen_action TEXT NOT NULL,
    rationale TEXT NOT NULL,
    outcome TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_logs_type ON decision_logs(decision_type);
CREATE INDEX IF NOT EXISTS idx_decision_logs_created ON decision_logs(created_at);

-- Content Strategy Metadata Table for Measurable Feedback Loops
CREATE TABLE IF NOT EXISTS content_strategies (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    script_id TEXT,
    category TEXT NOT NULL,
    hook_style TEXT NOT NULL,
    target_duration_sec INTEGER NOT NULL,
    words_per_minute REAL DEFAULT 150.0,
    narrative_archetype TEXT NOT NULL,
    experiment_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_strategies_job ON content_strategies(job_id);

-- Dynamic Strategy Weights (Updated based on measured video performance)
CREATE TABLE IF NOT EXISTS active_strategy_weights (
    strategy_key TEXT PRIMARY KEY,
    weight REAL NOT NULL DEFAULT 1.0,
    performance_multiplier REAL NOT NULL DEFAULT 1.0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL
);

-- Persistent Scheduler State & Health Lock
CREATE TABLE IF NOT EXISTS scheduler_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_research_at TEXT,
    last_production_at TEXT,
    last_analytics_at TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    is_paused INTEGER DEFAULT 0,
    pause_reason TEXT,
    updated_at TEXT NOT NULL
);

-- Factual Claims Verification Table
CREATE TABLE IF NOT EXISTS factual_claims (
    id TEXT PRIMARY KEY,
    script_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    sources_checked_json TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    is_flagged INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_factual_claims_script ON factual_claims(script_id);
"""


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply database migrations up to current SCHEMA_VERSION."""
    cursor = conn.cursor()
    from datetime import datetime, timezone

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
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, ?)", (now_iso,))
        conn.commit()
        current_version = 1
        logger.info("Database migration V1 applied successfully.")

    if current_version < 2:
        logger.info(f"Applying database schema migration V2 (current: {current_version})...")
        cursor.executescript(MIGRATION_V2_SQL)
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (2, ?)", (now_iso,))
        conn.commit()
        current_version = 2
        logger.info("Database migration V2 applied successfully.")

    if current_version < 3:
        logger.info(f"Applying database schema migration V3 (current: {current_version})...")
        cursor.executescript(MIGRATION_V3_SQL)
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (3, ?)", (now_iso,))
        conn.commit()
        current_version = 3
        logger.info("Database migration V3 applied successfully.")

    if current_version < 4:
        logger.info(f"Applying database schema migration V4 (current: {current_version})...")
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS factual_claims (
                id TEXT PRIMARY KEY,
                script_id TEXT NOT NULL,
                claim_text TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                sources_checked_json TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                is_flagged INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_factual_claims_script ON factual_claims(script_id);
            """
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (4, ?)", (now_iso,))
        conn.commit()
        logger.info("Database migration V4 applied successfully.")
    else:
        logger.debug(f"Database schema is already at version {current_version}.")

