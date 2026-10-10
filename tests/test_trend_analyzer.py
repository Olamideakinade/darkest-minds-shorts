"""Unit tests for trend intelligence, view velocity calculation, and channel baselines."""

from pathlib import Path
from app.database.db import Database
from app.database.models import ResearchedVideo, VideoObservation
from app.research.trend_analyzer import TrendAnalyzer


def test_view_velocity_with_multiple_observations(tmp_path: Path):
    test_db = Database(db_path=tmp_path / "velocity.db")
    video_id = "vid_velocity_01"

    # Observation 1: T0 with 10,000 views
    obs1 = VideoObservation(
        video_id=video_id,
        channel_id="chan_01",
        view_count=10000,
        observed_at="2026-10-01T10:00:00+00:00",
    )
    # Observation 2: 4 hours later with 18,000 views (+8,000 views over 4 hours = 2,000 views/hour)
    obs2 = VideoObservation(
        video_id=video_id,
        channel_id="chan_01",
        view_count=18000,
        observed_at="2026-10-01T14:00:00+00:00",
    )

    test_db.record_observation(obs1)
    test_db.record_observation(obs2)

    # Patch TrendAnalyzer's db reference
    import app.research.trend_analyzer as ta_mod
    original_db = ta_mod.db
    ta_mod.db = test_db
    try:
        metric = TrendAnalyzer.calculate_view_velocity(video_id)
        assert metric.has_multiple_observations is True
        assert metric.observation_count == 2
        assert metric.elapsed_hours == 4.0
        assert metric.hourly_velocity == 2000.0
        assert metric.daily_velocity == 48000.0
        assert "Estimated velocity" in metric.explanation
    finally:
        ta_mod.db = original_db


def test_view_velocity_with_single_observation(tmp_path: Path):
    test_db = Database(db_path=tmp_path / "velocity_single.db")
    video_id = "vid_single_01"

    obs = VideoObservation(
        video_id=video_id,
        channel_id="chan_01",
        view_count=50000,
        observed_at="2026-10-01T12:00:00+00:00",
    )
    test_db.record_observation(obs)

    import app.research.trend_analyzer as ta_mod
    original_db = ta_mod.db
    ta_mod.db = test_db
    try:
        metric = TrendAnalyzer.calculate_view_velocity(video_id)
        # MUST NOT invent a velocity value
        assert metric.hourly_velocity is None
        assert metric.daily_velocity is None
        assert metric.has_multiple_observations is False
        assert metric.observation_count == 1
        assert "unavailable" in metric.explanation.lower()
    finally:
        ta_mod.db = original_db


def test_channel_baseline_calculation(tmp_path: Path):
    test_db = Database(db_path=tmp_path / "baseline.db")
    channel_id = "chan_hist_01"

    # Add 3 videos for this channel: 10k, 20k, 30k (median = 20k)
    v1 = ResearchedVideo(video_id="v1", channel_id=channel_id, channel_title="Ch", title="T1", published_at="2026-09-01T00:00:00Z", view_count=10000)
    v2 = ResearchedVideo(video_id="v2", channel_id=channel_id, channel_title="Ch", title="T2", published_at="2026-09-02T00:00:00Z", view_count=20000)
    v3 = ResearchedVideo(video_id="v3", channel_id=channel_id, channel_title="Ch", title="T3", published_at="2026-09-03T00:00:00Z", view_count=30000)

    test_db.save_researched_video(v1)
    test_db.save_researched_video(v2)
    test_db.save_researched_video(v3)

    import app.research.trend_analyzer as ta_mod
    original_db = ta_mod.db
    ta_mod.db = test_db
    try:
        # A new video with 50,000 views should be 2.5x the 20k median
        baseline = TrendAnalyzer.calculate_channel_baseline(channel_id, current_video_views=50000)
        assert baseline.is_sufficient_sample is True
        assert baseline.sample_size == 3
        assert baseline.median_views == 20000.0
        assert baseline.performance_ratio == 2.5
        assert "Outperforming channel median" in baseline.explanation
    finally:
        ta_mod.db = original_db


def test_topic_momentum_cross_channel():
    v1 = ResearchedVideo(video_id="v1", channel_id="chan_A", channel_title="A", title="The Great Mona Lisa Heist", published_at="2026-09-01T00:00:00Z")
    v2 = ResearchedVideo(video_id="v2", channel_id="chan_B", channel_title="B", title="How Mona Lisa Was Stolen in 1911", published_at="2026-09-02T00:00:00Z")
    v3 = ResearchedVideo(video_id="v3", channel_id="chan_C", channel_title="C", title="Ancient Roman Concrete Mystery", published_at="2026-09-03T00:00:00Z")

    momentum = TrendAnalyzer.detect_topic_momentum("Mona Lisa Heist", [v1, v2, v3])
    assert momentum["has_cross_channel_momentum"] is True
    assert momentum["unique_channels_count"] >= 2
    assert "v1" in momentum["matching_video_ids"]
    assert "v2" in momentum["matching_video_ids"]
