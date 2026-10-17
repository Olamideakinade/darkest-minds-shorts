"""Data models and schemas for Mhide Story Intelligence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


def utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class JobState(str, Enum):
    """Explicit job lifecycle states adhering to Stage 10 pipeline specification."""
    QUEUED = "QUEUED"
    RESEARCHING = "RESEARCHING"
    SCRIPTING = "SCRIPTING"
    GENERATING_ASSETS = "GENERATING_ASSETS"
    EDITING = "EDITING"
    RENDERING = "RENDERING"
    QUALITY_CHECK = "QUALITY_CHECK"
    READY_TO_SCHEDULE = "READY_TO_SCHEDULE"
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"

    # Backward compatibility states
    NARRATING = "NARRATING"
    ASSEMBLING = "ASSEMBLING"
    QA = "QA"
    READY = "READY"
    UPLOADING = "UPLOADING"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class Job:
    """Core production job record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    niche: str = "Unsolved Mysteries & Strange Disappearances"
    state: JobState = JobState.QUEUED
    current_stage: str = "init"
    payload: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    lock_token: Optional[str] = None
    locked_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value if isinstance(self.state, JobState) else self.state
        return d


@dataclass
class CompetitorChannel:
    channel_id: str
    title: str
    subscriber_count: int = 0
    total_videos: int = 0
    tracked_since: str = field(default_factory=utc_now_iso)
    last_analyzed_at: Optional[str] = None


@dataclass
class ResearchedVideo:
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    published_at: str
    duration_sec: int = 0
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    estimated_vph: float = 0.0
    topic_tags: List[str] = field(default_factory=list)
    hook_summary: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class StoryIdea:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: Optional[str] = None
    topic: str = ""
    angle: str = ""
    score: float = 0.0
    rationale: str = ""
    source_urls: List[str] = field(default_factory=list)
    status: str = "CANDIDATE"  # CANDIDATE, APPROVED, REJECTED, PRODUCED
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ScriptRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    idea_id: Optional[str] = None
    hook_text: str = ""
    body_text: str = ""
    payoff_text: str = ""
    full_text: str = ""
    word_count: int = 0
    estimated_duration_sec: float = 0.0
    factual_verification_status: str = "UNVERIFIED"  # UNVERIFIED, VERIFIED, SPECULATIVE
    factual_notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class MediaAsset:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    asset_type: str = "video"  # audio, video, image, subtitle, music
    file_path: str = ""
    duration_sec: float = 0.0
    license_info: str = "Original / CC0"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class QualityReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    status: str = "PASS"  # PASS, WARNING, FAIL
    checks: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class PublishedVideo:
    video_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    youtube_id: str = ""
    title: str = ""
    description: str = ""
    privacy_status: str = "private"
    youtube_url: str = ""
    published_at: str = field(default_factory=utc_now_iso)


@dataclass
class AnalyticsSnapshot:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    youtube_id: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    watch_time_sec: float = 0.0
    average_view_duration_sec: float = 0.0
    retention_pct: float = 0.0
    subscribers_gained: int = 0
    recorded_at: str = field(default_factory=utc_now_iso)


@dataclass
class Experiment:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    hypothesis: str = ""
    variable_name: str = ""
    variant_value: str = ""
    outcome_metric: str = ""
    outcome_notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class SystemEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = "INFO"
    level: str = "INFO"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class VideoObservation:
    """Historical point-in-time observation of a YouTube video."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    video_id: str = ""
    channel_id: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    observed_at: str = field(default_factory=utc_now_iso)
    search_query: str = ""
    discovery_source: str = "keyword_search"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApiCacheEntry:
    """Cached response from YouTube API to protect quotas."""
    cache_key: str
    endpoint: str
    response_json: str
    created_at: str = field(default_factory=utc_now_iso)
    expires_at: str = field(default_factory=utc_now_iso)


@dataclass
class ApiQuotaRecord:
    """Daily YouTube API quota usage record."""
    date_utc: str
    units_used: int = 0
    request_count: int = 0
    last_updated: str = field(default_factory=utc_now_iso)


@dataclass
class OpportunityAnalysis:
    """Scored storytelling opportunity with transparent evidence."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    primary_video_id: Optional[str] = None
    related_video_ids: List[str] = field(default_factory=list)
    composite_score: float = 0.0
    confidence: str = "LOW"  # HIGH, MEDIUM, LOW
    signals: Dict[str, float] = field(default_factory=dict)
    supporting_observations: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    failure_risks: List[str] = field(default_factory=list)
    suggested_angle: str = ""
    factual_verification_notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OwnerChannelStatus:
    """Status and identity of the owner's authenticated YouTube channel."""
    channel_id: str = ""
    title: str = ""
    custom_url: str = ""
    subscriber_count: int = 0
    video_count: int = 0
    scopes_authorized: List[str] = field(default_factory=list)
    is_connected: bool = False
    connected_at: Optional[str] = None
    last_verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionLog:
    """Durable audit trail of AI agent autonomous decisions."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision_type: str = "TOPIC_SELECTION"  # TOPIC_SELECTION, PUBLISHING, PAUSE, STRATEGY_ADAPTATION
    input_summary: str = ""
    chosen_action: str = ""
    rationale: str = ""
    outcome: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContentStrategy:
    """Content strategy metadata for empirical learning and feedback loops."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    script_id: Optional[str] = None
    category: str = "strange_history"  # strange_history, unsolved_mystery, real_curiosity
    hook_style: str = "curiosity_gap"   # curiosity_gap, contradictory_fact, historical_anomaly
    target_duration_sec: int = 45
    words_per_minute: float = 150.0
    narrative_archetype: str = "escalating_revelation"  # escalating_revelation, ironclad_puzzle, lost_relic
    experiment_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyWeight:
    """Empirical weight dynamically updated based on video performance at comparable age."""
    strategy_key: str = ""
    weight: float = 1.0
    performance_multiplier: float = 1.0
    sample_count: int = 0
    last_updated: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SchedulerState:
    """Persistent scheduler heartbeat and health state."""
    id: int = 1
    last_research_at: Optional[str] = None
    last_production_at: Optional[str] = None
    last_analytics_at: Optional[str] = None
    consecutive_failures: int = 0
    is_paused: bool = False
    pause_reason: Optional[str] = None
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactualClaim:
    """Individual factual assertion extracted from a script for verification."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    script_id: str = ""
    claim_text: str = ""
    verification_status: str = "UNVERIFIED"  # VERIFIED, UNSUPPORTED, CONFLICTED, FAILED, SPECULATIVE
    sources_checked: List[str] = field(default_factory=list)
    source_url: str = ""
    source_title: str = ""
    evidence_passage: str = ""
    conflicting_evidence: str = ""
    notes: str = ""
    is_flagged: bool = False
    retrieval_timestamp: str = field(default_factory=utc_now_iso)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)



