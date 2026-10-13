"""Unit and integration tests for comprehensive YouTube OAuth scopes, channel management, and safety locks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from unittest.mock import MagicMock, patch
import pytest

from app.database.db import db
from app.database.models import OwnerChannelStatus
from app.youtube.channel_manager import (
    SCOPE_CAPABILITIES,
    YOUTUBE_MANAGEMENT_SCOPES,
    YOUTUBE_SCOPES,
    OwnerChannelManager,
)


@pytest.fixture
def temp_channel_manager(tmp_path: Path):
    """Create an isolated OwnerChannelManager with temporary credentials and tokens."""
    secrets_file = tmp_path / "credentials" / "client_secrets.json"
    secrets_file.parent.mkdir(parents=True, exist_ok=True)
    secrets_file.write_text(json.dumps({
        "installed": {
            "client_id": "test-client.apps.googleusercontent.com",
            "client_secret": "test-secret-value",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }))

    token_file = tmp_path / "data" / "youtube_token.json"
    token_file.parent.mkdir(parents=True, exist_ok=True)

    mgr = OwnerChannelManager(
        client_secrets_file=secrets_file,
        token_file=token_file,
    )
    return mgr


# -----------------------------------------------------------------------------
# 1. Scopes Definition & Verification Tests
# -----------------------------------------------------------------------------

def test_management_scopes_coverage():
    """Verify all official YouTube management, SSL, upload, and analytics scopes are defined."""
    expected_scopes = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    ]
    for sc in expected_scopes:
        assert sc in YOUTUBE_MANAGEMENT_SCOPES
        assert sc in SCOPE_CAPABILITIES
        assert len(SCOPE_CAPABILITIES[sc]) > 0


def test_scope_inspection_from_token(temp_channel_manager: OwnerChannelManager):
    """Verify that scopes are strictly parsed from the token file, avoiding false reporting."""
    # Case A: Token file does not exist
    assert temp_channel_manager.get_granted_scopes() == []
    assert temp_channel_manager.is_fully_scoped() is False
    assert len(temp_channel_manager.get_missing_scopes()) == len(YOUTUBE_MANAGEMENT_SCOPES)

    # Case B: Token file has partial scopes (e.g., legacy read/upload/analytics)
    legacy_scopes = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok-123",
        "scopes": legacy_scopes,
    }))

    granted = temp_channel_manager.get_granted_scopes()
    assert granted == legacy_scopes
    assert temp_channel_manager.has_scope("https://www.googleapis.com/auth/youtube.upload") is True
    assert temp_channel_manager.has_scope("https://www.googleapis.com/auth/youtube") is False
    assert temp_channel_manager.is_fully_scoped() is False

    missing = temp_channel_manager.get_missing_scopes()
    assert "https://www.googleapis.com/auth/youtube" in missing
    assert "https://www.googleapis.com/auth/youtube.force-ssl" in missing

    # Case C: Fully scoped token
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok-full",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    }))
    assert temp_channel_manager.is_fully_scoped() is True
    assert temp_channel_manager.get_missing_scopes() == []


# -----------------------------------------------------------------------------
# 2. Reauthorization & Disconnection Safeguards
# -----------------------------------------------------------------------------

def test_disconnect_channel_preserves_client_secrets(temp_channel_manager: OwnerChannelManager):
    """Disconnecting channel must remove the token and reset DB, but NEVER delete client_secrets.json."""
    temp_channel_manager.token_file.write_text(json.dumps({"token": "mock-token"}))
    assert temp_channel_manager.token_file.exists()
    assert temp_channel_manager.client_secrets_file.exists()

    # Disconnect
    success = temp_channel_manager.disconnect_channel()
    assert success is True

    # Token removed
    assert not temp_channel_manager.token_file.exists()

    # Client secrets strictly preserved!
    assert temp_channel_manager.client_secrets_file.exists()


def test_reauthorization_flow_requests_all_scopes(temp_channel_manager: OwnerChannelManager):
    """Verify reauthorization deletes the old token and initiates flow with full management scopes."""
    temp_channel_manager.token_file.write_text(json.dumps({"token": "old-token"}))

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = json.dumps({
        "token": "new-token",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    })
    mock_creds.valid = True

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds

    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow) as mock_flow_factory:
        with patch.object(temp_channel_manager, "verify_live_channel") as mock_verify:
            mock_verify.return_value = OwnerChannelStatus(
                channel_id="UC_MANAGED",
                title="Full Management Channel",
                is_connected=True,
                scopes_authorized=YOUTUBE_MANAGEMENT_SCOPES,
            )

            success, msg, status = temp_channel_manager.reauthorize_in_browser(port=9090)

            assert success is True
            assert status is not None
            assert status.channel_id == "UC_MANAGED"

            # Check that from_client_secrets_file was called with YOUTUBE_MANAGEMENT_SCOPES
            mock_flow_factory.assert_called_once_with(
                str(temp_channel_manager.client_secrets_file),
                scopes=YOUTUBE_MANAGEMENT_SCOPES,
            )

            # Check that new token was persisted with mode 0600
            assert temp_channel_manager.token_file.exists()
            file_mode = stat.S_IMODE(os.stat(temp_channel_manager.token_file).st_mode)
            assert file_mode == 0o600


# -----------------------------------------------------------------------------
# 3. Autonomous Safety Locks & Destructive Action Protections
# -----------------------------------------------------------------------------

def test_safety_locks_block_destructive_actions(temp_channel_manager: OwnerChannelManager):
    """Autonomous deletion of videos or playlists must be strictly prohibited."""
    ok_vid, msg_vid, details_vid = temp_channel_manager.delete_video("test-vid-123")
    assert ok_vid is False
    assert "SAFETY_LOCK" in msg_vid
    assert details_vid.get("prohibited") is True

    ok_pl, msg_pl, details_pl = temp_channel_manager.delete_playlist("PL_123")
    assert ok_pl is False
    assert "SAFETY_LOCK" in msg_pl
    assert details_pl.get("prohibited") is True


def test_safety_locks_block_unconfirmed_operations(temp_channel_manager: OwnerChannelManager):
    """Mutating operations must require explicit confirmation to avoid accidental autonomous changes."""
    # Write full scope token so scope check passes
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    }))

    # 1. Update Video Metadata
    ok, msg, d = temp_channel_manager.update_video_metadata(
        video_id="v1",
        title="New Title",
        explicit_confirm=False,
    )
    assert ok is False
    assert "SAFETY_LOCK" in msg

    # 2. Create Playlist
    ok, msg, d = temp_channel_manager.create_playlist(
        title="New Playlist",
        explicit_confirm=False,
    )
    assert ok is False
    assert "SAFETY_LOCK" in msg

    # 3. Add to Playlist
    ok, msg, d = temp_channel_manager.add_video_to_playlist(
        playlist_id="p1",
        video_id="v1",
        explicit_confirm=False,
    )
    assert ok is False
    assert "SAFETY_LOCK" in msg

    # 4. Dry run bypasses execution safely without modifying
    ok_dry, msg_dry, d_dry = temp_channel_manager.update_video_metadata(
        video_id="v1",
        title="Dry Run Title",
        dry_run=True,
    )
    assert ok_dry is True
    assert "[DRY-RUN]" in msg_dry


# -----------------------------------------------------------------------------
# 4. Scope Deficiency & Permission Failure Handling
# -----------------------------------------------------------------------------

def test_scope_deficiency_prevents_unauthorized_operations(temp_channel_manager: OwnerChannelManager):
    """Verify operations fail gracefully when required scope is missing from token."""
    # Token only has readonly scope
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok-read-only",
        "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
    }))

    # Attempting video metadata update fails on scope check
    ok, msg, d = temp_channel_manager.update_video_metadata(
        video_id="v1",
        title="Updated Title",
        explicit_confirm=True,
    )
    assert ok is False
    assert "INSUFFICIENT_SCOPES" in msg

    # Attempting playlist creation fails on scope check
    ok_pl, msg_pl, d_pl = temp_channel_manager.create_playlist(
        title="Test Playlist",
        explicit_confirm=True,
    )
    assert ok_pl is False
    assert "INSUFFICIENT_SCOPES" in msg_pl

    # Attempting analytics query fails on scope check
    ok_an, msg_an, d_an = temp_channel_manager.get_channel_analytics(
        start_date="2026-01-01",
        end_date="2026-01-31",
    )
    assert ok_an is False
    assert "INSUFFICIENT_SCOPES" in msg_an


# -----------------------------------------------------------------------------
# 5. Supported Channel Management Operations (Mock API Execution)
# -----------------------------------------------------------------------------

def test_update_video_metadata_execution(temp_channel_manager: OwnerChannelManager):
    """Verify video metadata update correctly fetches existing snippet and submits merged updates."""
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    }))

    mock_service = MagicMock()
    # Mock videos().list() response
    mock_list_req = MagicMock()
    mock_list_req.execute.return_value = {
        "items": [{
            "id": "vid-999",
            "snippet": {
                "title": "Original Title",
                "description": "Original Description",
                "categoryId": "27",
                "tags": ["History"],
            },
            "status": {
                "privacyStatus": "private",
            },
        }]
    }
    mock_service.videos().list.return_value = mock_list_req

    # Mock videos().update() response
    mock_update_req = MagicMock()
    mock_update_req.execute.return_value = {
        "id": "vid-999",
        "snippet": {"title": "Updated Cinematic Title"},
    }
    mock_service.videos().update.return_value = mock_update_req

    with patch.object(temp_channel_manager, "get_authenticated_service", return_value=mock_service):
        ok, msg, data = temp_channel_manager.update_video_metadata(
            video_id="vid-999",
            title="Updated Cinematic Title",
            description="New description",
            tags=["History", "TrueStory", "Shorts"],
            privacy_status="unlisted",
            explicit_confirm=True,
        )

        assert ok is True
        assert "Successfully updated metadata" in msg
        mock_service.videos().list.assert_called_with(id="vid-999", part="snippet,status")
        mock_service.videos().update.assert_called_once()
        call_kwargs = mock_service.videos().update.call_args[1]
        assert call_kwargs["body"]["snippet"]["title"] == "Updated Cinematic Title"
        assert call_kwargs["body"]["snippet"]["categoryId"] == "27"  # Preserved
        assert call_kwargs["body"]["status"]["privacyStatus"] == "unlisted"


def test_playlist_operations_execution(temp_channel_manager: OwnerChannelManager):
    """Verify create, update, and add item operations on playlists."""
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    }))

    mock_service = MagicMock()

    # 1. Create Playlist
    mock_service.playlists().insert().execute.return_value = {"id": "PL_NEW_1"}
    with patch.object(temp_channel_manager, "get_authenticated_service", return_value=mock_service):
        ok, msg, res = temp_channel_manager.create_playlist(
            title="Mysterious Heists",
            description="The greatest unsolved heists",
            explicit_confirm=True,
        )
        assert ok is True
        assert res.get("id") == "PL_NEW_1"

    # 2. Add Video to Playlist
    mock_service.playlistItems().insert().execute.return_value = {"id": "ITEM_1"}
    with patch.object(temp_channel_manager, "get_authenticated_service", return_value=mock_service):
        ok, msg, res = temp_channel_manager.add_video_to_playlist(
            playlist_id="PL_NEW_1",
            video_id="vid-999",
            explicit_confirm=True,
        )
        assert ok is True
        assert res.get("id") == "ITEM_1"

    # 3. List Playlists
    mock_service.playlists().list().execute.return_value = {
        "items": [{"id": "PL_NEW_1", "snippet": {"title": "Mysterious Heists"}}]
    }
    with patch.object(temp_channel_manager, "get_authenticated_service", return_value=mock_service):
        ok, msg, items = temp_channel_manager.list_channel_playlists()
        assert ok is True
        assert len(items) == 1
        assert items[0]["snippet"]["title"] == "Mysterious Heists"


def test_analytics_query_execution(temp_channel_manager: OwnerChannelManager):
    """Verify official YouTube Analytics query executes with channel metrics."""
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    }))

    mock_service = MagicMock()
    mock_service.reports().query().execute.return_value = {
        "columnHeaders": [{"name": "views"}, {"name": "likes"}],
        "rows": [[1450, 89]],
    }

    with patch.object(temp_channel_manager, "get_authenticated_service", return_value=mock_service):
        ok, msg, report = temp_channel_manager.get_channel_analytics(
            start_date="2026-01-01",
            end_date="2026-01-31",
            metrics=["views", "likes"],
        )
        assert ok is True
        assert "Analytics report retrieved" in msg
        assert report["rows"] == [[1450, 89]]


def test_audit_live_capabilities_structure(temp_channel_manager: OwnerChannelManager):
    """Verify audit_live_capabilities compiles structured report and separates read vs untested write operations."""
    temp_channel_manager.token_file.write_text(json.dumps({
        "token": "tok",
        "scopes": YOUTUBE_MANAGEMENT_SCOPES,
    }))

    mock_service = MagicMock()
    # Channels
    mock_service.channels().list().execute.return_value = {
        "items": [{
            "id": "UC_AUDIT",
            "snippet": {"title": "Audit Channel", "customUrl": "@audit"},
            "statistics": {"subscriberCount": "50", "videoCount": "5", "viewCount": "100"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UPLOADS_PL"}},
        }]
    }
    # Playlists
    mock_service.playlists().list().execute.return_value = {"items": []}
    # Playlist items (videos)
    mock_service.playlistItems().list().execute.return_value = {
        "items": [{
            "contentDetails": {"videoId": "vid-1"},
            "snippet": {"title": "Video 1", "publishedAt": "2026-01-01T00:00:00Z"},
            "status": {"privacyStatus": "public"},
        }]
    }
    # Analytics
    mock_service.reports().query().execute.return_value = {
        "columnHeaders": [{"name": "views"}],
        "rows": [[10]],
    }

    with patch.object(temp_channel_manager, "get_authenticated_service", return_value=mock_service):
        audit = temp_channel_manager.audit_live_capabilities()

        assert audit["overall_status"] == "ALL_LIVE_CHECKS_PASSED"
        assert audit["channel_identity"]["title"] == "Audit Channel"
        assert audit["live_tested_operations"]["channel_verification"]["status"] == "PASS"
        assert audit["live_tested_operations"]["playlist_listing"]["status"] == "PASS"
        assert audit["live_tested_operations"]["video_listing"]["status"] == "PASS"
        assert audit["live_tested_operations"]["analytics_reporting"]["status"] == "PASS"

        # Mutating operations must be present and marked CODE_VERIFIED_UNMUTATED or BLOCKED
        untested = audit["untested_mutating_operations"]
        assert untested["video_metadata_update"]["status"] == "CODE_VERIFIED_UNMUTATED"
        assert untested["destructive_deletion"]["status"] == "BLOCKED_BY_SAFETY_LOCK"
