"""Unit tests for the Autonomous Scheduler."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.database.db import Database
from app.scheduler.engine import AutonomousScheduler


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        db_instance = Database(db_path=db_path)
        yield db_instance


def test_scheduler_pause_and_resume(test_db):
    scheduler = AutonomousScheduler(database=test_db)
    state = scheduler.get_state()
    assert state.is_paused is False

    scheduler.pause(reason="Maintenance")
    state_after_pause = scheduler.get_state()
    assert state_after_pause.is_paused is True
    assert state_after_pause.pause_reason == "Maintenance"

    # Cycle should skip while paused
    result = scheduler.run_cycle()
    assert result["status"] == "PAUSED"

    scheduler.resume()
    state_after_resume = scheduler.get_state()
    assert state_after_resume.is_paused is False
    assert state_after_resume.pause_reason is None


def test_scheduler_run_cycle_executes(test_db):
    scheduler = AutonomousScheduler(database=test_db)
    result = scheduler.run_cycle()

    assert result["status"] == "SUCCESS"
    assert result["learning_updated"] is True

    # State in DB should have recorded execution timestamps
    state = scheduler.get_state()
    assert state.last_research_at is not None or state.last_production_at is not None
