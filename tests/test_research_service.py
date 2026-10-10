"""Unit tests for ResearchService, data persistence, deduplication, and reports."""

from pathlib import Path
from unittest.mock import MagicMock

from app.database.db import Database
from app.database.models import CompetitorChannel, OwnerChannelStatus
from app.research.service import ResearchService
from app.research.youtube_client import YouTubeResearchClient


def test_research_service_offline_demo_mode(tmp_path: Path):
    test_db = Database(db_path=tmp_path / "res_service.db")

    import app.research.service as rs_mod
    original_db = rs_mod.db
    rs_mod.db = test_db

    try:
        unconfigured_client = YouTubeResearchClient(api_key="")
        service = ResearchService(api_client=unconfigured_client)

        result = service.run_research(query="strange history", max_videos=5, use_demo_if_unconfigured=True)

        assert result["success"] is True
        assert result["is_demo_mode"] is True  # Honestly labels as demo data
        assert len(result["videos"]) > 0
        assert len(result["opportunities"]) > 0
        assert "METHODOLOGY & SAFETY NOTICE" in result["report_text"]

        # Verify records persisted in database
        saved_videos = test_db.get_researched_videos()
        assert len(saved_videos) == len(result["videos"])

        saved_opps = test_db.list_opportunity_analyses()
        assert len(saved_opps) == len(result["opportunities"])
    finally:
        rs_mod.db = original_db


def test_research_service_deduplication(tmp_path: Path):
    test_db = Database(db_path=tmp_path / "dedup.db")

    import app.research.service as rs_mod
    original_db = rs_mod.db
    rs_mod.db = test_db

    try:
        service = ResearchService(api_client=YouTubeResearchClient(api_key=""))

        # Run twice
        service.run_research(query="strange history", use_demo_if_unconfigured=True)
        count_first = len(test_db.get_researched_videos())

        service.run_research(query="strange history", use_demo_if_unconfigured=True)
        count_second = len(test_db.get_researched_videos())

        # Video count must not duplicate on re-run
        assert count_first == count_second

        # But observation snapshots should have incremented for velocity tracking
        observations = test_db.get_video_observations("demo_vid_001")
        assert len(observations) == 2
    finally:
        rs_mod.db = original_db


def test_owner_channel_decoupled_from_research(tmp_path: Path):
    test_db = Database(db_path=tmp_path / "owner_decoupled.db")

    # Set owner channel status
    status = OwnerChannelStatus(
        channel_id="UC_OWNER_123",
        title="Owner Real Channel",
        custom_url="@ownerstories",
        subscriber_count=2500,
        video_count=18,
        scopes_authorized=["https://www.googleapis.com/auth/youtube.readonly"],
        is_connected=True,
    )
    test_db.set_owner_channel_status(status)

    retrieved = test_db.get_owner_channel_status()
    assert retrieved.is_connected is True
    assert retrieved.title == "Owner Real Channel"
    assert retrieved.channel_id == "UC_OWNER_123"

    # Verify that research queries and public observations do not alter owner channel table
    obs = test_db.get_video_observations("any_vid")
    assert obs == []

    # Disconnect channel locally
    test_db.clear_owner_channel_status()
    cleared = test_db.get_owner_channel_status()
    assert cleared.is_connected is False
