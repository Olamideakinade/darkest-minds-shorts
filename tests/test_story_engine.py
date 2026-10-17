"""Unit tests for Phase 3 Storytelling Engine, Factual Verifier, and Validators."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.database.db import Database
from app.scripts.factual_verifier import FactualVerifier
from app.scripts.story_engine import StoryEngine
from app.scripts.story_models import StoryScript
from app.scripts.validators import ScriptValidator


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        db_instance = Database(db_path=db_path)
        yield db_instance


def test_script_validator_cliches():
    validator = ScriptValidator()
    script = StoryScript(
        hook_text="Did you know that in 1911 the Mona Lisa was stolen?",
        escalation_text="Wait until the end to find out who stole it. The truth is crazy.",
        payoff_text="Leave a comment below if you enjoyed this video.",
        full_narration="Did you know that in 1911 the Mona Lisa was stolen? Wait until the end to find out who stole it. Leave a comment below.",
    )
    is_valid, issues = validator.validate(script)
    assert is_valid is False
    assert any("did you know" in issue.lower() for issue in issues)
    assert any("wait until the end" in issue.lower() for issue in issues)


def test_factual_verifier_extracts_dates_and_figures():
    verifier = FactualVerifier()
    text = "In 1911, Vincenzo Peruggia stole the Mona Lisa from the Louvre in Paris."
    claims, status, notes = verifier.verify_script_claims("test-script-1", text, topic="Mona Lisa theft")

    assert status == "VERIFIED"
    assert len(claims) >= 2
    claim_texts = [c.claim_text for c in claims]
    assert any("1911" in t for t in claim_texts)
    assert any("Vincenzo Peruggia" in t or "Louvre" in t for t in claim_texts)


def test_factual_verifier_flags_speculative_assertions():
    verifier = FactualVerifier()
    text = "Ancient aliens built the monuments using secret time travel technology."
    claims, status, notes = verifier.verify_script_claims("test-script-2", text)

    assert status == "SPECULATIVE"
    assert any(c.is_flagged for c in claims)


def test_story_engine_generates_and_persists_script(test_db):
    engine = StoryEngine(database=test_db)
    job = test_db.create_job(
        title="The 1911 Louvre Heist",
        payload={"topic": "1911 Mona Lisa Heist", "category": "strange_history"},
    )
    story = engine.generate_story(job)

    assert story.hook_text != ""
    assert story.escalation_text != ""
    assert story.payoff_text != ""
    assert story.word_count > 40
    assert len(story.scenes) >= 3

    # Check database persistence
    with test_db.connection() as conn:
        row = conn.execute("SELECT * FROM scripts WHERE job_id = ?", (job.id,)).fetchone()
        assert row is not None
        assert row["hook_text"] == story.hook_text

    claims = test_db.get_factual_claims_for_script(story.id)
    assert isinstance(claims, list)
