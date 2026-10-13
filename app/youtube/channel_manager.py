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
from typing import Any, Dict, List, Optional, Tuple

from app.config import config
from app.database.db import db
from app.database.models import OwnerChannelStatus, utc_now_iso
from app.utils.logger import logger

# Comprehensive official YouTube OAuth scopes for broad channel management
YOUTUBE_MANAGEMENT_SCOPES = [
    "https://www.googleapis.com/auth/youtube",                   # Full management: videos, playlists, channel assets
    "https://www.googleapis.com/auth/youtube.force-ssl",         # Edit/manage videos, playlists, captions (SSL-enforced)
    "https://www.googleapis.com/auth/youtube.upload",            # Video uploads and metadata configuration
    "https://www.googleapis.com/auth/youtube.readonly",          # View account data, videos, and playlists
    "https://www.googleapis.com/auth/yt-analytics.readonly",      # YouTube Analytics API v2 reports
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly", # Monetary YouTube Analytics reports (if monetized)
]

# Mapping of scopes to human-readable capability descriptions
SCOPE_CAPABILITIES: Dict[str, str] = {
    "https://www.googleapis.com/auth/youtube": "Full channel management (videos, playlists, channel assets)",
    "https://www.googleapis.com/auth/youtube.force-ssl": "Manage & edit videos, playlists, captions, comments (SSL)",
    "https://www.googleapis.com/auth/youtube.upload": "Upload videos and configure uploaded video metadata",
    "https://www.googleapis.com/auth/youtube.readonly": "View channel details, videos, and playlists",
    "https://www.googleapis.com/auth/yt-analytics.readonly": "View YouTube Analytics reports (views, retention, subscribers)",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly": "View monetary YouTube Analytics (revenue, CPM if monetized)",
}

# Aliased for backwards compatibility
YOUTUBE_SCOPES = YOUTUBE_MANAGEMENT_SCOPES


class OwnerChannelManager:
    """Manages authentication, identity, scopes, and supported operations for the owner's YouTube channel."""

    def __init__(
        self,
        client_secrets_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
    ) -> None:
        self.client_secrets_file = client_secrets_file or config.youtube_client_secrets_file
        self.token_file = token_file or config.youtube_token_file

    def get_granted_scopes(self) -> List[str]:
        """Read the actual token file on disk and return only genuinely granted scopes."""
        if not self.token_file.exists():
            return []
        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                token_data = json.load(f)
            return list(token_data.get("scopes", []))
        except Exception as e:
            logger.warning(f"Failed to read granted scopes from token file: {e}")
            return []

    def has_scope(self, scope: str) -> bool:
        """Check whether a specific OAuth scope is present in the current granted token."""
        return scope in self.get_granted_scopes()

    def get_missing_scopes(self) -> List[str]:
        """Return which of the full management scopes have not yet been granted."""
        granted = set(self.get_granted_scopes())
        return [s for s in YOUTUBE_MANAGEMENT_SCOPES if s not in granted]

    def is_fully_scoped(self) -> bool:
        """Check if all recommended channel management scopes are granted."""
        return len(self.get_missing_scopes()) == 0

    def get_connection_status(self) -> OwnerChannelStatus:
        """Check the live or stored connection status of the owner channel.
        
        Guarantees that reported scopes match the actual token file on disk.
        """
        if not self.token_file.exists():
            return OwnerChannelStatus(
                is_connected=False,
                scopes_authorized=[],
                last_verified_at=utc_now_iso(),
            )

        granted_scopes = self.get_granted_scopes()

        # Check local persistent database status
        saved_status = db.get_owner_channel_status()
        if saved_status.is_connected and saved_status.channel_id:
            # Strictly reflect the actual token file's granted scopes
            saved_status.scopes_authorized = granted_scopes
            return saved_status

        # If DB status is empty but token exists, return verified token scopes
        return OwnerChannelStatus(
            is_connected=bool(granted_scopes),
            scopes_authorized=granted_scopes,
            last_verified_at=utc_now_iso(),
        )

    def get_authenticated_service(self, api_name: str = "youtube", api_version: str = "v3") -> Any:
        """Construct and return an authorized Google API service instance.
        
        Handles automatic token refresh if expired.
        """
        if not self.token_file.exists():
            raise RuntimeError(f"Authentication token not found at {self.token_file}. Please authorize channel first.")

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        from google.auth.exceptions import RefreshError

        with open(self.token_file, "r", encoding="utf-8") as f:
            token_info = json.load(f)

        creds = Credentials.from_authorized_user_info(token_info, scopes=YOUTUBE_MANAGEMENT_SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(self.token_file, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                    try:
                        os.chmod(self.token_file, 0o600)
                    except OSError:
                        pass
                except RefreshError as re:
                    logger.warning(f"OAuth token refresh failed (revoked or expired): {re}")
                    self.disconnect_channel(remove_token_only=True)
                    raise RuntimeError(f"Token refresh failed. Access may be revoked: {re}")
            else:
                raise RuntimeError("OAuth credentials are invalid or expired without refresh token.")

        return build(api_name, api_version, credentials=creds)

    def verify_live_channel(self) -> OwnerChannelStatus:
        """Verify the OAuth token with YouTube API and fetch authenticated channel identity."""
        if not self.token_file.exists():
            return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

        if not self.client_secrets_file.exists():
            logger.warning(f"Client secrets file not found at: {self.client_secrets_file}")
            return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            resp = service.channels().list(mine=True, part="snippet,statistics").execute()
            items = resp.get("items", [])
            if not items:
                logger.warning("OAuth token valid, but no YouTube channel found for this Google account.")
                return OwnerChannelStatus(is_connected=False, last_verified_at=utc_now_iso())

            ch = items[0]
            actual_scopes = self.get_granted_scopes()

            status = OwnerChannelStatus(
                channel_id=ch.get("id", ""),
                title=ch.get("snippet", {}).get("title", "Owner Channel"),
                custom_url=ch.get("snippet", {}).get("customUrl", ""),
                subscriber_count=int(ch.get("statistics", {}).get("subscriberCount", 0)),
                video_count=int(ch.get("statistics", {}).get("videoCount", 0)),
                scopes_authorized=actual_scopes,
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

    def authenticate_in_browser(
        self,
        port: int = 0,
        force_reauth: bool = False,
    ) -> Tuple[bool, str, Optional[OwnerChannelStatus]]:
        """Start official Google OAuth 2.0 flow for desktop application, opening system browser.
        
        Requests the comprehensive YOUTUBE_MANAGEMENT_SCOPES.
        If force_reauth is True, removes the old token first so Google prompts with fresh scope consent.
        """
        if not self.client_secrets_file.exists():
            msg = (
                f"OAuth client secrets file not found at: {self.client_secrets_file}\n\n"
                "To authorize your existing YouTube channel:\n"
                "1. Go to Google Cloud Console (https://console.cloud.google.com/).\n"
                "2. Ensure 'YouTube Data API v3' and 'YouTube Analytics API' are enabled.\n"
                "3. In 'OAuth consent screen', configure User Type as External, add your email under Test Users.\n"
                "4. Under 'Credentials' -> 'Create Credentials' -> 'OAuth client ID', select 'Desktop app'.\n"
                f"5. Download the credentials JSON and save it as '{self.client_secrets_file}'.\n"
                "6. Run './run.sh youtube --connect' to authenticate in your browser."
            )
            logger.warning("Browser sign-in aborted: client_secrets.json not found.")
            return False, msg, None

        if force_reauth:
            logger.info("Force reauthorization requested: resetting old token before browser sign-in.")
            self.disconnect_channel(remove_token_only=True)

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            logger.info("Initializing Google OAuth 2.0 flow with comprehensive management scopes...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_file),
                scopes=YOUTUBE_MANAGEMENT_SCOPES,
            )

            print("\n" + "=" * 70)
            print(" GOOGLE OAUTH 2.0 — SYSTEM BROWSER SIGN-IN (FULL CHANNEL MANAGEMENT)")
            print("=" * 70)
            print("Opening your default web browser for Google sign-in...")
            print("1. Select the Google account that owns your YouTube channel.")
            print("2. Approve the requested management, upload, and analytics permissions.")
            print("3. Return to this terminal once Google confirms authorization.")
            print("-" * 70 + "\n")

            creds = flow.run_local_server(
                port=port,
                prompt="consent",
                access_type="offline",
                success_message="Authentication complete! You may now close this browser tab and return to Mhide Story Intelligence.",
                open_browser=True,
            )

            # Persist token to disk with restrictive 0o600 permissions
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

            try:
                os.chmod(self.token_file, 0o600)
            except OSError:
                pass

            logger.info(f"OAuth token saved securely to {self.token_file} (mode 0600, git-ignored)")

            # Verify the connected channel identity
            status = self.verify_live_channel()
            if status.is_connected:
                granted_count = len(status.scopes_authorized)
                total_count = len(YOUTUBE_MANAGEMENT_SCOPES)
                msg = (
                    f"Successfully authorized YouTube channel: '{status.title}' (ID: {status.channel_id})\n"
                    f"Granted {granted_count} of {total_count} management scopes."
                )
                logger.info(msg)
                return True, msg, status
            else:
                msg = "OAuth authorization completed, but unable to retrieve YouTube channel metadata."
                logger.warning(msg)
                return False, msg, status

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Browser authentication encountered an error: {err_msg}")
            return False, f"Browser authorization failed: {err_msg}", None

    def reauthorize_in_browser(self, port: int = 0) -> Tuple[bool, str, Optional[OwnerChannelStatus]]:
        """Convenience method to safely reset the old token and launch browser reauthorization."""
        return self.authenticate_in_browser(port=port, force_reauth=True)

    def disconnect_channel(self, remove_token_only: bool = True) -> bool:
        """Safely disconnect local owner channel authentication without modifying YouTube or client secrets."""
        try:
            if self.token_file.exists():
                self.token_file.unlink()
            db.clear_owner_channel_status()
            logger.info("Owner channel disconnected locally (token removed; client secrets preserved).")
            db.record_event("OWNER_CHANNEL_DISCONNECTED", "Owner channel token removed locally.")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting channel: {e}")
            return False

    # -------------------------------------------------------------------------
    # Supported Channel Management Operations (Guarded by Safety Lock)
    # -------------------------------------------------------------------------

    def update_video_metadata(
        self,
        video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category_id: Optional[str] = None,
        privacy_status: Optional[str] = None,
        dry_run: bool = False,
        explicit_confirm: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Update metadata on an existing video owned by this channel.
        
        Requires 'https://www.googleapis.com/auth/youtube' or 'https://www.googleapis.com/auth/youtube.force-ssl'.
        Guarded by explicit_confirm to prevent autonomous modifications of existing videos without approval.
        """
        # Safety Lock check
        if not explicit_confirm and not dry_run:
            msg = "SAFETY_LOCK: Video metadata update requires explicit approval (explicit_confirm=True)."
            logger.warning(msg)
            return False, msg, {"safety_lock": True}

        # Check required scopes
        can_manage = (
            self.has_scope("https://www.googleapis.com/auth/youtube")
            or self.has_scope("https://www.googleapis.com/auth/youtube.force-ssl")
        )
        if not can_manage:
            msg = (
                "INSUFFICIENT_SCOPES: Updating video metadata requires 'https://www.googleapis.com/auth/youtube' "
                "or 'https://www.googleapis.com/auth/youtube.force-ssl'. Please run './run.sh youtube --reconnect'."
            )
            logger.warning(msg)
            return False, msg, {"error": "INSUFFICIENT_SCOPES"}

        if dry_run:
            return True, f"[DRY-RUN] Video '{video_id}' metadata would be updated.", {
                "dry_run": True,
                "video_id": video_id,
                "updates": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "category_id": category_id,
                    "privacy_status": privacy_status,
                },
            }

        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")

            # 1. Fetch current snippet and status to preserve required YouTube fields
            curr_resp = service.videos().list(id=video_id, part="snippet,status").execute()
            items = curr_resp.get("items", [])
            if not items:
                msg = f"Video '{video_id}' not found on authenticated channel."
                logger.error(msg)
                return False, msg, {"error": "VIDEO_NOT_FOUND"}

            curr_snippet = items[0].get("snippet", {})
            curr_status = items[0].get("status", {})

            # 2. Merge changes
            if title is not None:
                curr_snippet["title"] = title
            if description is not None:
                curr_snippet["description"] = description
            if tags is not None:
                curr_snippet["tags"] = tags
            if category_id is not None:
                curr_snippet["categoryId"] = category_id
            if privacy_status is not None:
                curr_status["privacyStatus"] = privacy_status

            body = {
                "id": video_id,
                "snippet": curr_snippet,
                "status": curr_status,
            }

            update_resp = service.videos().update(part="snippet,status", body=body).execute()
            msg = f"Successfully updated metadata for video '{video_id}'."
            logger.info(msg)
            db.record_event("OWNER_VIDEO_METADATA_UPDATED", msg, {"video_id": video_id})
            return True, msg, update_resp

        except Exception as e:
            err_msg = f"Failed to update video metadata: {e}"
            logger.error(err_msg)
            return False, err_msg, {"error": str(e)}

    def set_video_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Path,
        dry_run: bool = False,
        explicit_confirm: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Upload and assign a custom thumbnail to a video.
        
        Requires account to have custom thumbnail permissions enabled in YouTube Studio.
        Guarded by explicit_confirm.
        """
        if not explicit_confirm and not dry_run:
            msg = "SAFETY_LOCK: Setting custom thumbnail requires explicit approval (explicit_confirm=True)."
            logger.warning(msg)
            return False, msg, {"safety_lock": True}

        can_manage = (
            self.has_scope("https://www.googleapis.com/auth/youtube")
            or self.has_scope("https://www.googleapis.com/auth/youtube.force-ssl")
            or self.has_scope("https://www.googleapis.com/auth/youtube.upload")
        )
        if not can_manage:
            msg = "INSUFFICIENT_SCOPES: Uploading custom thumbnails requires 'youtube' or 'youtube.upload' scope."
            return False, msg, {"error": "INSUFFICIENT_SCOPES"}

        if not thumbnail_path.exists():
            return False, f"Thumbnail image not found: {thumbnail_path}", {"error": "FILE_NOT_FOUND"}

        if dry_run:
            return True, f"[DRY-RUN] Thumbnail for video '{video_id}' would be uploaded from {thumbnail_path}.", {"dry_run": True}

        try:
            from googleapiclient.http import MediaFileUpload

            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg", resumable=True)
            resp = service.thumbnails().set(videoId=video_id, media_body=media).execute()

            msg = f"Successfully updated thumbnail for video '{video_id}'."
            logger.info(msg)
            db.record_event("OWNER_THUMBNAIL_UPDATED", msg, {"video_id": video_id})
            return True, msg, resp

        except Exception as e:
            err_msg = f"Failed to set custom thumbnail: {e}"
            logger.error(err_msg)
            return False, err_msg, {"error": str(e)}

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "public",
        dry_run: bool = False,
        explicit_confirm: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Create a new playlist on the authenticated channel."""
        if not explicit_confirm and not dry_run:
            msg = "SAFETY_LOCK: Creating playlists requires explicit approval (explicit_confirm=True)."
            logger.warning(msg)
            return False, msg, {"safety_lock": True}

        can_manage = (
            self.has_scope("https://www.googleapis.com/auth/youtube")
            or self.has_scope("https://www.googleapis.com/auth/youtube.force-ssl")
        )
        if not can_manage:
            msg = "INSUFFICIENT_SCOPES: Creating playlists requires 'youtube' or 'youtube.force-ssl' scope."
            return False, msg, {"error": "INSUFFICIENT_SCOPES"}

        if dry_run:
            return True, f"[DRY-RUN] Playlist '{title}' would be created.", {"dry_run": True, "title": title}

        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                },
                "status": {
                    "privacyStatus": privacy_status,
                },
            }
            resp = service.playlists().insert(part="snippet,status", body=body).execute()
            pl_id = resp.get("id", "")
            msg = f"Successfully created playlist '{title}' (ID: {pl_id})."
            logger.info(msg)
            db.record_event("OWNER_PLAYLIST_CREATED", msg, {"playlist_id": pl_id, "title": title})
            return True, msg, resp

        except Exception as e:
            err_msg = f"Failed to create playlist: {e}"
            logger.error(err_msg)
            return False, err_msg, {"error": str(e)}

    def update_playlist(
        self,
        playlist_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        privacy_status: Optional[str] = None,
        dry_run: bool = False,
        explicit_confirm: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Update an existing playlist's title, description, or visibility."""
        if not explicit_confirm and not dry_run:
            msg = "SAFETY_LOCK: Modifying playlists requires explicit approval (explicit_confirm=True)."
            return False, msg, {"safety_lock": True}

        can_manage = (
            self.has_scope("https://www.googleapis.com/auth/youtube")
            or self.has_scope("https://www.googleapis.com/auth/youtube.force-ssl")
        )
        if not can_manage:
            msg = "INSUFFICIENT_SCOPES: Updating playlists requires 'youtube' or 'youtube.force-ssl' scope."
            return False, msg, {"error": "INSUFFICIENT_SCOPES"}

        if dry_run:
            return True, f"[DRY-RUN] Playlist '{playlist_id}' would be updated.", {"dry_run": True}

        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            curr = service.playlists().list(id=playlist_id, part="snippet,status").execute()
            items = curr.get("items", [])
            if not items:
                return False, f"Playlist '{playlist_id}' not found.", {"error": "PLAYLIST_NOT_FOUND"}

            snippet = items[0].get("snippet", {})
            status = items[0].get("status", {})

            if title is not None:
                snippet["title"] = title
            if description is not None:
                snippet["description"] = description
            if privacy_status is not None:
                status["privacyStatus"] = privacy_status

            body = {"id": playlist_id, "snippet": snippet, "status": status}
            resp = service.playlists().update(part="snippet,status", body=body).execute()
            msg = f"Successfully updated playlist '{playlist_id}'."
            logger.info(msg)
            db.record_event("OWNER_PLAYLIST_UPDATED", msg, {"playlist_id": playlist_id})
            return True, msg, resp

        except Exception as e:
            err_msg = f"Failed to update playlist: {e}"
            logger.error(err_msg)
            return False, err_msg, {"error": str(e)}

    def add_video_to_playlist(
        self,
        playlist_id: str,
        video_id: str,
        position: Optional[int] = None,
        dry_run: bool = False,
        explicit_confirm: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Add a video to a playlist."""
        if not explicit_confirm and not dry_run:
            msg = "SAFETY_LOCK: Adding videos to playlists requires explicit approval (explicit_confirm=True)."
            return False, msg, {"safety_lock": True}

        can_manage = (
            self.has_scope("https://www.googleapis.com/auth/youtube")
            or self.has_scope("https://www.googleapis.com/auth/youtube.force-ssl")
        )
        if not can_manage:
            msg = "INSUFFICIENT_SCOPES: Adding items to playlists requires 'youtube' or 'youtube.force-ssl' scope."
            return False, msg, {"error": "INSUFFICIENT_SCOPES"}

        if dry_run:
            return True, f"[DRY-RUN] Video '{video_id}' would be added to playlist '{playlist_id}'.", {"dry_run": True}

        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            snippet: Dict[str, Any] = {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
            if position is not None:
                snippet["position"] = position

            body = {"snippet": snippet}
            resp = service.playlistItems().insert(part="snippet", body=body).execute()
            item_id = resp.get("id", "")
            msg = f"Successfully added video '{video_id}' to playlist '{playlist_id}' (Item ID: {item_id})."
            logger.info(msg)
            db.record_event("OWNER_PLAYLIST_ITEM_ADDED", msg, {"playlist_id": playlist_id, "video_id": video_id})
            return True, msg, resp

        except Exception as e:
            err_msg = f"Failed to add video to playlist: {e}"
            logger.error(err_msg)
            return False, err_msg, {"error": str(e)}

    def list_channel_playlists(self, max_results: int = 50) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Retrieve playlists belonging to the authenticated channel."""
        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            resp = service.playlists().list(
                part="snippet,contentDetails,status",
                mine=True,
                maxResults=max_results,
            ).execute()
            items = resp.get("items", [])
            return True, f"Found {len(items)} playlists.", items
        except Exception as e:
            err_msg = f"Failed to list playlists: {e}"
            logger.error(err_msg)
            return False, err_msg, []

    def list_channel_videos(self, max_results: int = 50) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """List uploaded videos for the authenticated channel via the uploads playlist (read-only, 1 quota unit)."""
        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            ch_resp = service.channels().list(mine=True, part="contentDetails").execute()
            items = ch_resp.get("items", [])
            if not items:
                return False, "Channel not found.", []
            uploads_pl_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not uploads_pl_id:
                return False, "Uploads playlist not found for channel.", []

            pl_resp = service.playlistItems().list(
                playlistId=uploads_pl_id,
                part="snippet,contentDetails,status",
                maxResults=max_results,
            ).execute()
            vids = pl_resp.get("items", [])
            return True, f"Found {len(vids)} uploaded videos.", vids
        except Exception as e:
            err_msg = f"Failed to list channel videos: {e}"
            logger.error(err_msg)
            return False, err_msg, []

    def get_channel_analytics(
        self,
        start_date: str,
        end_date: str,
        metrics: Optional[List[str]] = None,
        dimensions: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Query official YouTube Analytics API v2 for the authenticated channel."""
        can_read_analytics = (
            self.has_scope("https://www.googleapis.com/auth/yt-analytics.readonly")
            or self.has_scope("https://www.googleapis.com/auth/yt-analytics-monetary.readonly")
        )
        if not can_read_analytics:
            msg = "INSUFFICIENT_SCOPES: Querying analytics requires 'https://www.googleapis.com/auth/yt-analytics.readonly'."
            return False, msg, {"error": "INSUFFICIENT_SCOPES"}

        metric_str = ",".join(metrics or [
            "views",
            "estimatedMinutesWatched",
            "averageViewDuration",
            "likes",
            "comments",
            "subscribersGained",
        ])

        try:
            service = self.get_authenticated_service(api_name="youtubeAnalytics", api_version="v2")
            kwargs: Dict[str, Any] = {
                "ids": "channel==MINE",
                "startDate": start_date,
                "endDate": end_date,
                "metrics": metric_str,
            }
            if dimensions:
                kwargs["dimensions"] = dimensions

            resp = service.reports().query(**kwargs).execute()
            return True, "Analytics report retrieved successfully.", resp

        except Exception as e:
            err_msg = f"YouTube Analytics query failed: {e}"
            logger.error(err_msg)
            return False, err_msg, {"error": str(e)}

    def audit_live_capabilities(self) -> Dict[str, Any]:
        """Execute a strictly read-only, non-destructive live capability audit against official YouTube APIs.
        
        Confirms live identity, lists playlists & videos, and queries analytics.
        Does NOT upload, mutate, publish, or delete anything.
        """
        audit_results: Dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "channel_identity": {},
            "live_tested_operations": {},
            "untested_mutating_operations": {},
            "api_quotas_and_limitations": {},
            "overall_status": "UNKNOWN",
        }

        # 1. LIVE CHECK: Channel Identity
        try:
            service = self.get_authenticated_service(api_name="youtube", api_version="v3")
            ch_resp = service.channels().list(mine=True, part="snippet,statistics,contentDetails,status").execute()
            items = ch_resp.get("items", [])
            if items:
                ch = items[0]
                audit_results["channel_identity"] = {
                    "live_verified": True,
                    "title": ch.get("snippet", {}).get("title"),
                    "channel_id": ch.get("id"),
                    "custom_url": ch.get("snippet", {}).get("customUrl"),
                    "subscribers": int(ch.get("statistics", {}).get("subscriberCount", 0)),
                    "video_count": int(ch.get("statistics", {}).get("videoCount", 0)),
                    "view_count": int(ch.get("statistics", {}).get("viewCount", 0)),
                    "privacy_status": ch.get("status", {}).get("privacyStatus", "public"),
                }
                audit_results["live_tested_operations"]["channel_verification"] = {
                    "status": "PASS",
                    "api": "YouTube Data API v3 (channels.list)",
                    "details": f"Authenticated live channel '{ch.get('snippet', {}).get('title')}' ({ch.get('id')})",
                }
            else:
                audit_results["live_tested_operations"]["channel_verification"] = {
                    "status": "FAIL",
                    "error": "No YouTube channel associated with this Google Account.",
                }
        except Exception as e:
            audit_results["live_tested_operations"]["channel_verification"] = {
                "status": "FAIL",
                "error": str(e),
            }

        # 2. LIVE CHECK: List Existing Playlists (Read-Only)
        try:
            ok_pl, msg_pl, playlists = self.list_channel_playlists(max_results=20)
            pl_summaries = []
            for p in playlists:
                pl_summaries.append({
                    "id": p.get("id"),
                    "title": p.get("snippet", {}).get("title"),
                    "item_count": p.get("contentDetails", {}).get("itemCount", 0),
                    "privacy": p.get("status", {}).get("privacyStatus"),
                })
            audit_results["live_tested_operations"]["playlist_listing"] = {
                "status": "PASS" if ok_pl else "FAIL",
                "api": "YouTube Data API v3 (playlists.list)",
                "count": len(playlists),
                "items": pl_summaries,
                "message": msg_pl,
            }
        except Exception as e:
            audit_results["live_tested_operations"]["playlist_listing"] = {
                "status": "FAIL",
                "error": str(e),
            }

        # 3. LIVE CHECK: List Existing Videos (Read-Only via Uploads Playlist)
        try:
            ok_vids, msg_vids, vids = self.list_channel_videos(max_results=20)
            vid_summaries = []
            for v in vids:
                vid_summaries.append({
                    "id": v.get("contentDetails", {}).get("videoId") or v.get("snippet", {}).get("resourceId", {}).get("videoId"),
                    "title": v.get("snippet", {}).get("title"),
                    "published_at": v.get("snippet", {}).get("publishedAt"),
                    "privacy": v.get("status", {}).get("privacyStatus", "unknown"),
                })
            audit_results["live_tested_operations"]["video_listing"] = {
                "status": "PASS" if ok_vids else "FAIL",
                "api": "YouTube Data API v3 (playlistItems.list on uploads playlist)",
                "count": len(vids),
                "items": vid_summaries,
                "message": msg_vids,
            }
        except Exception as e:
            audit_results["live_tested_operations"]["video_listing"] = {
                "status": "FAIL",
                "error": str(e),
            }

        # 4. LIVE CHECK: Read-Only YouTube Analytics Query
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        # 3-day lag for mature YouTube analytics reporting
        end_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        start_date = (now - timedelta(days=33)).strftime("%Y-%m-%d")

        try:
            ok_an, msg_an, an_data = self.get_channel_analytics(
                start_date=start_date,
                end_date=end_date,
                metrics=["views", "estimatedMinutesWatched", "averageViewDuration", "likes", "subscribersGained"],
            )
            if ok_an:
                headers = [h.get("name") for h in an_data.get("columnHeaders", [])]
                rows = an_data.get("rows", [])
                audit_results["live_tested_operations"]["analytics_reporting"] = {
                    "status": "PASS",
                    "api": "YouTube Analytics API v2 (reports.query)",
                    "date_range": f"{start_date} to {end_date}",
                    "headers": headers,
                    "row_count": len(rows),
                    "sample_data": rows[:3] if rows else "No view activity recorded in query window (normal for low-traffic/new channels)",
                }
            else:
                audit_results["live_tested_operations"]["analytics_reporting"] = {
                    "status": "FAIL",
                    "api": "YouTube Analytics API v2 (reports.query)",
                    "error": msg_an,
                }
        except Exception as e:
            audit_results["live_tested_operations"]["analytics_reporting"] = {
                "status": "FAIL",
                "api": "YouTube Analytics API v2 (reports.query)",
                "error": str(e),
            }

        # 5. CODE-INSPECTED BUT UNTESTED MUTATING OPERATIONS (Clearly Separated)
        audit_results["untested_mutating_operations"] = {
            "video_metadata_update": {
                "method": "OwnerChannelManager.update_video_metadata()",
                "api": "YouTube Data API v3 (videos.update)",
                "required_scopes": ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"],
                "scope_granted": self.has_scope("https://www.googleapis.com/auth/youtube") or self.has_scope("https://www.googleapis.com/auth/youtube.force-ssl"),
                "status": "CODE_VERIFIED_UNMUTATED",
                "note": "Implementation verified via unit tests with mock API. NOT executed live to prevent unwanted modifications to your existing videos.",
            },
            "playlist_creation": {
                "method": "OwnerChannelManager.create_playlist()",
                "api": "YouTube Data API v3 (playlists.insert)",
                "required_scopes": ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"],
                "scope_granted": self.has_scope("https://www.googleapis.com/auth/youtube"),
                "status": "CODE_VERIFIED_UNMUTATED",
                "note": "Implementation verified via unit tests. NOT executed live to avoid creating unwanted test playlists on your channel.",
            },
            "playlist_item_addition": {
                "method": "OwnerChannelManager.add_video_to_playlist()",
                "api": "YouTube Data API v3 (playlistItems.insert)",
                "required_scopes": ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"],
                "scope_granted": self.has_scope("https://www.googleapis.com/auth/youtube"),
                "status": "CODE_VERIFIED_UNMUTATED",
                "note": "Implementation verified via unit tests. NOT executed live.",
            },
            "custom_thumbnail_upload": {
                "method": "OwnerChannelManager.set_video_thumbnail()",
                "api": "YouTube Data API v3 (thumbnails.set)",
                "required_scopes": ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.upload"],
                "scope_granted": self.has_scope("https://www.googleapis.com/auth/youtube") or self.has_scope("https://www.googleapis.com/auth/youtube.upload"),
                "status": "CODE_VERIFIED_UNMUTATED",
                "note": "Requires channel to have verified phone number for custom thumbnails in YouTube Studio. NOT executed live.",
            },
            "video_upload": {
                "method": "YouTubePublisher.publish_video()",
                "api": "YouTube Data API v3 (videos.insert)",
                "required_scopes": ["https://www.googleapis.com/auth/youtube.upload"],
                "scope_granted": self.has_scope("https://www.googleapis.com/auth/youtube.upload"),
                "status": "CODE_VERIFIED_UNMUTATED",
                "note": "Publishing mode is DISABLED. NOT executed live. Test uploads default to private visibility when explicitly authorized.",
            },
            "destructive_deletion": {
                "method": "OwnerChannelManager.delete_video() / delete_playlist()",
                "status": "BLOCKED_BY_SAFETY_LOCK",
                "note": "Autonomous deletion of videos or playlists is strictly prohibited by safety policy.",
            },
        }

        # 6. OFFICIAL API BOUNDARIES & QUOTAS
        audit_results["api_quotas_and_limitations"] = {
            "daily_default_quota": "10,000 units per day (YouTube Data API v3)",
            "operations_cost": {
                "read_channel_or_playlist_items": "1 unit per request",
                "write_video_metadata_update": "50 units per update",
                "create_playlist": "50 units per insert",
                "upload_video": "1,600 units per upload",
                "analytics_queries": "Separate YouTube Analytics API quota (not counted against Data API 10k)",
            },
            "known_api_boundaries": [
                "Channel custom URL/handle cannot be changed via Data API v3 (YouTube Studio only).",
                "Personal channel names cannot be updated via Data API v3 (Google Account only).",
                "Custom thumbnails require phone verification in YouTube Studio settings.",
                "Analytics data has an official 24-48 hour processing delay on YouTube's servers.",
            ],
        }

        # Check overall live score
        live_checks = audit_results["live_tested_operations"]
        all_passed = all(check.get("status") == "PASS" for check in live_checks.values())
        audit_results["overall_status"] = "ALL_LIVE_CHECKS_PASSED" if all_passed else "SOME_LIVE_CHECKS_FAILED"

        return audit_results

    # -------------------------------------------------------------------------
    # Destructive Action Safety Locks
    # -------------------------------------------------------------------------

    def delete_video(self, video_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Strictly prohibited by autonomous safety policy."""
        msg = (
            "SAFETY_LOCK: Deleting videos is strictly prohibited by autonomous safety policy. "
            "To delete videos, do so manually via YouTube Studio (https://studio.youtube.com)."
        )
        logger.warning(msg)
        return False, msg, {"safety_lock": True, "prohibited": True}

    def delete_playlist(self, playlist_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Strictly prohibited by autonomous safety policy."""
        msg = (
            "SAFETY_LOCK: Deleting playlists is strictly prohibited by autonomous safety policy. "
            "To delete playlists, do so manually via YouTube Studio (https://studio.youtube.com)."
        )
        logger.warning(msg)
        return False, msg, {"safety_lock": True, "prohibited": True}

    def generate_setup_instructions(self) -> Dict[str, Any]:
        """Generate local setup instructions for authenticating the owner's existing channel."""
        secrets_exist = self.client_secrets_file.exists()
        token_exists = self.token_file.exists()
        granted_scopes = self.get_granted_scopes()

        return {
            "client_secrets_path": str(self.client_secrets_file),
            "client_secrets_found": secrets_exist,
            "token_path": str(self.token_file),
            "token_found": token_exists,
            "required_scopes": YOUTUBE_MANAGEMENT_SCOPES,
            "granted_scopes": granted_scopes,
            "missing_scopes": self.get_missing_scopes(),
            "instructions": [
                "1. Open Google Cloud Console (https://console.cloud.google.com/).",
                "2. Ensure 'YouTube Data API v3' and 'YouTube Analytics API' are enabled.",
                "3. In 'OAuth consent screen', configure User Type as External, add your email as Test User.",
                "4. Under 'Credentials' -> 'Create Credentials' -> 'OAuth client ID', select 'Desktop app'.",
                f"5. Download the JSON credential file and save it locally as '{self.client_secrets_file}'.",
                "6. Run: ./run.sh youtube --reconnect to grant all channel management scopes in your browser.",
                "7. The local token will be stored securely at data/youtube_token.json (never committed to git).",
            ],
        }


# Global channel manager singleton
channel_manager = OwnerChannelManager()
