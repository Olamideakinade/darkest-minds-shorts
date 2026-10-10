"""Unit tests for YouTube Data API v3 client, duration parsing, caching, and error handling."""

import json
from unittest.mock import MagicMock, patch
import urllib.error

from app.research.youtube_client import (
    YouTubeResearchClient,
    parse_iso8601_duration,
)


def test_iso8601_duration_parsing():
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT1M15S") == 75
    assert parse_iso8601_duration("PT2M") == 120
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("P1DT2H") == 93600
    assert parse_iso8601_duration("PT0S") == 0
    assert parse_iso8601_duration("invalid_string") == 0


def test_missing_api_key_handling():
    client = YouTubeResearchClient(api_key="")
    assert client.is_configured is False

    res = client.search_story_videos("strange history")
    assert res.success is False
    assert "YouTube API Key not configured" in res.error_message
    assert res.quota_spent == 0

    batch_res = client.get_video_details_batch(["vid_123"])
    assert batch_res.success is False
    assert batch_res.quota_spent == 0


def test_parse_video_item():
    client = YouTubeResearchClient(api_key="test_key")
    raw_item = {
        "id": "abc123xyz",
        "snippet": {
            "title": "The Mysterious Vault of Padmanabhaswamy",
            "channelId": "chan_001",
            "channelTitle": "Ancient Curiosities",
            "publishedAt": "2026-09-01T12:00:00Z",
            "tags": ["history", "vault", "mystery"],
        },
        "contentDetails": {
            "duration": "PT55S",
        },
        "statistics": {
            "viewCount": "150000",
            "likeCount": "12000",
            "commentCount": "450",
        },
    }

    parsed = client.parse_video_item(raw_item)
    assert parsed is not None
    assert parsed.video_id == "abc123xyz"
    assert parsed.title == "The Mysterious Vault of Padmanabhaswamy"
    assert parsed.duration_sec == 55
    assert parsed.view_count == 150000
    assert parsed.like_count == 12000
    assert parsed.comment_count == 450
    assert "mystery" in parsed.topic_tags


def test_request_limit_enforcement():
    client = YouTubeResearchClient(api_key="fake_key", max_requests_per_run=1)
    client.requests_made_this_run = 1  # simulate limit hit

    res = client.search_story_videos("strange events")
    assert res.success is False
    assert "Reached maximum API requests limit" in res.error_message


def test_quota_exhaustion_handling():
    client = YouTubeResearchClient(api_key="exhausted_key")

    error_response = json.dumps({
        "error": {
            "errors": [{"reason": "quotaExceeded", "message": "The request cannot be completed because you have exceeded your quota."}],
            "code": 403,
            "message": "Quota exceeded",
        }
    }).encode("utf-8")

    http_error = urllib.error.HTTPError(
        url="https://www.googleapis.com/youtube/v3/search",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=MagicMock(read=lambda: error_response),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        res = client._execute_request("search", {"q": "test"}, quota_cost=100)
        assert res.success is False
        assert "quota exhausted" in res.error_message.lower()


def test_network_retry_and_backoff():
    client = YouTubeResearchClient(api_key="retry_key", timeout_sec=2)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"items": []}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    side_effects = [
        urllib.error.URLError("Connection reset by peer"),
        mock_resp,
    ]


    with patch("urllib.request.urlopen", side_effect=side_effects):
        with patch("time.sleep") as mock_sleep:
            res = client._execute_request("search", {"q": "test"}, quota_cost=100, max_retries=2)
            assert res.success is True
            assert mock_sleep.called
