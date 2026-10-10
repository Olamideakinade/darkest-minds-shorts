"""Unit tests for the Empirical Learning Engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.analytics.learning_engine import LearningEngine
from app.database.db import Database
from app.database.models import ContentStrategy, PublishedVideo


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        db_instance = Database(db_path=db_path)
        yield db_instance


def test_learning_engine_with_insufficient_samples(test_db):
    engine = LearningEngine(database=test_db)
    result = engine.evaluate_and_adapt()
    assert result["status"] == "INSUFFICIENT_DATA"


def test_learning_engine_adapts_weights_from_cohort_performance(test_db):
    # Seed published videos and attached strategies
    job1 = test_db.create_job(title="Video 1")
    job2 = test_db.create_job(title="Video 2")

    pub1 = PublishedVideo(
        video_id="v1",
        job_id=job1.id,
        youtube_id="yt-1",
        title="High performer",
    )
    pub2 = PublishedVideo(
        video_id="v2",
        job_id=job2.id,
        youtube_id="yt-2",
        title="Lower performer",
    )
    test_db.save_published_video(pub1)
    test_db.save_published_video(pub2)

    strat1 = ContentStrategy(
        job_id=job1.id,
        category="strange_history",
        hook_style="contradictory_fact",
        narrative_archetype="escalating_revelation",
    )
    strat2 = ContentStrategy(
        job_id=job2.id,
        category="unsolved_mystery",
        hook_style="curiosity_gap",
        narrative_archetype="lost_relic",
    )
    test_db.record_content_strategy(strat1)
    test_db.record_content_strategy(strat2)

    # Seed analytics snapshots
    with test_db.connection() as conn:
        conn.execute(
            "INSERT INTO analytics_snapshots (id, youtube_id, views, likes, comments, recorded_at) VALUES ('s1', 'yt-1', 500, 50, 10, '2026-10-10T10:00:00')"
        )
        conn.execute(
            "INSERT INTO analytics_snapshots (id, youtube_id, views, likes, comments, recorded_at) VALUES ('s2', 'yt-2', 100, 10, 2, '2026-10-10T10:00:00')"
        )

    engine = LearningEngine(database=test_db)
    result = engine.evaluate_and_adapt()

    assert result["status"] == "UPDATED"
    assert result["evaluated_videos"] == 2
    assert result["cohort_average_views"] == 300.0

    weights = test_db.get_strategy_weights()
    # High performer's dimension should have multiplier > 1.0
    contradictory_weight = weights.get("hook_style:contradictory_fact")
    assert contradictory_weight is not None
    assert contradictory_weight.performance_multiplier > 1.0

    # Low performer's dimension should have multiplier < 1.0
    curiosity_weight = weights.get("hook_style:curiosity_gap")
    assert curiosity_weight is not None
    assert curiosity_weight.performance_multiplier < 1.0

    # Verify decision log was created
    logs = test_db.get_decision_logs(decision_type="STRATEGY_ADAPTATION")
    assert len(logs) == 1
    assert "Empirical feedback loop updated strategy weights" in logs[0].rationale
