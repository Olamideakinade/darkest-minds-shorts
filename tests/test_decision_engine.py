"""Unit tests for the Autonomous Decision Engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.config import config
from app.database.db import Database
from app.database.models import Job, JobState, OpportunityAnalysis, OwnerChannelStatus
from app.intelligence.decision_engine import DecisionEngine


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        db_instance = Database(db_path=db_path)
        yield db_instance


def test_decision_engine_triggers_research_when_empty(test_db):
    engine = DecisionEngine(database=test_db)
    result = engine.select_next_story_opportunity()

    assert result.action_taken == "TRIGGER_RESEARCH"
    assert result.decision_type == "TOPIC_SELECTION"

    logs = test_db.get_decision_logs()
    assert len(logs) == 1
    assert logs[0].chosen_action == "TRIGGER_RESEARCH"


def test_decision_engine_selects_and_enqueues_best_candidate(test_db):
    # Seed opportunities
    opp1 = OpportunityAnalysis(
        topic="The Lost Amber Room of St. Petersburg",
        composite_score=85.0,
        confidence="HIGH",
        suggested_angle="Focus on the wartime train mystery",
    )
    opp2 = OpportunityAnalysis(
        topic="The 1911 Mona Lisa Heist",
        composite_score=70.0,
        confidence="MEDIUM",
        suggested_angle="Focus on the broom closet",
    )
    test_db.save_opportunity_analysis(opp1)
    test_db.save_opportunity_analysis(opp2)

    engine = DecisionEngine(database=test_db)
    result = engine.select_next_story_opportunity()

    assert "ENQUEUE_JOB" in result.action_taken
    assert result.job_id is not None
    assert result.details["topic"] == "The Lost Amber Room of St. Petersburg"

    # Verify Job created in DB
    job = test_db.get_job(result.job_id)
    assert job is not None
    assert job.title == "The Lost Amber Room of St. Petersburg"
    assert job.state == JobState.QUEUED

    # Verify decision log was persisted with explainable rationale
    logs = test_db.get_decision_logs()
    assert len(logs) == 1
    assert "Selected 'The Lost Amber Room of St. Petersburg'" in logs[0].rationale
    assert "The 1911 Mona Lisa Heist" in logs[0].rationale


def test_publishing_safety_evaluation(test_db):
    engine = DecisionEngine(database=test_db)
    job = test_db.create_job(title="Test Job")

    # 1. Default mode is 'disabled'
    can_pub, privacy, reason = engine.evaluate_publishing_safety(job)
    assert can_pub is False
    assert "disabled" in reason.lower()

    # 2. Test when channel is not connected in autonomous_public
    config.youtube_publish_mode = "autonomous_public"
    can_pub, privacy, reason = engine.evaluate_publishing_safety(job)
    assert can_pub is False
    assert "not connected" in reason.lower()

    # Reset config
    config.youtube_publish_mode = "disabled"
