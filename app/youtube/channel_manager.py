"""Owner YouTube channel integration and OAuth 2.0 connection manager.

Manages connection to the owner's EXISTING YouTube channel.
Strictly decoupled from public competitor research.
Does NOT publish, upload, or alter channel settings unless explicitly approved.
Never asks the user to paste credentials into chat.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config
from app.database.db import db
from app.database.models import OwnerChannelStatus, utc_now_iso
from app.utils.logger import logger

# Official OAuth scopes for YouTube channel management & analytics
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",           # Inspect owner channel info & videos
    "https://www.googleapis.com/auth/youtube.upload",             # Private video upload (when approved)
    "https://www.googleapis.com/auth/yt-analytics.readonly",       # Read authorized channel analytics
]


class OwnerChannelManager:
    """Manages authentication, identity, and permissions for the owner's existing YouTube channel."""

    def __init__(
        self,
        client_secrets_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
    ) -> None:
        self.client_secrets_file = client_secrets_file or config.youtube_client_secrets_file
        self.token_file = token_file or config.youtube_token_file

    def get_connection_status(self) -> OwnerChannelStatus:
        """Check the live or stored connection status of the owner channel."""
        # 1. Check local persistent database status
        saved_status = db.get_owner_channel_status()
        if saved_status.is_connected:
            return saved_status

        # 2. Check token file on local disk
        if not self.token_file.exists():
            return OwnerChannelStatus(
                is_connected=False,
                scopes_authorized=[],
                last_verified_at=utc_now_iso(),
            )

        # 3. If token file exists, attempt verification
        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                token_data = json.load(f)
            scopes = token_data.get("scopes", [])
            has_refresh = bool(token_data.get("refresh_token"))

            # Return preliminary status based on valid token format
            return OwnerChannelStatus(
                is_connected=True,
                scopes_authorized=scopes,
                last_verified_at=utc_now_iso(),
            )
        except Exception as e:
            logger.warning(f"Error reading local YouTube token file: {e}")
            return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

    def verify_live_channel(self) -> OwnerChannelStatus:
        """Verify the OAuth token with YouTube API and fetch authenticated channel identity."""
        if not self.token_file.exists():
            return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

        if not self.client_secrets_file.exists():
            logger.warning(f"Client secrets file not found at: {self.client_secrets_file}")
            return OwnerChannelStatus(
                is_connected=False,
                last_verified_at=utc_now_iso(),
            )

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            with open(self.token_file, "r", encoding="utf-8") as f:
                token_info = json.load(f)

            creds = Credentials.from_authorized_user_info(token_info, scopes=YOUTUBE_SCOPES)
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())
                    # Save refreshed token
                    with open(self.token_file, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                else:
                    return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

            service = build("youtube", "v3", credentials=creds)
            # Fetch authenticated channel
            resp = service.channels().list(mine=True, part="snippet,statistics").execute()
            items = resp.get("items", [])
            if not items:
                logger.warning("OAuth token valid, but no YouTube channel found for this Google account.")
                return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

            ch = items[0]
            status = OwnerChannelStatus(
                channel_id=ch.get("id", ""),
                title=ch.get("snippet", {}).get("title", "Owner Channel"),
                custom_url=ch.get("snippet", {}).get("customUrl", ""),
                subscriber_count=int(ch.get("statistics", {}).get("subscriberCount", 0)),
                video_count=int(ch.get("statistics", {}).get("videoCount", 0)),
                scopes_authorized=list(creds.scopes or []),
                is_connected=True,
                connected_at=utc_now_iso(),
                last_verified_at=utc_now_iso(),
            )
            # Persist in DB
            db.set_owner_channel_status(status)
            db.record_event(
                "OWNER_CHANNEL_VERIFIED",
                f"Owner channel verified: {status.title} ({status.channel_id})",
                status.to_dict(),
            )
            return status

        except Exception as e:
            logger.error(f"Live verification of owner channel failed: {e}")
            return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

    def disconnect_channel(self) -> bool:
        """Safely disconnect local owner channel authentication without modifying YouTube."""
        try:
            if self.token_file.exists():
                self.token_file.unlink()
            db.clear_owner_channel_status()
            logger.info("Owner channel disconnected locally.")
            db.record_event("OWNER_CHANNEL_DISCONNECTED", "Owner channel disconnected locally.")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting channel: {e}")
            return False

    def generate_setup_instructions(self) -> Dict[str, Any]:
        """Generate local setup instructions for authenticating the owner's existing channel."""
        secrets_exist = self.client_secrets_file.exists()
        token_exists = self.token_file.exists()

        return {
            "client_secrets_path": str(self.client_secrets_file),
            "client_secrets_found": secrets_exist,
            "token_path": str(self.token_file),
            "token_found": token_exists,
            "required_scopes": YOUTUBE_SCOPES,
            "instructions": [
                "1. Open Google Cloud Console (https://console.cloud.google.com/).",
                "2. Ensure YouTube Data API v3 and YouTube Analytics API are enabled.",
                "3. In 'OAuth consent screen', configure User Type as External, add your email as Test User.",
                "4. Under 'Credentials' -> 'Create Credentials' -> 'OAuth client ID', select 'Desktop app'.",
                f"5. Download the JSON credential file and save it locally as '{self.client_secrets_file}'.",
                "6. Run: ./run.sh youtube --connect to authenticate your existing channel in your browser.",
                "7. The local token will be stored securely at data/youtube_token.json (never committed to git).",
            ],
        }


# Global channel manager singleton
channel_manager = OwnerChannelManager()
